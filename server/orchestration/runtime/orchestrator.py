from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any

from db.database import database
from orchestration.agents.stubs import AGENT_STUBS
from orchestration.contracts.contract_builder import ContractBuilder
from orchestration.contracts.contract_validator import ContractValidator
from orchestration.generation.patch_generator import PatchGenerator
from orchestration.observability import alerts, metrics
from orchestration.observability.audit_ledger import AuditLedger
from orchestration.planning.master_planner import MasterPlanner
from orchestration.planning.plan_schema import (
    AgentResult,
    AgentSpec,
    ExecutionPlan,
    PipelineResult,
)
from orchestration.runtime.checkpoint import PipelineCheckpoint
from orchestration.runtime.failure_handler import FailureHandler
from orchestration.scoring.generic_scorer import GenericConfidenceScorer


AgentCallable = Callable[[dict[str, Any], str | None], Awaitable[dict[str, Any]] | dict[str, Any]]


class PipelineOrchestrator:
    def __init__(
        self,
        planner: MasterPlanner | None = None,
        checkpoint: PipelineCheckpoint | None = None,
        scorer: GenericConfidenceScorer | None = None,
        agent_registry: dict[str, AgentCallable] | None = None,
        patch_generator: PatchGenerator | None = None,
    ) -> None:
        self.planner = planner or MasterPlanner()
        self.checkpoint = checkpoint or PipelineCheckpoint()
        self.scorer = scorer or GenericConfidenceScorer()
        self.agent_registry = agent_registry or {}
        self.contract_builder = ContractBuilder()
        self.contract_validator = ContractValidator()
        self.failure_handler = FailureHandler()
        self.patch_generator = patch_generator or PatchGenerator()
        self.audit_ledger = AuditLedger()

    async def run_pipeline(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        plan: ExecutionPlan | None = None,
    ) -> PipelineResult:
        context = context or {}
        plan = plan or await self.planner.build_plan(task, context)
        run_id = plan.run_id
        user_id = plan.context.get("user_id")
        await self._update_plan_status(run_id, "running")

        results: dict[str, AgentResult] = {}
        suspended_agents: set[str] = set()
        skipped_agents: set[str] = set()
        degraded = False

        missing = set(await self.checkpoint.resume_from(run_id, plan))
        for agent in plan.agents:
            if agent.id not in missing:
                output = await self.checkpoint.get_output(run_id, agent.id, user_id=user_id)
                results[agent.id] = AgentResult(
                    agent_id=agent.id,
                    status="success",
                    output=output,
                    score=1.0,
                    attempts=0,
                )

        while missing:
            ready = [
                agent
                for agent in plan.agents
                if agent.id in missing
                and agent.id not in suspended_agents
                and all(self._dependency_satisfied(dep, results) for dep in agent.depends_on)
            ]
            if not ready:
                suspended_agents.update(missing)
                break

            batch_results = await asyncio.gather(
                *(self.run_agent_with_validation(agent.id, plan, run_id) for agent in ready)
            )

            for result in batch_results:
                results[result.agent_id] = result
                missing.discard(result.agent_id)

            for result in batch_results:
                if result.status in {"success", "fallback_success"}:
                    if result.status == "fallback_success":
                        degraded = True
                    continue

                decision = self.failure_handler.decide(
                    result.agent_id,
                    plan,
                    results,
                    fallback_activated=result.status == "fallback_success",
                )
                suspended_agents.update(decision.suspended_agents)
                skipped_agents.update(decision.skipped_agents)
                missing.difference_update(decision.suspended_agents)
                missing.difference_update(decision.skipped_agents)
                if decision.degraded:
                    degraded = True
                if not decision.continue_pipeline:
                    missing.clear()
                    break

        status = self._final_status(plan, results, suspended_agents, skipped_agents, degraded)
        metrics.pipeline_status(run_id, status)
        await self._update_plan_status(run_id, status)
        return PipelineResult(
            run_id=run_id,
            status=status,
            plan=plan.model_copy(update={"status": status}),
            results=results,
            suspended_agents=sorted(suspended_agents),
            skipped_agents=sorted(skipped_agents),
            errors=[
                error
                for result in results.values()
                for error in result.errors
                if result.status in {"failed", "suspended"}
            ],
        )

    async def run_agent_with_validation(self, agent_id: str, plan: ExecutionPlan, run_id: str) -> AgentResult:
        spec = plan.agent_map()[agent_id]
        user_id = plan.context.get("user_id")
        existing = await self.checkpoint.get_output(run_id, agent_id, user_id=user_id)
        if existing is not None:
            return AgentResult(agent_id=agent_id, status="success", output=existing, score=1.0, attempts=0)

        agent_fn = self._resolve_agent(agent_id)
        if agent_fn is None:
            return AgentResult(
                agent_id=agent_id,
                status="failed",
                attempts=0,
                errors=[f"No callable registered for agent '{agent_id}'"],
            )

        retry_hint: str | None = None
        last_errors: list[str] = []
        for attempt in range(1, spec.max_retries + 1):
            output = await self._invoke_agent(agent_fn, await self._build_inputs(spec, plan, run_id), retry_hint)
            scoring = await self.scorer.score(output, spec, await self._agent_manifest(agent_id))
            metrics.agent_score(run_id, agent_id, scoring.score)
            metrics.threshold_delta(run_id, agent_id, round(scoring.score - scoring.threshold, 4))
            metrics.retries_per_agent(run_id, agent_id, attempt - 1)

            if spec.critical and not scoring.passed and attempt == 1:
                alerts.critical_below_threshold(agent_id, run_id, scoring.score, scoring.threshold, attempt)

            if not scoring.passed:
                last_errors = scoring.details
                retry_hint = self._scoring_retry_hint(scoring.failed_checks, scoring.score, scoring.threshold)
                continue

            contract_errors = await self._validate_downstream_contracts(output, spec, plan, run_id)
            if contract_errors:
                last_errors = contract_errors
                retry_hint = "Contract validation failed: " + "; ".join(contract_errors)
                continue

            # --- Patch generation & diff budget check ---
            # Extract the text content from the agent output to run through
            # the patch generator (works with both 'content' field and full dicts).
            agent_text = output.get("content", "") if isinstance(output.get("content"), str) else ""
            if not agent_text:
                # Fallback: JSON-encode the whole output as the patch text
                agent_text = json.dumps(output, default=str)
            patch_result = self.patch_generator.process(
                agent_output=agent_text,
                task_description=spec.task,
            )
            # Attach patch metadata to output so it flows to checkpoint + audit ledger
            output_with_patch = {
                **output,
                "_patch": {
                    "task_type": patch_result.task_type,
                    "total_files": patch_result.total_files,
                    "total_lines": patch_result.total_lines,
                    "within_budget": patch_result.budget.within_budget if patch_result.budget else True,
                    "requires_approval": patch_result.budget.requires_approval if patch_result.budget else False,
                    "violation_reason": patch_result.budget.violation_reason if patch_result.budget else None,
                    "risk_level": self.patch_generator.infer_risk_level(patch_result.patches),
                    "semantic_summary": patch_result.semantic_summary,
                    "search_replace_blocks": patch_result.search_replace_blocks,
                },
            }
            if patch_result.budget and not patch_result.budget.within_budget:
                alerts.contract_validation_failed(
                    run_id, agent_id, "diff_budget",
                    [patch_result.budget.violation_reason or "Diff budget exceeded"],
                )
            metrics.agent_score(run_id, agent_id + "_patch_files", patch_result.total_files)
            metrics.agent_score(run_id, agent_id + "_patch_lines", patch_result.total_lines)

            await self.checkpoint.save(run_id, agent_id, output_with_patch, scoring.score, user_id=user_id)
            await self.audit_ledger.record(
                run_id=run_id,
                agent_id=agent_id,
                user_id=user_id,
                task_description=spec.task,
                patch_metadata=output_with_patch.get("_patch"),
                validation_passed=scoring.passed,
                confidence_score=scoring.score,
                integration_status="merged",
                build_status="passed" if scoring.passed else "failed",
            )
            return AgentResult(
                agent_id=agent_id,
                status="success",
                output=output_with_patch,
                score=scoring.score,
                attempts=attempt,
            )

        fallback_result = await self._try_fallback(spec, plan, run_id, retry_hint)
        if fallback_result is not None:
            return fallback_result

        return AgentResult(
            agent_id=agent_id,
            status="failed",
            attempts=spec.max_retries,
            errors=last_errors,
            retry_hint=retry_hint,
        )

    async def _try_fallback(
        self,
        spec: AgentSpec,
        plan: ExecutionPlan,
        run_id: str,
        retry_hint: str | None,
    ) -> AgentResult | None:
        if not spec.fallback:
            return None
        fallback_fn = self._resolve_agent(spec.fallback)
        if fallback_fn is None:
            return None
        output = await self._invoke_agent(fallback_fn, await self._build_inputs(spec, plan, run_id), retry_hint)
        scoring = await self.scorer.score(output, spec, await self._agent_manifest(spec.id))
        if not scoring.passed:
            return AgentResult(
                agent_id=spec.id,
                status="failed",
                attempts=spec.max_retries,
                errors=scoring.details,
                retry_hint=self._scoring_retry_hint(scoring.failed_checks, scoring.score, scoring.threshold),
            )
        contract_errors = await self._validate_downstream_contracts(output, spec, plan, run_id)
        if contract_errors:
            return AgentResult(
                agent_id=spec.id,
                status="failed",
                attempts=spec.max_retries,
                errors=contract_errors,
                retry_hint="Contract validation failed: " + "; ".join(contract_errors),
            )
        await self.checkpoint.save(run_id, spec.id, output, scoring.score, user_id=plan.context.get("user_id"))
        metrics.fallback_activations_total(run_id, spec.id, 1)
        return AgentResult(
            agent_id=spec.id,
            status="fallback_success",
            output=output,
            score=scoring.score,
            attempts=spec.max_retries,
        )

    async def _validate_downstream_contracts(
        self,
        output: dict[str, Any],
        spec: AgentSpec,
        plan: ExecutionPlan,
        run_id: str,
    ) -> list[str]:
        errors: list[str] = []
        for contract in self.contract_builder.downstream_contracts(plan, spec.id):
            result = await self.contract_validator.validate(output, contract)
            if not result.passed:
                errors.extend(result.errors)
                metrics.contract_violations_total(run_id, spec.id, len(result.errors))
                alerts.contract_validation_failed(run_id, spec.id, contract.consumer_id, result.errors)
        return errors

    async def _build_inputs(self, spec: AgentSpec, plan: ExecutionPlan, run_id: str) -> dict[str, Any]:
        inputs: dict[str, Any] = {"task": spec.task, "context": plan.context, "dependencies": {}}
        user_id = plan.context.get("user_id")
        for producer_id, fields in spec.consumes_from.items():
            output = await self.checkpoint.get_output(run_id, producer_id, user_id=user_id)
            if output is None:
                continue
            inputs["dependencies"][producer_id] = {field: output.get(field) for field in fields}
        return inputs

    def _resolve_agent(self, agent_id: str) -> AgentCallable | None:
        return self.agent_registry.get(agent_id) or AGENT_STUBS.get(agent_id)

    async def _invoke_agent(
        self,
        agent_fn: AgentCallable,
        inputs: dict[str, Any],
        retry_hint: str | None,
    ) -> dict[str, Any]:
        result = agent_fn(inputs, retry_hint)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            raise TypeError(f"Agent returned {type(result).__name__}, expected dict")
        return result

    def _dependency_satisfied(self, dependency: str, results: dict[str, AgentResult]) -> bool:
        result = results.get(dependency)
        return result is not None and result.status in {"success", "fallback_success"}

    def _scoring_retry_hint(self, failed_checks: list[str], score: float, threshold: float) -> str:
        delta = round(score - threshold, 4)
        return (
            f"Confidence gate failed. Failed checks: {', '.join(failed_checks)}. "
            f"Score {score:.4f}, threshold {threshold:.4f}, delta {delta:.4f}. "
            "Fix exactly those check failures and preserve the expected output contract."
        )

    def _final_status(
        self,
        plan: ExecutionPlan,
        results: dict[str, AgentResult],
        suspended_agents: set[str],
        skipped_agents: set[str],
        degraded: bool,
    ) -> str:
        if degraded:
            return "degraded_success"
        if suspended_agents:
            return "suspended_partial"
        failed = [result for result in results.values() if result.status == "failed"]
        if any(plan.agent_map()[result.agent_id].critical for result in failed):
            return "failed"
        if failed or skipped_agents:
            return "partial_success"
        return "success"

    async def _agent_manifest(self, agent_id: str) -> dict[str, Any]:
        try:
            conn = await database.get_conn()
        except Exception:
            return {}
        try:
            row = await conn.fetchrow("SELECT manifest_json FROM agent_manifests WHERE agent_id = $1", agent_id)
            if not row:
                return {}
            value = row["manifest_json"]
            return dict(value) if not isinstance(value, str) else json.loads(value)
        except Exception:
            return {}
        finally:
            await database.release_conn(conn)

    async def _update_plan_status(self, run_id: str, status: str) -> None:
        try:
            conn = await database.get_conn()
        except Exception:
            return
        try:
            await conn.execute(
                "UPDATE pipeline_execution_plans SET status = $2, updated_at = now() WHERE run_id = $1",
                run_id,
                status,
            )
        except Exception:
            pass
        finally:
            await database.release_conn(conn)


async def orchestration_node(state: dict[str, Any]) -> dict[str, Any]:
    orchestrator = PipelineOrchestrator()
    context = dict(state.get("context") or state.get("context_payload") or {})
    if state.get("user_id"):
        context["user_id"] = state["user_id"]
    result = await orchestrator.run_pipeline(
        task=str(state.get("goal") or state.get("task") or ""),
        context=context,
    )
    state["orchestration_result"] = result.model_dump()
    return state

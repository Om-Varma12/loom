from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from langchain_groq import ChatGroq

from config.config import QWEN_MODEL
from db.database import database
from graph.llm_utils import compact_text
from observability.execution_logger import log_execution_event
from prompts.prompts import AGENT_PROMPT_MAP
from orchestration.planning.plan_schema import (
    AgentSpec,
    ExecutionPlan,
    ExpectedOutputField,
    FailurePolicy,
)
from orchestration.planning.plan_validator import PlanValidator
from orchestration.planning.decomposition_engine import DecompositionEngine


SUPPORTED_AGENT_IDS = set(AGENT_PROMPT_MAP)
SPECIALIZED_AGENT_IDS = SUPPORTED_AGENT_IDS - {"all_rounder"}
UNSUPPORTED_AGENT_ALIASES = {
    "db_agent": "postgresql",
    "database_agent": "postgresql",
    "database": "postgresql",
    "python_agent": "all_rounder",
    "python": "all_rounder",
    "logic_agent": "all_rounder",
    "backend_agent": "fastapi",
    "backend": "fastapi",
    "api_agent": "fastapi",
    "flask": "fastapi",
    "streamlit_agent": "streamlit",
    "frontend": "streamlit",
    "ui": "streamlit",
    "readme_agent": "all_rounder",
    "docs_agent": "all_rounder",
    "documentation": "all_rounder",
}


class MasterPlanner:
    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm
        self.validator = PlanValidator()
        self.decomposition_engine = DecompositionEngine(llm=llm)

    async def build_plan(self, task: str, context: dict[str, Any]) -> ExecutionPlan:
        run_id = str(context.get("run_id") or uuid.uuid4())
        raw_plan = await self._llm_plan(task, context, run_id)
        plan = self._normalize_plan(raw_plan, task, context, run_id)
        plan = self._coerce_to_available_agents(plan, task, context, run_id)
        plan = self._apply_dynamic_thresholds(plan)
        validation = await self.validator.validate(plan)
        if not validation.passed:
            raise ValueError("Invalid execution plan: " + "; ".join(validation.errors))

        # Build hierarchical task graph via decomposition engine and attach to plan
        try:
            task_graph = await self.decomposition_engine.decompose(task, context)
            plan = plan.model_copy(update={"task_graph": task_graph})
            log_execution_event(
                "orchestration.plan.task_graph_built",
                {"run_id": run_id, "node_count": len(task_graph.nodes)},
            )
        except Exception as exc:
            log_execution_event(
                "orchestration.plan.task_graph_skipped",
                {"run_id": run_id, "error": str(exc)},
            )

        await self._persist_plan(plan)
        return plan

    async def _llm_plan(self, task: str, context: dict[str, Any], run_id: str) -> dict[str, Any]:
        if not os.getenv("GROQ_API_KEY_1") and self.llm is None:
            return self._calculator_plan_json(task, context, run_id)

        llm = self.llm or ChatGroq(
            model=QWEN_MODEL,
            api_key=os.environ.get("GROQ_API_KEY_1"),
            temperature=0.2,
            max_tokens=1536,
        )
        prompt = self._planner_prompt(task, context, run_id)
        messages = [
            {"role": "system", "content": "Return only JSON matching the requested ExecutionPlan shape."},
            {"role": "user", "content": prompt},
        ]
        try:
            response = await llm.ainvoke(messages) if hasattr(llm, "ainvoke") else llm.invoke(messages)
            raw = getattr(response, "content", str(response))
            return json.loads(self._strip_json(raw))
        except Exception as exc:
            log_execution_event(
                "orchestration.plan.llm_fallback",
                {"run_id": run_id, "error": str(exc)},
            )
            return self._calculator_plan_json(task, context, run_id)

    def _planner_prompt(self, task: str, context: dict[str, Any], run_id: str) -> str:
        context_json = compact_text(json.dumps(context, default=str), 4000)
        return f"""
Build a complete JSON ExecutionPlan for this multi-agent task.

Task: {task}
Run ID: {run_id}
Context JSON: {context_json}

Schema:
{{
  "run_id": "str",
  "task": "str",
  "context": {{}},
  "failure_policy": {{
    "max_retries": 3,
    "non_critical_failure": "skip_continue",
    "critical_failure_no_downstream": "fail_checkpoint_prior",
    "critical_failure_with_unblocked_siblings": "suspend_blocked_continue_unblocked",
    "fallback_activation": "degraded_success"
  }},
  "agents": [
    {{
      "id": "agent_id",
      "role": "short role",
      "task": "specific task",
      "critical": true,
      "depends_on": [],
      "consumes_from": {{"producer_id": ["field"]}},
      "expected_output": {{"field": {{"type": "str|int|float|bool|list|dict|any", "required": true}}}},
      "scoring_checks": ["all_required_fields_present"],
      "confidence_threshold": 0.6,
      "fallback": null,
      "max_retries": 3
    }}
  ],
  "status": "pending"
}}

Use plan-declared contracts only. For calculator app tasks, include db_agent, python_agent,
backend_agent, streamlit_agent, and readme_agent with the dependencies in Issue #20.
"""

    def _normalize_plan(
        self,
        raw_plan: dict[str, Any],
        task: str,
        context: dict[str, Any],
        run_id: str,
    ) -> ExecutionPlan:
        if "plan" in raw_plan and "agents" not in raw_plan:
            raw_plan = self._legacy_steps_to_plan(raw_plan["plan"], task, context, run_id)
        raw_plan.setdefault("run_id", run_id)
        raw_plan.setdefault("task", task)
        raw_plan.setdefault("context", context)
        raw_plan.setdefault("failure_policy", FailurePolicy().model_dump())
        raw_plan.setdefault("status", "pending")
        return ExecutionPlan.model_validate(raw_plan)

    def _coerce_to_available_agents(
        self,
        plan: ExecutionPlan,
        task: str,
        context: dict[str, Any],
        run_id: str,
    ) -> ExecutionPlan:
        requested_agents = self._requested_available_agents(context)
        available_agents = set(requested_agents or SUPPORTED_AGENT_IDS)
        unsupported = [
            agent.id
            for agent in plan.agents
            if self._canonical_agent_id(agent.id, task, available_agents) != agent.id
            or self._uses_non_generic_contract(agent)
        ]
        if not unsupported:
            return plan

        log_execution_event(
            "orchestration.plan.coerced_to_available_agents",
            {
                "run_id": run_id,
                "unsupported_agents": unsupported,
                "available_agents": sorted(available_agents),
            },
        )
        return ExecutionPlan.model_validate(
            self._available_agent_plan_json(task, context, run_id, requested_agents)
        )

    def _requested_available_agents(self, context: dict[str, Any]) -> list[str]:
        raw_agents = context.get("available_agents") or context.get("selected_agents") or []
        agents: list[str] = []
        for raw_agent in raw_agents:
            canonical = self._canonical_agent_id(str(raw_agent), "", SUPPORTED_AGENT_IDS)
            if canonical in SUPPORTED_AGENT_IDS and canonical not in agents:
                agents.append(canonical)
        return agents

    def _canonical_agent_id(self, agent_id: str, task: str, available_agents: set[str]) -> str:
        normalized = agent_id.lower().strip().replace(" ", "_").replace("-", "_")
        normalized = normalized.removesuffix("_agent") if normalized not in SUPPORTED_AGENT_IDS else normalized
        candidates = [
            agent_id,
            normalized,
            UNSUPPORTED_AGENT_ALIASES.get(agent_id),
            UNSUPPORTED_AGENT_ALIASES.get(normalized),
        ]
        for candidate in candidates:
            if candidate and candidate in available_agents:
                return candidate

        if any(term in normalized for term in ("db", "database", "sql")):
            return self._preferred_data_agent(task, available_agents)
        if any(term in normalized for term in ("backend", "api", "route", "flask")) and "fastapi" in available_agents:
            return "fastapi"
        if any(term in normalized for term in ("front", "ui", "streamlit")) and "streamlit" in available_agents:
            return "streamlit"
        if any(term in normalized for term in ("auth", "login")) and "auth" in available_agents:
            return "auth"
        return "all_rounder" if "all_rounder" in available_agents else sorted(available_agents)[0]

    def _uses_non_generic_contract(self, agent: AgentSpec) -> bool:
        return set(agent.expected_output) != {"content"} or agent.scoring_checks != [
            "all_required_fields_present",
            "output_not_empty",
        ]

    def _preferred_data_agent(self, task: str, available_agents: set[str]) -> str:
        lower_task = task.lower()
        preferences = []
        if "mongo" in lower_task:
            preferences.extend(["mongodb", "postgresql", "supabase"])
        elif "supabase" in lower_task:
            preferences.extend(["supabase", "postgresql", "mongodb"])
        else:
            preferences.extend(["postgresql", "mongodb", "supabase"])
        for candidate in preferences:
            if candidate in available_agents:
                return candidate
        return "all_rounder" if "all_rounder" in available_agents else sorted(available_agents)[0]

    def _available_agent_plan_json(
        self,
        task: str,
        context: dict[str, Any],
        run_id: str,
        requested_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        available_agents = set(requested_agents or SUPPORTED_AGENT_IDS)
        selected: list[str] = []

        def add(agent_id: str) -> None:
            if agent_id in available_agents and agent_id not in selected:
                selected.append(agent_id)

        lower_task = task.lower()
        if any(term in lower_task for term in ("database", "db", "store data", "sql", "mongo", "supabase")):
            add(self._preferred_data_agent(task, available_agents))
        if any(term in lower_task for term in ("auth", "login", "user")):
            add("auth")
        if any(term in lower_task for term in ("api", "backend", "route", "fastapi", "flask", "streamlit", "frontend")):
            add("fastapi")
        if any(term in lower_task for term in ("streamlit", "frontend", "ui", "dashboard")):
            add("streamlit")
        if any(term in lower_task for term in ("python", "logic", "calculator", "readme", "documentation", "docs")):
            add("all_rounder")
        if not selected:
            add("all_rounder")

        agents: list[dict[str, Any]] = []
        prior_agent: str | None = None
        for agent_id in selected:
            depends_on = [prior_agent] if prior_agent else []
            consumes_from = {prior_agent: ["content"]} if prior_agent else {}
            agents.append(
                {
                    "id": agent_id,
                    "role": self._agent_role(agent_id),
                    "task": self._agent_task(agent_id, task),
                    "critical": agent_id != "all_rounder",
                    "depends_on": depends_on,
                    "consumes_from": consumes_from,
                    "expected_output": {"content": {"type": "str", "required": True, "min_length": 1}},
                    "scoring_checks": ["all_required_fields_present", "output_not_empty"],
                    "confidence_threshold": 0.60,
                    "fallback": None,
                    "max_retries": 3,
                }
            )
            prior_agent = agent_id

        return {
            "run_id": run_id,
            "task": task,
            "context": context,
            "failure_policy": FailurePolicy().model_dump(),
            "status": "pending",
            "agents": agents,
        }

    def _agent_role(self, agent_id: str) -> str:
        roles = {
            "postgresql": "PostgreSQL database agent",
            "mongodb": "MongoDB database agent",
            "supabase": "Supabase backend agent",
            "fastapi": "FastAPI backend agent",
            "streamlit": "Streamlit frontend agent",
            "auth": "Authentication agent",
            "all_rounder": "All-rounder fallback agent",
        }
        return roles.get(agent_id, f"{agent_id.replace('_', ' ').title()} agent")

    def _agent_task(self, agent_id: str, task: str) -> str:
        tasks = {
            "postgresql": f"Design the PostgreSQL schema and persistence layer for: {task}",
            "mongodb": f"Design the MongoDB collections and data access layer for: {task}",
            "supabase": f"Design the Supabase schema/client layer for: {task}",
            "fastapi": f"Build the FastAPI backend/API layer for: {task}",
            "streamlit": f"Build the Streamlit frontend for: {task}",
            "auth": f"Add authentication and user/session handling for: {task}",
            "all_rounder": f"Fill any remaining app logic, Python modules, docs, or glue code for: {task}",
        }
        return tasks.get(agent_id, task)

    def _legacy_steps_to_plan(
        self,
        steps: list[dict[str, Any]],
        task: str,
        context: dict[str, Any],
        run_id: str,
    ) -> dict[str, Any]:
        agents: list[dict[str, Any]] = []
        for step in steps:
            agent_id = str(step.get("agent"))
            agents.append(
                {
                    "id": agent_id,
                    "role": agent_id,
                    "task": str(step.get("task") or task),
                    "critical": True,
                    "depends_on": list(step.get("context_keys") or []),
                    "consumes_from": {producer: [] for producer in step.get("context_keys") or []},
                    "expected_output": {"content": {"type": "str", "required": True}},
                    "scoring_checks": ["all_required_fields_present", "output_not_empty"],
                    "confidence_threshold": 0.6,
                    "fallback": None,
                    "max_retries": 3,
                }
            )
        return {"run_id": run_id, "task": task, "context": context, "agents": agents}

    def _apply_dynamic_thresholds(self, plan: ExecutionPlan) -> ExecutionPlan:
        updated_agents: list[AgentSpec] = []
        for agent in plan.agents:
            dependent_count = self.count_transitive_dependents(plan, agent.id)
            if dependent_count >= 2:
                threshold = 0.85
            elif dependent_count >= 1:
                threshold = 0.75
            elif agent.critical:
                threshold = 0.70
            else:
                threshold = 0.60
            updated_agents.append(agent.model_copy(update={"confidence_threshold": threshold}))
        return plan.model_copy(update={"agents": updated_agents})

    def count_transitive_dependents(self, plan: ExecutionPlan, agent_id: str) -> int:
        dependents: dict[str, list[str]] = {agent.id: [] for agent in plan.agents}
        for agent in plan.agents:
            for dependency in agent.depends_on:
                dependents.setdefault(dependency, []).append(agent.id)

        seen: set[str] = set()

        def walk(current: str) -> None:
            for child in dependents.get(current, []):
                if child not in seen:
                    seen.add(child)
                    walk(child)

        walk(agent_id)
        return len(seen)

    async def _persist_plan(self, plan: ExecutionPlan) -> None:
        try:
            conn = await database.get_conn()
        except Exception as exc:
            log_execution_event("orchestration.plan.persist_skipped", {"run_id": plan.run_id, "error": str(exc)})
            return
        try:
            await conn.execute(
                """
                INSERT INTO pipeline_execution_plans (run_id, task, plan_json, status, user_id, updated_at)
                VALUES ($1, $2, $3::jsonb, $4, $5, now())
                ON CONFLICT (run_id) DO UPDATE SET
                  task = EXCLUDED.task,
                  plan_json = EXCLUDED.plan_json,
                  status = EXCLUDED.status,
                  user_id = EXCLUDED.user_id,
                  updated_at = now()
                """,
                plan.run_id,
                plan.task,
                plan.model_dump_json(),
                plan.status,
                plan.context.get("user_id"),
            )
        except Exception as exc:
            log_execution_event("orchestration.plan.persist_error", {"run_id": plan.run_id, "error": str(exc)})
        finally:
            await database.release_conn(conn)

    def _strip_json(self, raw: str) -> str:
        raw = raw.strip()
        if "<think>" in raw and "</think>" in raw:
            raw = raw[raw.index("</think>") + len("</think>") :].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        match = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
        return match.group(0) if match else raw.strip().rstrip("```").strip()

    def _calculator_plan_json(self, task: str, context: dict[str, Any], run_id: str) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "task": task,
            "context": context,
            "failure_policy": FailurePolicy().model_dump(),
            "status": "pending",
            "agents": [
                {
                    "id": "db_agent",
                    "role": "PostgreSQL schema builder",
                    "task": "Create database schema and SQL for calculator operation history.",
                    "critical": True,
                    "depends_on": [],
                    "consumes_from": {},
                    "expected_output": {
                        "table_name": {"type": "str", "required": True},
                        "columns": {"type": "list", "required": True, "min_length": 1},
                        "pk_field": {"type": "str", "required": True, "nullable": False},
                        "create_sql": {"type": "str", "required": True},
                    },
                    "scoring_checks": [
                        "all_required_fields_present",
                        "no_nullable_pk",
                        "types_are_valid",
                        "sql_syntax_valid",
                    ],
                    "confidence_threshold": 0.85,
                    "fallback": "sqlite_agent",
                    "max_retries": 3,
                },
                {
                    "id": "python_agent",
                    "role": "Calculator business logic builder",
                    "task": "Create Python calculator functions for arithmetic operations.",
                    "critical": True,
                    "depends_on": [],
                    "consumes_from": {},
                    "expected_output": {
                        "module_path": {"type": "str", "required": True},
                        "functions": {"type": "list", "required": True, "min_length": 1},
                        "imports": {"type": "list", "required": True},
                    },
                    "scoring_checks": ["all_required_fields_present", "imports_resolve", "output_not_empty"],
                    "confidence_threshold": 0.85,
                    "fallback": None,
                    "max_retries": 3,
                },
                {
                    "id": "backend_agent",
                    "role": "FastAPI backend builder",
                    "task": "Expose calculator history and persistence routes using the database schema.",
                    "critical": True,
                    "depends_on": ["db_agent"],
                    "consumes_from": {"db_agent": ["table_name", "columns", "pk_field"]},
                    "expected_output": {
                        "routes": {"type": "list", "required": True, "min_length": 1},
                        "app_file": {"type": "str", "required": True},
                    },
                    "scoring_checks": ["all_required_fields_present", "routes_not_empty", "imports_resolve"],
                    "confidence_threshold": 0.75,
                    "fallback": None,
                    "max_retries": 3,
                },
                {
                    "id": "streamlit_agent",
                    "role": "Streamlit frontend builder",
                    "task": "Create a Streamlit UI that calls the Python calculator module.",
                    "critical": True,
                    "depends_on": ["python_agent"],
                    "consumes_from": {"python_agent": ["module_path", "functions"]},
                    "expected_output": {
                        "app_file": {"type": "str", "required": True},
                        "widgets": {"type": "list", "required": True, "min_length": 1},
                    },
                    "scoring_checks": ["all_required_fields_present", "output_not_empty", "imports_resolve"],
                    "confidence_threshold": 0.75,
                    "fallback": None,
                    "max_retries": 3,
                },
                {
                    "id": "readme_agent",
                    "role": "Documentation writer",
                    "task": "Document how to run and use the calculator app.",
                    "critical": False,
                    "depends_on": ["python_agent", "backend_agent", "streamlit_agent"],
                    "consumes_from": {
                        "python_agent": ["module_path", "functions"],
                        "backend_agent": ["app_file"],
                        "streamlit_agent": ["app_file"],
                    },
                    "expected_output": {"content": {"type": "str", "required": True}},
                    "scoring_checks": ["all_required_fields_present", "output_not_empty"],
                    "confidence_threshold": 0.60,
                    "fallback": None,
                    "max_retries": 3,
                },
            ],
        }

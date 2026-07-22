from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db.database import database
from orchestration.planning.plan_schema import ExecutionPlan, PipelineResult
from orchestration.runtime.checkpoint import PipelineCheckpoint
from orchestration.runtime.orchestrator import PipelineOrchestrator
from dependencies.auth_dep import CurrentUser, get_current_user


router = APIRouter(
    prefix="/api/orchestration",
    tags=["Orchestration"],
    dependencies=[Depends(get_current_user)],
)


class RunRequest(BaseModel):
    task: str
    context: dict[str, Any] = Field(default_factory=dict)


class RetryRequest(BaseModel):
    fix_description: str


class TaskNodeResponse(BaseModel):
    id: str
    parent_id: str | None = None
    agent_id: str
    task: str
    capabilities_required: list[str]
    capability_score: float
    selection_reasoning: str
    depends_on: list[str]


class TaskGraphResponse(BaseModel):
    nodes: list[TaskNodeResponse]
    selection_logs: list[str]


@router.post("/run", response_model=PipelineResult)
async def run_orchestration(
    request: RunRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> PipelineResult:
    orchestrator = PipelineOrchestrator()
    context = dict(request.context)
    context["user_id"] = current_user.id
    return await orchestrator.run_pipeline(request.task, context)


@router.get("/status/{run_id}")
async def get_orchestration_status(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    conn = await database.get_conn()
    try:
        row = await conn.fetchrow(
            """
            SELECT run_id, task, status, plan_json, created_at, updated_at
            FROM pipeline_execution_plans
            WHERE run_id = $1 AND user_id = $2
            """,
            run_id,
            current_user.id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        return dict(row)
    finally:
        await database.release_conn(conn)


@router.get("/plan/{run_id}/task-graph", response_model=TaskGraphResponse)
async def get_task_graph(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> TaskGraphResponse:
    """Return the hierarchical task graph and per-node agent selection reasoning for a pipeline run."""
    plan = await _load_plan(run_id, current_user.id)
    if plan.task_graph is None:
        raise HTTPException(
            status_code=404,
            detail="No task graph available for this run. The decomposition engine may not have run.",
        )
    nodes = [
        TaskNodeResponse(
            id=node.id,
            parent_id=node.parent_id,
            agent_id=node.agent_id,
            task=node.task,
            capabilities_required=node.capabilities_required,
            capability_score=node.capability_score,
            selection_reasoning=node.selection_reasoning,
            depends_on=node.depends_on,
        )
        for node in plan.task_graph.nodes
    ]
    selection_logs = [
        f"[{node.id}] agent={node.agent_id} score={node.capability_score:.2f} | {node.selection_reasoning}"
        for node in plan.task_graph.nodes
    ]
    return TaskGraphResponse(nodes=nodes, selection_logs=selection_logs)


@router.get("/agent/{run_id}/{agent_id}/output")
async def get_agent_output(
    run_id: str,
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    await _load_plan(run_id, current_user.id)
    output = await PipelineCheckpoint().get_output(run_id, agent_id, user_id=current_user.id)
    if output is None:
        raise HTTPException(status_code=404, detail="Checkpointed output not found")
    return {"run_id": run_id, "agent_id": agent_id, "output": output}


@router.post("/retry/{run_id}", response_model=PipelineResult)
async def retry_orchestration(
    run_id: str,
    request: RetryRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> PipelineResult:
    plan = await _load_plan(run_id, current_user.id)
    context = dict(plan.context)
    context["user_id"] = current_user.id
    context["fix_description"] = request.fix_description
    plan = plan.model_copy(update={"context": context})
    orchestrator = PipelineOrchestrator()
    return await orchestrator.run_pipeline(plan.task, context, plan=plan)


async def _load_plan(run_id: str, user_id: str) -> ExecutionPlan:
    conn = await database.get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT plan_json FROM pipeline_execution_plans WHERE run_id = $1 AND user_id = $2",
            run_id,
            user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        plan_json = row["plan_json"]
        if isinstance(plan_json, str):
            return ExecutionPlan.model_validate(json.loads(plan_json))
        return ExecutionPlan.model_validate(dict(plan_json))
    finally:
        await database.release_conn(conn)

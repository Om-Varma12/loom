"""
audit_route.py — REST API for the Loom semantic audit ledger.

Endpoints:
    GET /api/audit/{run_id}
        Returns all audit entries for the given pipeline run,
        ordered by creation time ascending.

    GET /api/audit/{run_id}/summary
        Returns a compact risk-annotated summary for the run:
        agent name → semantic change list + risk level.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictStr

from orchestration.observability.audit_ledger import AuditLedger
from dependencies.auth_dep import CurrentUser, get_current_user

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(get_current_user)],
)
_ledger = AuditLedger()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class AuditEntryResponse(BaseModel):
    run_id: StrictStr
    agent_id: StrictStr
    task_description: StrictStr = ""
    files_changed: int = 0
    lines_changed: int = 0
    task_type: StrictStr = "uncategorized"
    risk_level: StrictStr = "low"
    within_budget: bool = True
    requires_approval: bool = False
    violation_reason: StrictStr | None = None
    integration_status: StrictStr = "pending"
    build_status: StrictStr = "unknown"
    validation_passed: bool = False
    confidence_score: float | None = None
    semantic_summary: list[StrictStr] = []
    created_at: StrictStr = ""


class RunAuditSummary(BaseModel):
    run_id: StrictStr
    total_agents: int
    total_files_changed: int
    total_lines_changed: int
    risk_distribution: dict[str, int]     # low/medium/high → count
    budget_violations: int
    requires_approval_count: int
    agents: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

import json
from datetime import datetime

@router.get("/{run_id}", response_model=list[AuditEntryResponse])
async def get_audit_entries(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """
    Return all audit ledger entries for the given pipeline run.
    Entries are ordered chronologically (oldest first).
    """
    entries = await _ledger.get_entries(run_id, current_user.id)
    if not entries:
        raise HTTPException(
            status_code=404,
            detail=f"No audit entries found for run_id: {run_id}",
        )
    
    formatted = []
    for entry in entries:
        d = dict(entry)
        # Parse semantic_summary if it is a JSON string
        summary = d.get("semantic_summary", [])
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                summary = [summary]
        
        # Format created_at to ISO string if it is a datetime object
        created_at = d.get("created_at", "")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
            
        d["semantic_summary"] = summary
        d["created_at"] = created_at
        formatted.append(d)
        
    return formatted


@router.get("/{run_id}/summary", response_model=RunAuditSummary)
async def get_audit_summary(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> RunAuditSummary:
    """
    Return a compact risk-annotated summary for the given run.
    Suitable for displaying in the frontend's SemanticChangeSummary panel.
    """
    entries = await _ledger.get_entries(run_id, current_user.id)
    if not entries:
        raise HTTPException(
            status_code=404,
            detail=f"No audit entries found for run_id: {run_id}",
        )

    risk_dist: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    total_files = 0
    total_lines = 0
    violations = 0
    approval_needed = 0
    agents_summary: list[dict[str, Any]] = []

    for entry in entries:
        d = dict(entry)
        risk = d.get("risk_level", "low")
        risk_dist[risk] = risk_dist.get(risk, 0) + 1
        total_files += d.get("files_changed", 0)
        total_lines += d.get("lines_changed", 0)
        if not d.get("within_budget", True):
            violations += 1
        if d.get("requires_approval", False):
            approval_needed += 1

        summary = d.get("semantic_summary", [])
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                summary = [summary]

        agents_summary.append({
            "agent_id": d.get("agent_id", ""),
            "risk_level": risk,
            "semantic_summary": summary,
            "files_changed": d.get("files_changed", 0),
            "lines_changed": d.get("lines_changed", 0),
            "within_budget": d.get("within_budget", True),
            "confidence_score": d.get("confidence_score"),
            "build_status": d.get("build_status", "unknown"),
        })

    return RunAuditSummary(
        run_id=run_id,
        total_agents=len(entries),
        total_files_changed=total_files,
        total_lines_changed=total_lines,
        risk_distribution=risk_dist,
        budget_violations=violations,
        requires_approval_count=approval_needed,
        agents=agents_summary,
    )

"""
audit_ledger.py — Semantic audit ledger for Loom orchestration.

Records every agent change with full provenance:
  - Who made the change (agent_id)
  - What changed (files, lines, semantic summary)
  - Why it was made (task description)
  - Risk level (low / medium / high)
  - Compliance (within diff budget, requires approval)
  - Integration status (merged / rejected / needs_review)
  - Build / validation status

Persists to:
  1. Supabase (agent_audit_log table) — primary store
  2. Local JSONL file — fast append, works without DB connection

Usage:
    from orchestration.observability.audit_ledger import AuditLedger, AuditEntry

    ledger = AuditLedger()
    await ledger.record(
        run_id="run-42",
        agent_id="fastapi",
        task_description="Add auth routes",
        patch_metadata=output["_patch"],
        validation_passed=True,
        confidence_score=0.91,
    )
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

logger = logging.getLogger(__name__)

# Local JSONL file for audit log (useful when DB is unavailable)
_AUDIT_LOG_DIR = Path(os.environ.get("LOOM_AUDIT_DIR", "/tmp/loom_audit"))


class AuditEntry(BaseModel):
    """A single audit record for one agent execution."""
    model_config = ConfigDict(extra="allow")

    run_id: StrictStr
    agent_id: StrictStr
    user_id: StrictStr | None = None
    task_id: StrictStr | None = None
    task_description: StrictStr = ""

    # What changed
    files_changed: StrictInt = 0
    lines_changed: StrictInt = 0
    task_type: StrictStr = "uncategorized"

    # Risk & compliance
    risk_level: StrictStr = "low"
    within_budget: StrictBool = True
    requires_approval: StrictBool = False
    violation_reason: StrictStr | None = None

    # Integration & build status
    integration_status: StrictStr = "pending"
    build_status: StrictStr = "unknown"
    validation_passed: StrictBool = False
    confidence_score: StrictFloat | None = None

    # Human-readable summary
    semantic_summary: list[StrictStr] = Field(default_factory=list)
    patch_blocks: StrictStr | None = None

    created_at: StrictStr = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class AuditLedger:
    """
    Writes AuditEntry records to Supabase and a local JSONL file.
    Gracefully degrades: if DB is unavailable, only writes locally.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or _AUDIT_LOG_DIR

    async def record(
        self,
        run_id: str,
        agent_id: str,
        task_description: str = "",
        patch_metadata: dict[str, Any] | None = None,
        validation_passed: bool = False,
        confidence_score: float | None = None,
        task_id: str | None = None,
        integration_status: str = "merged",
        build_status: str = "unknown",
        user_id: str | None = None,
    ) -> AuditEntry:
        """
        Record a completed agent execution to the audit ledger.

        Args:
            run_id:              The pipeline run ID.
            agent_id:            The agent that produced output.
            task_description:    The task the agent was given.
            patch_metadata:      The _patch dict attached to agent output by the orchestrator.
            validation_passed:   Whether confidence scoring passed.
            confidence_score:    The confidence score (0.0–1.0).
            task_id:             Optional task node ID from the TaskGraph.
            integration_status:  One of: pending, merged, rejected, needs_review.
            build_status:        One of: unknown, passed, failed, skipped.

        Returns:
            The created AuditEntry.
        """
        pm = patch_metadata or {}

        entry = AuditEntry(
            run_id=run_id,
            agent_id=agent_id,
            user_id=user_id,
            task_id=task_id,
            task_description=task_description,
            files_changed=pm.get("total_files", 0),
            lines_changed=pm.get("total_lines", 0),
            task_type=pm.get("task_type", "uncategorized"),
            risk_level=pm.get("risk_level", "low"),
            within_budget=pm.get("within_budget", True),
            requires_approval=pm.get("requires_approval", False),
            violation_reason=pm.get("violation_reason"),
            integration_status=integration_status,
            build_status=build_status,
            validation_passed=validation_passed,
            confidence_score=confidence_score,
            semantic_summary=pm.get("semantic_summary", []),
            patch_blocks=pm.get("search_replace_blocks"),
        )

        # Write to local JSONL (always — fast, no network dependency)
        await self._write_local(run_id, entry)

        # Write to Supabase (best-effort — don't fail the pipeline on DB error)
        try:
            await self._write_supabase(entry)
        except Exception as exc:
            logger.warning("AuditLedger Supabase write raised unexpectedly: %s", exc)

        return entry

    async def _write_local(self, run_id: str, entry: AuditEntry) -> None:
        """Append the audit entry to a JSONL file in the log directory."""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.log_dir / f"{run_id}.jsonl"
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), default=str) + "\n")
        except Exception as exc:
            logger.warning("AuditLedger local write failed: %s", exc)

    async def _write_supabase(self, entry: AuditEntry) -> None:
        """Persist the audit entry to the Supabase agent_audit_log table."""
        try:
            from db.database import database
            conn = await database.get_conn()
        except Exception as exc:
            logger.debug("AuditLedger DB unavailable, skipping Supabase write: %s", exc)
            return
        try:
            await conn.execute(
                """
                INSERT INTO agent_audit_log (
                    run_id, agent_id, user_id, task_id, task_description,
                    files_changed, lines_changed, task_type,
                    risk_level, within_budget, requires_approval, violation_reason,
                    integration_status, build_status, validation_passed, confidence_score,
                    semantic_summary, patch_blocks
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8,
                    $9, $10, $11, $12,
                    $13, $14, $15, $16,
                    $17::jsonb, $18
                )
                """,
                entry.run_id, entry.agent_id, entry.user_id, entry.task_id, entry.task_description,
                entry.files_changed, entry.lines_changed, entry.task_type,
                entry.risk_level, entry.within_budget, entry.requires_approval, entry.violation_reason,
                entry.integration_status, entry.build_status, entry.validation_passed, entry.confidence_score,
                json.dumps(entry.semantic_summary), entry.patch_blocks,
            )
        except Exception as exc:
            logger.warning("AuditLedger Supabase write failed: %s", exc)
        finally:
            try:
                from db.database import database
                await database.release_conn(conn)
            except Exception:
                pass

    async def get_entries(self, run_id: str, user_id: str | None = None) -> list[dict[str, Any]]:
        """
        Retrieve all audit entries for a given run_id.
        Tries Supabase first, falls back to local JSONL.
        """
        try:
            from db.database import database
            conn = await database.get_conn()
            try:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM agent_audit_log
                    WHERE run_id = $1
                      AND ($2::uuid IS NULL OR user_id = $2)
                    ORDER BY created_at ASC
                    """,
                    run_id,
                    user_id,
                )
                return [dict(row) for row in rows]
            finally:
                await database.release_conn(conn)
        except Exception:
            pass

        # Fallback: read local JSONL
        log_file = self.log_dir / f"{run_id}.jsonl"
        if not log_file.exists():
            return []
        entries = []
        with log_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if user_id is None or entry.get("user_id") == user_id:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        pass
        return entries

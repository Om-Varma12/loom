from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from db.database import database
from orchestration.planning.plan_schema import ExecutionPlan


logger = logging.getLogger(__name__)
_MEMORY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
TTL_SECONDS = 24 * 60 * 60


class PipelineCheckpoint:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url if redis_url is not None else os.getenv("REDIS_URL")
        self.redis = None
        if not self.redis_url:
            logger.warning("REDIS_URL is not set; pipeline checkpoints will use in-memory cache")

    async def _redis_client(self) -> Any | None:
        if not self.redis_url:
            return None
        if self.redis is not None:
            return self.redis
        try:
            import redis.asyncio as redis

            self.redis = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis.ping()
            return self.redis
        except Exception as exc:
            logger.warning("Redis unavailable; falling back to in-memory cache: %s", exc)
            self.redis_url = None
            return None

    def _key(self, run_id: str, agent_id: str, user_id: str | None = None) -> str:
        owner = user_id or "global"
        return f"pipeline:{owner}:{run_id}:agent:{agent_id}:output"

    async def save(
        self,
        run_id: str,
        agent_id: str,
        output: dict[str, Any],
        score: float,
        user_id: str | None = None,
    ) -> None:
        payload = {"output": output, "score": score, "saved_at": time.time()}
        key = self._key(run_id, agent_id, user_id)
        redis_client = await self._redis_client()
        if redis_client is not None:
            await redis_client.set(key, json.dumps(payload, default=str), ex=TTL_SECONDS)
        else:
            _MEMORY_CACHE[key] = (time.time() + TTL_SECONDS, payload)
        await self._save_supabase(run_id, agent_id, output, score, user_id)

    async def get_output(
        self,
        run_id: str,
        agent_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any] | None:
        key = self._key(run_id, agent_id, user_id)
        redis_client = await self._redis_client()
        if redis_client is not None:
            raw = await redis_client.get(key)
            if raw:
                return json.loads(raw)["output"]
        cached = _MEMORY_CACHE.get(key)
        if cached:
            expires_at, payload = cached
            if expires_at > time.time():
                return payload["output"]
            _MEMORY_CACHE.pop(key, None)
        return await self._get_supabase_output(run_id, agent_id, user_id)

    async def resume_from(self, run_id: str, plan: ExecutionPlan) -> list[str]:
        missing: list[str] = []
        user_id = plan.context.get("user_id")
        for agent in plan.agents:
            output = await self.get_output(run_id, agent.id, user_id=user_id)
            if output is None:
                missing.append(agent.id)
        return missing

    async def _save_supabase(
        self,
        run_id: str,
        agent_id: str,
        output: dict[str, Any],
        score: float,
        user_id: str | None,
    ) -> None:
        try:
            conn = await database.get_conn()
        except Exception as exc:
            logger.warning("pipeline_agent_results persist skipped: %s", exc)
            return
        try:
            await conn.execute(
                """
                INSERT INTO pipeline_agent_results (run_id, agent_id, status, output_json, score, attempt_count, user_id)
                VALUES ($1, $2, 'success', $3::jsonb, $4, 1, $5)
                """,
                run_id,
                agent_id,
                json.dumps(output, default=str),
                score,
                user_id,
            )
        except Exception as exc:
            logger.warning("pipeline_agent_results persist error: %s", exc)
        finally:
            await database.release_conn(conn)

    async def _get_supabase_output(
        self,
        run_id: str,
        agent_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            conn = await database.get_conn()
        except Exception:
            return None
        try:
            row = await conn.fetchrow(
                """
                SELECT output_json
                FROM pipeline_agent_results
                WHERE run_id = $1 AND agent_id = $2 AND status = 'success'
                  AND ($3::uuid IS NULL OR user_id = $3)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                run_id,
                agent_id,
                user_id,
            )
            if not row:
                return None
            value = row["output_json"]
            return dict(value) if not isinstance(value, str) else json.loads(value)
        except Exception:
            return None
        finally:
            await database.release_conn(conn)

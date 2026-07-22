import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID
from db.database import database
from knowledge.memory_models import AgentMemoryEntry, AgentExecutionEntry, AgentDecisionEntry
from knowledge.memory_embedding_service import memory_embedding_service

logger = logging.getLogger(__name__)

def _vector_literal(values: List[float]) -> str:
    """Formats a list of floats into a pgvector-compatible string literal."""
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"

class AgentMemoryService:
    def __init__(self, db=database):
        self.db = db

    @property
    def has_pool(self) -> bool:
        return bool(getattr(self.db, "pool", None))

    async def resolve_agent_id(self, agent_name_or_id: str) -> str | None:
        """Resolves an agent name or ID to its database UUID string."""
        if not self.has_pool:
            return None
        try:
            UUID(agent_name_or_id)
            return agent_name_or_id
        except ValueError:
            pass
        conn = await self.db.get_conn()
        try:
            row = await conn.fetchrow(
                "SELECT id FROM agents WHERE LOWER(name) = LOWER($1) OR LOWER(name) LIKE LOWER($2) LIMIT 1",
                agent_name_or_id,
                f"%{agent_name_or_id}%"
            )
            if row:
                return str(row["id"])
            return None
        finally:
            await self.db.release_conn(conn)

    async def save_memory(self, entry: AgentMemoryEntry, user_id: str) -> AgentMemoryEntry:
        if not self.has_pool:
            raise RuntimeError("Database pool not initialized")
        
        # Generate memory embedding
        embedding = await memory_embedding_service.generate_embedding(
            entry.context, entry.summary, entry.learned_info
        )
        
        conn = await self.db.get_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO agent_memories (agent_id, context, summary, learned_info, tags, embedding, user_id)
                VALUES ($1, $2, $3, $4, $5, $6::vector, $7)
                RETURNING id, agent_id, context, summary, learned_info, tags, embedding, created_at
                """,
                entry.agent_id,
                entry.context,
                entry.summary,
                entry.learned_info,
                entry.tags,
                _vector_literal(embedding),
                user_id
            )
            data = dict(row)
            if data.get("embedding") is not None:
                from context_system.db import _parse_vector
                data["embedding"] = _parse_vector(data["embedding"])
            return AgentMemoryEntry(**data)
        finally:
            await self.db.release_conn(conn)

    async def get_memories(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[AgentMemoryEntry]:
        if not self.has_pool:
            return []
        conn = await self.db.get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, agent_id, context, summary, learned_info, tags, embedding, created_at FROM agent_memories
                WHERE user_id = $1
                  AND ($2::text IS NULL OR agent_id = $2)
                  AND ($3::text[] IS NULL OR tags && $3)
                ORDER BY created_at DESC
                """,
                user_id,
                agent_id,
                tags
            )
            results = []
            for row in rows:
                data = dict(row)
                if data.get("embedding") is not None:
                    from context_system.db import _parse_vector
                    data["embedding"] = _parse_vector(data["embedding"])
                results.append(AgentMemoryEntry(**data))
            return results
        finally:
            await self.db.release_conn(conn)

    async def save_execution(self, entry: AgentExecutionEntry, user_id: str) -> AgentExecutionEntry:
        if not self.has_pool:
            raise RuntimeError("Database pool not initialized")
        conn = await self.db.get_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO agent_executions (agent_id, task_id, input_data, output_data, status, metadata, user_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, agent_id, task_id, input_data, output_data, status, metadata, created_at
                """,
                entry.agent_id,
                entry.task_id,
                entry.input_data,
                entry.output_data,
                entry.status,
                json.dumps(entry.metadata),
                user_id
            )
            data = dict(row)
            if isinstance(data.get("metadata"), str):
                data["metadata"] = json.loads(data["metadata"])
            return AgentExecutionEntry(**data)
        finally:
            await self.db.release_conn(conn)

    async def get_executions(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> List[AgentExecutionEntry]:
        if not self.has_pool:
            return []
        conn = await self.db.get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, agent_id, task_id, input_data, output_data, status, metadata, created_at FROM agent_executions
                WHERE user_id = $1
                  AND ($2::text IS NULL OR agent_id = $2)
                  AND ($3::text IS NULL OR status = $3)
                  AND ($4::text IS NULL OR task_id = $4)
                ORDER BY created_at DESC
                """,
                user_id,
                agent_id,
                status,
                task_id
            )
            results = []
            for row in rows:
                data = dict(row)
                if isinstance(data.get("metadata"), str):
                    data["metadata"] = json.loads(data["metadata"])
                results.append(AgentExecutionEntry(**data))
            return results
        finally:
            await self.db.release_conn(conn)

    async def save_decision(self, entry: AgentDecisionEntry, user_id: str) -> AgentDecisionEntry:
        if not self.has_pool:
            raise RuntimeError("Database pool not initialized")
        conn = await self.db.get_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO agent_decisions (execution_id, agent_id, decision, reasoning, outcome, user_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, execution_id, agent_id, decision, reasoning, outcome, created_at
                """,
                entry.execution_id,
                entry.agent_id,
                entry.decision,
                entry.reasoning,
                entry.outcome,
                user_id
            )
            return AgentDecisionEntry(**dict(row))
        finally:
            await self.db.release_conn(conn)

    async def get_decisions(
        self,
        user_id: str,
        execution_id: Optional[UUID] = None,
        agent_id: Optional[str] = None
    ) -> List[AgentDecisionEntry]:
        if not self.has_pool:
            return []
        conn = await self.db.get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, execution_id, agent_id, decision, reasoning, outcome, created_at FROM agent_decisions
                WHERE user_id = $1
                  AND ($2::uuid IS NULL OR execution_id = $2)
                  AND ($3::text IS NULL OR agent_id = $3)
                ORDER BY created_at DESC
                """,
                user_id,
                execution_id,
                agent_id
            )
            return [AgentDecisionEntry(**dict(row)) for row in rows]
        finally:
            await self.db.release_conn(conn)

    async def semantic_search_memories(
        self,
        query: str,
        user_id: str,
        agent_id: Optional[str] = None,
        limit: int = 5
    ) -> List[tuple[AgentMemoryEntry, float]]:
        if not self.has_pool:
            return []
        
        # Generate query embedding
        query_vector = await memory_embedding_service.generate_query_embedding(query)
        
        conn = await self.db.get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, agent_id, context, summary, learned_info, tags, embedding, created_at,
                       1 - (embedding <=> $1::vector) AS similarity_score
                FROM agent_memories
                WHERE user_id = $2
                  AND ($3::text IS NULL OR agent_id = $3)
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector ASC
                LIMIT $4
                """,
                _vector_literal(query_vector),
                user_id,
                agent_id,
                limit
            )
            results = []
            for row in rows:
                data = dict(row)
                score = float(data.pop("similarity_score"))
                if data.get("embedding") is not None:
                    from context_system.db import _parse_vector
                    data["embedding"] = _parse_vector(data["embedding"])
                results.append((AgentMemoryEntry(**data), score))
            return results
        finally:
            await self.db.release_conn(conn)

    async def get_historical_context(
        self,
        user_id: str,
        agent_id: str,
        task: str,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Retrieves relevant historical executions, memories, and decisions to assist
        the agent in learning from prior runs.
        """
        # Fetch relevant memories by tags/metadata
        memories = await self.get_memories(user_id=user_id, agent_id=agent_id, tags=tags)
        
        # ALSO fetch memories via semantic similarity lookup on the task
        semantic_results = await self.semantic_search_memories(
            task,
            user_id=user_id,
            agent_id=agent_id,
            limit=5
        )
        semantic_memories = [m for m, score in semantic_results]
        
        # Combine and deduplicate memories by ID
        combined_memories = {m.id: m for m in memories if m.id is not None}
        for sm in semantic_memories:
            if sm.id is not None:
                combined_memories[sm.id] = sm
        
        # Fetch successful past executions for this agent
        executions = await self.get_executions(
            user_id=user_id,
            agent_id=agent_id,
            status="success",
            task_id=task
        )
        
        # If no executions directly matching task, retrieve successful ones for agent in general
        if not executions:
            executions = await self.get_executions(user_id=user_id, agent_id=agent_id, status="success")
            # Limit to top 5 recent successful runs
            executions = executions[:5]

        # Retrieve decisions linked to these executions
        decisions = []
        if executions:
            exec_ids = [e.id for e in executions if e.id is not None]
            if exec_ids:
                conn = await self.db.get_conn()
                try:
                    rows = await conn.fetch(
                        """
                        SELECT id, execution_id, agent_id, decision, reasoning, outcome, created_at FROM agent_decisions
                        WHERE user_id = $1
                          AND execution_id = ANY($2::uuid[])
                        ORDER BY created_at DESC
                        """,
                        user_id,
                        exec_ids
                    )
                    decisions = [AgentDecisionEntry(**dict(row)) for row in rows]
                finally:
                    await self.db.release_conn(conn)

        return {
            "memories": list(combined_memories.values()),
            "executions": executions,
            "decisions": decisions
        }


# Global singleton instance
memory_service = AgentMemoryService()

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from db.database import database
from context_system.semantic_searcher import embedding_provider

logger = logging.getLogger(__name__)


def _vector_literal(values: list[float]) -> str:
    """Formats a list of floats into a pgvector-compatible string literal."""
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


class KnowledgeService:
    """
    Phase 1: Knowledge & Learning Infrastructure Service.
    Handles shared knowledge synchronization, semantic retrieval,
    long-term agent memory, and execution history retrieval.
    """

    def __init__(self, db=database):
        self.db = db

    async def _resolve_agent_id(self, conn, agent_name_or_id: str) -> str | None:
        """Resolves an agent name (e.g. 'fastapi') or string ID to a UUID string."""
        if not agent_name_or_id:
            return None
        try:
            uuid.UUID(agent_name_or_id)
            return agent_name_or_id
        except ValueError:
            pass

        # Try exact mapping/matching or fallback pattern
        query = """
        SELECT id FROM agents 
        WHERE LOWER(name) = LOWER($1) 
           OR LOWER(name) LIKE LOWER($2)
        LIMIT 1
        """
        row = await conn.fetchrow(query, agent_name_or_id, f"%{agent_name_or_id}%")
        if row:
            return str(row["id"])
        return None

    def chunk_text(self, text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
        """Splits raw text into sliding window chunks of max_chars length."""
        if not text:
            return []
        if len(text) <= max_chars:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            if len(text) - start <= overlap and chunks:
                break
            end = start + max_chars
            chunks.append(text[start:end])
            start += max_chars - overlap
        return chunks

    async def sync_agent_knowledge(
        self,
        agent_name_or_id: str,
        source_id: str | None,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Ingests and chunks a documentation source, embeds each chunk,
        and saves it to the agent_knowledge table.
        """
        conn = await self.db.get_conn()
        try:
            agent_id = await self._resolve_agent_id(conn, agent_name_or_id)
            if not agent_id:
                raise ValueError(f"Could not resolve agent for identifier: {agent_name_or_id}")

            chunks = self.chunk_text(content)
            if not chunks:
                return

            metadata = metadata or {}
            
            async with conn.transaction():
                for chunk in chunks:
                    # Generate stable hash to prevent duplicate chunks per agent
                    chunk_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
                    embedding = await embedding_provider.encode(chunk)
                    
                    await conn.execute(
                        """
                        INSERT INTO agent_knowledge (
                            agent_id, source_id, source_type, content, content_hash, embedding, metadata
                        )
                        VALUES ($1, $2, 'sync_source', $3, $4, $5::vector, $6)
                        ON CONFLICT (agent_id, content_hash)
                        DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            created_at = NOW()
                        """,
                        agent_id,
                        uuid.UUID(source_id) if source_id else None,
                        chunk,
                        chunk_hash,
                        _vector_literal(embedding),
                        json.dumps(metadata),
                    )

                # Update timestamp metadata
                await conn.execute(
                    "UPDATE agents SET last_kb_update = NOW() WHERE id = $1",
                    uuid.UUID(agent_id),
                )
                if source_id:
                    await conn.execute(
                        "UPDATE agent_sources SET last_scraped_at = NOW() WHERE id = $1",
                        uuid.UUID(source_id),
                    )
        finally:
            await self.db.release_conn(conn)

    async def retrieve_knowledge(
        self,
        agent_name_or_id: str,
        query_text: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Performs semantic similarity search over indexed agent knowledge sources."""
        conn = await self.db.get_conn()
        try:
            agent_id = await self._resolve_agent_id(conn, agent_name_or_id)
            if not agent_id:
                return []

            query_embedding = await embedding_provider.encode(query_text)
            
            rows = await conn.fetch(
                """
                SELECT content, metadata, 1 - (embedding <=> $2::vector) AS similarity
                FROM agent_knowledge
                WHERE agent_id = $1 AND source_type = 'sync_source'
                ORDER BY embedding <=> $2::vector
                LIMIT $3
                """,
                uuid.UUID(agent_id),
                _vector_literal(query_embedding),
                limit,
            )
            return [dict(row) for row in rows]
        finally:
            await self.db.release_conn(conn)

    async def record_agent_memory(
        self,
        agent_name_or_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> None:
        """Saves a self-generated agent memory/reflection to the agent_knowledge table."""
        if not user_id:
            return
        conn = await self.db.get_conn()
        try:
            agent_id = await self._resolve_agent_id(conn, agent_name_or_id)
            if not agent_id:
                raise ValueError(f"Could not resolve agent for identifier: {agent_name_or_id}")

            memory_hash = hashlib.sha256(f"{user_id}:{content}".encode("utf-8")).hexdigest()
            embedding = await embedding_provider.encode(content)
            metadata = metadata or {}

            await conn.execute(
                """
                INSERT INTO agent_knowledge (
                    agent_id, source_type, content, content_hash, embedding, metadata, user_id
                )
                VALUES ($1, 'long_term_memory', $2, $3, $4::vector, $5, $6)
                ON CONFLICT (agent_id, content_hash)
                DO UPDATE SET
                    metadata = EXCLUDED.metadata,
                    user_id = EXCLUDED.user_id,
                    created_at = NOW()
                """,
                uuid.UUID(agent_id),
                content,
                memory_hash,
                _vector_literal(embedding),
                json.dumps(metadata),
                user_id,
            )
        finally:
            await self.db.release_conn(conn)

    async def retrieve_agent_memories(
        self,
        agent_name_or_id: str,
        query_text: str,
        limit: int = 3,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieves semantically similar long-term memories/reflections for an agent."""
        if not user_id:
            return []
        conn = await self.db.get_conn()
        try:
            agent_id = await self._resolve_agent_id(conn, agent_name_or_id)
            if not agent_id:
                return []

            query_embedding = await embedding_provider.encode(query_text)

            rows = await conn.fetch(
                """
                SELECT content, metadata, 1 - (embedding <=> $2::vector) AS similarity
                FROM agent_knowledge
                WHERE agent_id = $1
                  AND source_type = 'long_term_memory'
                  AND user_id = $4
                ORDER BY embedding <=> $2::vector
                LIMIT $3
                """,
                uuid.UUID(agent_id),
                _vector_literal(query_embedding),
                limit,
                user_id,
            )
            return [dict(row) for row in rows]
        finally:
            await self.db.release_conn(conn)

    async def retrieve_execution_history(
        self,
        agent_name: str,
        chat_session_id: str,
        limit: int = 2,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieves successful outputs/results from previous runs of this agent
        belonging to the same project.
        """
        if not chat_session_id or not user_id:
            return []
        conn = await self.db.get_conn()
        try:
            # 1. Fetch project ID for the active chat session
            session_row = await conn.fetchrow(
                """
                SELECT cs.project_id
                FROM chat_sessions cs
                INNER JOIN projects p ON p.id = cs.project_id
                WHERE cs.id = $1 AND p.user_id = $2
                """,
                uuid.UUID(chat_session_id),
                user_id,
            )
            if not session_row:
                return []
            project_id = session_row["project_id"]

            # 2. Retrieve execution records matching same project and agent key
            rows = await conn.fetch(
                """
                SELECT r.agent_id, r.output_json, r.score, r.created_at
                FROM pipeline_agent_results r
                WHERE r.agent_id = $1
                  AND r.status = 'success'
                  AND r.user_id = $4
                  AND r.run_id IN (
                    SELECT id::text FROM chat_sessions WHERE project_id = $2
                )
                ORDER BY r.created_at DESC
                LIMIT $3
                """,
                agent_name,
                project_id,
                limit,
                user_id,
            )
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.warning("Failed to retrieve execution history: %s", exc)
            return []
        finally:
            await self.db.release_conn(conn)

    async def record_agent_run(
        self,
        agent_name: str,
        chat_session_id: str,
        output: str,
        user_id: str | None = None,
    ) -> None:
        """
        Saves the successful execution run of an agent under a chat session,
        ensuring a valid execution plan reference exists.
        Runs inside an atomic transaction block.
        """
        if not chat_session_id or not output or not user_id:
            return
        conn = await self.db.get_conn()
        try:
            # 1. Retrieve session title for task label
            session_row = await conn.fetchrow(
                """
                SELECT cs.title
                FROM chat_sessions cs
                INNER JOIN projects p ON p.id = cs.project_id
                WHERE cs.id = $1 AND p.user_id = $2
                """,
                uuid.UUID(chat_session_id),
                user_id,
            )
            if not session_row:
                return
            task_label = session_row["title"] if session_row else "Developer Workspace Task"

            async with conn.transaction():
                # 2. Ensure pipeline execution plan reference exists for run_id
                await conn.execute(
                    """
                    INSERT INTO pipeline_execution_plans (run_id, task, plan_json, status, user_id)
                    VALUES ($1, $2, '{}'::jsonb, 'success', $3)
                    ON CONFLICT (run_id) DO UPDATE SET updated_at = NOW(), user_id = EXCLUDED.user_id
                    """,
                    chat_session_id,
                    task_label,
                    user_id,
                )

                # 3. Insert results output JSON mapping
                output_payload = {"output": output}
                await conn.execute(
                    """
                    INSERT INTO pipeline_agent_results (run_id, agent_id, status, output_json, score, attempt_count, user_id)
                    VALUES ($1, $2, 'success', $3::jsonb, 1.0, 1, $4)
                    """,
                    chat_session_id,
                    agent_name,
                    json.dumps(output_payload),
                    user_id,
                )
        except Exception as exc:
            logger.warning("Failed to record agent execution run: %s", exc)
            raise exc
        finally:
            await self.db.release_conn(conn)

    async def after_agent_execution(
        self,
        agent_name: str,
        chat_session_id: str,
        task: str,
        output: str,
        user_id: str | None = None,
    ) -> None:
        """
        Processes callbacks after a successful agent execution:
        records the execution output and saves task learning summary to long-term memory.
        """
        await self.record_agent_run(agent_name, chat_session_id, output, user_id=user_id)
        
        learning_text = f"Successfully completed task: '{task}'. Key deliverables: generated/modified file structures."
        await self.record_agent_memory(
            agent_name_or_id=agent_name,
            content=learning_text,
            metadata={"task": task, "session_id": chat_session_id},
            user_id=user_id,
        )

    async def prepare_agent_context(
        self,
        agent_name: str,
        chat_session_id: str,
        task: str,
        user_id: str | None = None,
    ) -> str:
        """
        Prepares and formats semantic knowledge, memories, and execution history
        into a markdown block context, respecting strict length budget rules.
        """
        if not agent_name:
            return ""

        conn = await self.db.get_conn()
        agent_id = None
        try:
            agent_id = await self._resolve_agent_id(conn, agent_name)
        except Exception as e:
            logger.warning("Failed to resolve agent ID: %s", e)
        finally:
            await self.db.release_conn(conn)

        # Run all retrieval operations in parallel
        knowledge_task = self.retrieve_knowledge(agent_name, task, limit=2)
        memory_task = self.retrieve_agent_memories(agent_name, task, limit=2, user_id=user_id)
        history_task = self.retrieve_execution_history(agent_name, chat_session_id, limit=2, user_id=user_id)

        knowledge_items, memory_items, history_items = await asyncio.gather(
            knowledge_task, memory_task, history_task, return_exceptions=True
        )

        # Fetch Phase 2 context (memories, executions, decisions)
        new_memories = []
        new_executions = []
        new_decisions = []
        if agent_id and user_id:
            try:
                from knowledge.memory_service import memory_service
                context_data = await memory_service.get_historical_context(user_id, agent_id, task)
                new_memories = context_data.get("memories", [])
                new_executions = context_data.get("executions", [])
                new_decisions = context_data.get("decisions", [])
            except Exception as e:
                logger.warning("Failed to retrieve Phase 2 historical context: %s", e)

        # Fetch relevant shared project knowledge semantically matching the task
        shared_knowledge_items = []
        try:
            from knowledge.sync_manager import sync_manager
            if user_id:
                # Fetch up to 3 relevant user-owned shared knowledge entries.
                shared_results = await sync_manager.semantic_search_shared_knowledge(task, user_id=user_id, limit=3)
                shared_knowledge_items = [entry for entry, score in shared_results]
        except Exception as se:
            logger.warning("Failed to retrieve shared knowledge for context: %s", se)

        # Budgeting control
        max_total_chars = 3000
        total_chars = 0
        sections = []

        # 0. Format Shared Project Knowledge (800 chars cap)
        if shared_knowledge_items:
            shared_parts = []
            for idx, item in enumerate(shared_knowledge_items):
                content = item.content[:800]
                shared_parts.append(f"- Shared Info {idx + 1} (Source: {item.source_agent}): {content}")
            shared_text = "## Shared Project Understanding & Global Knowledge:\n" + "\n".join(shared_parts)
            if len(shared_text) <= max_total_chars:
                sections.append(shared_text)
                total_chars += len(shared_text)


        # 1. Format Ingested Knowledge Base Chunks (800 chars cap)
        if isinstance(knowledge_items, list) and knowledge_items:
            kb_parts = []
            for idx, item in enumerate(knowledge_items):
                content = item['content'][:800]
                kb_parts.append(f"--- Document Chunk {idx + 1} ---\n{content}")
            kb_text = "## Relevant Documentation:\n" + "\n\n".join(kb_parts)
            if len(kb_text) <= max_total_chars:
                sections.append(kb_text)
                total_chars += len(kb_text)

        # 2. Format Prior Agent Reflections/Memories (500 chars cap)
        if isinstance(memory_items, list) and memory_items:
            mem_parts = []
            for idx, item in enumerate(memory_items):
                content = item['content'][:500]
                mem_parts.append(f"- Memory {idx + 1}: {content}")
            mem_text = "## Long-Term Learnings & Reflections:\n" + "\n".join(mem_parts)
            if total_chars + len(mem_text) <= max_total_chars:
                sections.append(mem_text)
                total_chars += len(mem_text)

        # 2.5 Format Phase 2 Permanent Agent Memories (500 chars cap)
        if new_memories:
            new_mem_parts = []
            for idx, m in enumerate(new_memories[:3]):
                content = m.learned_info[:500]
                new_mem_parts.append(f"- Memory {idx + 1} (Context: {m.context}): {content}")
            new_mem_text = "## Permanent Agent Memories:\n" + "\n".join(new_mem_parts)
            if total_chars + len(new_mem_text) <= max_total_chars:
                sections.append(new_mem_text)
                total_chars += len(new_mem_text)

        # 3. Format Historical Execution Outputs (1200 chars cap)
        if total_chars < max_total_chars and isinstance(history_items, list) and history_items:
            hist_parts = []
            for idx, item in enumerate(history_items):
                out_json = item.get("output_json") or {}
                if isinstance(out_json, str):
                    try:
                        out_json = json.loads(out_json)
                    except Exception:
                        out_json = {}
                raw_out = (out_json.get("output") or "")[:1200]
                if raw_out:
                    hist_parts.append(
                        f"--- Past Output {idx + 1} (Date: {item.get('created_at')}) ---\n{raw_out}"
                    )
            if hist_parts:
                hist_text = "## Successful Prior Outputs:\n" + "\n\n".join(hist_parts)
                if total_chars + len(hist_text) <= max_total_chars:
                    sections.append(hist_text)
                    total_chars += len(hist_text)

        # 3.5 Format Phase 2 Historical Executions and Decisions (800 chars cap)
        if total_chars < max_total_chars and (new_executions or new_decisions):
            exec_desc_parts = []
            if new_executions:
                exec_desc_parts.append("## Past Executions:")
                for idx, e in enumerate(new_executions[:2]):
                    exec_desc_parts.append(f"- Task: '{e.task_id}' (Status: {e.status})")
            if new_decisions:
                exec_desc_parts.append("## Past Decisions & Outcomes:")
                for idx, d in enumerate(new_decisions[:2]):
                    exec_desc_parts.append(f"- Decision: {d.decision}\n  Reasoning: {d.reasoning}\n  Outcome: {d.outcome}")
            
            exec_desc_text = "\n".join(exec_desc_parts)
            if total_chars + len(exec_desc_text) <= max_total_chars:
                sections.append(exec_desc_text)
                total_chars += len(exec_desc_text)

        if not sections:
            return ""

        return "\n\n# Prior Ingested Context & Agent Learnings:\n" + "\n\n".join(sections)


import asyncio
knowledge_service = KnowledgeService()

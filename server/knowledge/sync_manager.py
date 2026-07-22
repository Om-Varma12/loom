import logging
from typing import Any, Dict, List
from knowledge.schema import KnowledgeEntry
from knowledge.store import KnowledgeStore
from knowledge.conflict_resolver import ConflictResolver
from knowledge.propagator import KnowledgePropagator

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self, store: KnowledgeStore = None, resolver: ConflictResolver = None, propagator: KnowledgePropagator = None):
        self.store = store or KnowledgeStore()
        self.resolver = resolver or ConflictResolver()
        self.propagator = propagator or KnowledgePropagator()

    async def add_knowledge(self, entry_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        Executes the Sync Flow Pipeline:
        Schema Validation -> Conflict Check -> Version Resolution -> Store in DB -> Propagate -> Log
        """
        # 1. Schema Validation
        try:
            incoming = KnowledgeEntry(**entry_data)
        except Exception as e:
            logger.warning("[SyncManager] Validation failed: %s for data %s", e, entry_data)
            return {
                "success": False,
                "reason": f"validation error: {str(e)}",
                "action": "rejected"
            }

        # Generate embedding if missing
        if incoming.embedding is None:
            try:
                from knowledge.memory_embedding_service import memory_embedding_service
                incoming.embedding = await memory_embedding_service.generate_query_embedding(incoming.content)
            except Exception as e:
                logger.warning("[SyncManager] Failed to generate embedding: %s", e)

        # 2. Retrieve existing & Resolve Conflicts
        existing = await self.store.get_entry(incoming.id, user_id)
        should_write, action = self.resolver.resolve(incoming, existing)

        if not should_write:
            return {
                "success": False,
                "reason": "conflict check: version or timestamp is outdated",
                "action": "rejected"
            }

        # 3. Store in DB
        try:
            await self.store.save_entry(incoming, user_id)
        except PermissionError as exc:
            return {
                "success": False,
                "reason": str(exc),
                "action": "rejected",
            }

        # 4. Propagate Update
        await self.propagator.propagate(incoming)

        # 5. Return success PASS Response
        return {
            "success": True,
            "action": action,
            "version": incoming.version
        }

    async def get_all(self, user_id: str) -> List[KnowledgeEntry]:
        """Gets all entries via cached read."""
        return await self.propagator.get_cached_all(user_id, self.store.get_all_entries)

    async def get_by_tag(self, tag: str, user_id: str) -> List[KnowledgeEntry]:
        """Gets tag filtered entries via cached read."""
        return await self.propagator.get_cached_tag(tag, user_id, self.store.get_entries_by_tag)

    async def semantic_search_shared_knowledge(
        self, query: str, user_id: str, limit: int = 5
    ) -> List[tuple[KnowledgeEntry, float]]:
        """Performs semantic search over the shared_knowledge table."""
        if not self.store.has_pool:
            return []
        
        # Generate query embedding
        from knowledge.memory_embedding_service import memory_embedding_service
        query_vector = await memory_embedding_service.generate_query_embedding(query)
        
        from knowledge.memory_service import _vector_literal
        conn = await self.store.db.get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, content, version, timestamp, source_agent, priority, tags, embedding,
                       1 - (embedding <=> $1::vector) AS similarity_score
                FROM shared_knowledge
                WHERE embedding IS NOT NULL
                  AND user_id = $2
                ORDER BY embedding <=> $1::vector ASC
                LIMIT $3
                """,
                _vector_literal(query_vector),
                user_id,
                limit
            )
            results = []
            for row in rows:
                data = dict(row)
                score = float(data.pop("similarity_score"))
                if data.get("embedding") is not None:
                    from context_system.db import _parse_vector
                    data["embedding"] = _parse_vector(data["embedding"])
                results.append((KnowledgeEntry(**data), score))
            return results
        finally:
            await self.store.db.release_conn(conn)


# Global singleton sync manager
sync_manager = SyncManager()

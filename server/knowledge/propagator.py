import logging
from typing import Callable, Dict, List, Optional
from knowledge.schema import KnowledgeEntry

logger = logging.getLogger(__name__)

class KnowledgePropagator:
    def __init__(self):
        self._listeners: List[Callable[[KnowledgeEntry], None]] = []
        self._cache_all: Dict[str, List[KnowledgeEntry]] = {}
        self._cache_tags: Dict[tuple[str, str], List[KnowledgeEntry]] = {}

    def register_listener(self, callback: Callable[[KnowledgeEntry], None]) -> None:
        """Register a callback to be notified when knowledge is updated."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[KnowledgeEntry], None]) -> None:
        """Unregister a notification callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def get_cached_all(self, user_id: str, fetch_func) -> List[KnowledgeEntry]:
        """Get all entries, using cache if available."""
        if user_id not in self._cache_all:
            logger.debug("[Propagator] Cache miss for get_all_entries, fetching from store")
            self._cache_all[user_id] = await fetch_func(user_id)
        else:
            logger.debug("[Propagator] Cache hit for get_all_entries")
        return self._cache_all[user_id]

    async def get_cached_tag(self, tag: str, user_id: str, fetch_func) -> List[KnowledgeEntry]:
        """Get entries filtered by tag, using cache if available."""
        cache_key = (user_id, tag)
        if cache_key not in self._cache_tags:
            logger.debug("[Propagator] Cache miss for tag '%s', fetching from store", tag)
            self._cache_tags[cache_key] = await fetch_func(tag, user_id)
        else:
            logger.debug("[Propagator] Cache hit for tag '%s'", tag)
        return self._cache_tags[cache_key]

    def invalidate_cache(self) -> None:
        """Clear all in-memory caches."""
        logger.debug("[Propagator] Invalidating all shared knowledge caches")
        self._cache_all.clear()
        self._cache_tags.clear()

    async def propagate(self, entry: KnowledgeEntry) -> None:
        """Invalidates caches and notifies all registered listeners of the new/updated entry."""
        self.invalidate_cache()
        logger.info("[Propagator] Propagating update for ID '%s' to %d listeners", entry.id, len(self._listeners))
        for listener in self._listeners:
            try:
                # Call callback
                if hasattr(listener, "__code__") and listener.__code__.co_flags & 0x80: # async function check
                    import asyncio
                    asyncio.create_task(listener(entry))
                else:
                    listener(entry)
            except Exception as e:
                logger.error("[Propagator] Failed to notify listener: %s", e)

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any, Dict, List
from knowledge.sync_manager import sync_manager
from knowledge.schema import KnowledgeEntry
from dependencies.auth_dep import CurrentUser, get_current_user

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(get_current_user)],
)

@router.post("/add")
async def add_knowledge(
    entry: Dict[str, Any],
    current_user: CurrentUser = Depends(get_current_user)
):
    res = await sync_manager.add_knowledge(entry, current_user.id)
    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res
        )
    return res

@router.get("/get", response_model=List[KnowledgeEntry])
async def get_knowledge(current_user: CurrentUser = Depends(get_current_user)):
    return await sync_manager.get_all(current_user.id)

@router.get("/tags/{tag}", response_model=List[KnowledgeEntry])
async def get_knowledge_by_tag(
    tag: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    return await sync_manager.get_by_tag(tag, current_user.id)

@router.post("/sources/add")
async def add_agent_source(payload: Dict[str, Any]):
    agent_id = payload.get("agent_id")
    url = payload.get("url")
    source_type = payload.get("source_type", "website")
    
    if not agent_id or not url:
        raise HTTPException(status_code=400, detail="agent_id and url are required")
        
    from db.database import database
    conn = await database.get_conn()
    try:
        # Check if agent exists by ID or name
        agent = await conn.fetchrow(
            "SELECT id FROM agents WHERE id = $1::uuid OR LOWER(name) = LOWER($2)", 
            agent_id if len(agent_id) == 36 else None,
            agent_id
        )
        if not agent:
            from knowledge.memory_service import memory_service
            resolved = await memory_service.resolve_agent_id(agent_id)
            if resolved:
                agent_id = resolved
            else:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        else:
            agent_id = str(agent["id"])
            
        row = await conn.fetchrow(
            """
            INSERT INTO agent_sources (agent_id, url, source_type, is_active, last_scraped_at)
            VALUES ($1::uuid, $2, $3, TRUE, NULL)
            RETURNING id, agent_id, url, source_type, is_active, last_scraped_at
            """,
            agent_id,
            url,
            source_type
        )
        return dict(row)
    finally:
        await database.release_conn(conn)

@router.get("/sources")
async def get_agent_sources():
    from db.database import database
    conn = await database.get_conn()
    try:
        rows = await conn.fetch(
            "SELECT id, agent_id, url, source_type, is_active, last_scraped_at FROM agent_sources"
        )
        return [dict(row) for row in rows]
    finally:
        await database.release_conn(conn)

@router.post("/sources/refresh")
async def refresh_sources():
    from knowledge.update_pipeline import update_pipeline
    return await update_pipeline.run_refresh_cycle()

@router.get("/search")
async def search_shared_knowledge(
    query: str = Query(...),
    limit: int = Query(5),
    current_user: CurrentUser = Depends(get_current_user)
):
    try:
        results = await sync_manager.semantic_search_shared_knowledge(
            query,
            current_user.id,
            limit
        )
        return [
            {
                "entry": entry,
                "similarity_score": score
            }
            for entry, score in results
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Shared knowledge semantic search failed: {e}"
        )

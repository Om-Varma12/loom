from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket, WebSocketDisconnect

from context_system.models import (
    ContextAnalyzeRequest,
    ContextIndexRequest,
    ContextPayload,
    ContextStatus,
    PartitionRequest,
    SubgraphAssignment,
)
from context_system.repo_watcher import repo_watcher_manager
from context_system.service import context_system
from dependencies.auth_dep import get_current_user, verify_clerk_token


router = APIRouter(
    prefix="/context",
    tags=["Context"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/analyze", response_model=ContextPayload)
async def analyze_context(request: ContextAnalyzeRequest):
    try:
        return await context_system.analyze(
            request.repo_path,
            request.prompt,
            request.task_id,
            token_budget=request.token_budget,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Context analysis failed: {exc}") from exc


@router.post("/index")
async def index_context(request: ContextIndexRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(context_system.index_repo, request.repo_path)
    return {"status": "scheduled", "repo_path": request.repo_path}


@router.get("/status/{repo_path:path}", response_model=ContextStatus)
async def context_status(repo_path: str):
    try:
        return await context_system.status(repo_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Context status failed: {exc}") from exc


@router.websocket("/watch")
async def watch_context(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        verify_clerk_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        first_message = await websocket.receive_json()
        repo_path = first_message.get("repo_path")
        if not repo_path:
            await websocket.send_json({"type": "error", "message": "repo_path is required"})
            await websocket.close(code=1008)
            return
        await repo_watcher_manager.watch(repo_path)
        await websocket.send_json({"type": "watching", "repo_path": repo_path})
        while True:
            event = await repo_watcher_manager.events.get()
            if event.repo_path == repo_path:
                await websocket.send_json(event.model_dump())
    except WebSocketDisconnect:
        return


@router.post("/partition", response_model=list[SubgraphAssignment])
async def partition_context(request: PartitionRequest):
    try:
        return await context_system.partition(request.repo_path, request.prompt, request.agents)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Context partition failed: {exc}") from exc

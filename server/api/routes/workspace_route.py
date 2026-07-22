from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response

from db.schema.workspace import FileTreeNode, FileContentResponse, SaveFileRequest
from dependencies.auth_dep import CurrentUser, get_current_user
from dependencies.project_dep import project_service
from dependencies.workspace_dep import workspace_service

router = APIRouter(
    prefix="/workspace",
    tags=["Workspace"]
)

@router.get("/{project_id}/tree", response_model=list[FileTreeNode])
async def get_workspace_tree(
    project_id: UUID,
    current_user: CurrentUser = Depends(get_current_user)
):
    project = await project_service.get_project(str(project_id), current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return workspace_service.get_tree(project["name"])

@router.get("/{project_id}/file", response_model=FileContentResponse)
async def get_workspace_file(
    project_id: UUID,
    path: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    project = await project_service.get_project(str(project_id), current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        content = workspace_service.read_file(project["name"], path)
        return FileContentResponse(path=path, content=content)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{project_id}/file")
async def save_workspace_file(
    project_id: UUID,
    request: SaveFileRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    project = await project_service.get_project(str(project_id), current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        workspace_service.save_file(project["name"], request.path, request.content)
        return {"status": "success", "message": f"File '{request.path}' saved successfully."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{project_id}/download")
async def download_workspace(
    project_id: UUID,
    current_user: CurrentUser = Depends(get_current_user)
):
    project = await project_service.get_project(str(project_id), current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        zip_bytes = workspace_service.download_zip(project["name"])
        headers = {
            "Content-Disposition": f'attachment; filename="{project["name"]}_workspace.zip"'
        }
        return Response(content=zip_bytes, media_type="application/zip", headers=headers)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

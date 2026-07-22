from fastapi import APIRouter

from api.routes.project_route import router as project_router
from api.routes.agent_route import router as agent_router
from api.routes.chat_route import router as chat_router
from api.routes.workspace_route import router as workspace_router
from api.routes.context_route import router as context_router
from api.routes.orchestration_route import router as orchestration_router
from api.routes.shared_knowledge_route import router as shared_knowledge_router
from api.routes.agent_memory_route import router as agent_memory_router
from api.routes.audit_route import router as audit_router
from api.routes.theme_route import router as theme_router
from api.routes.auth_route import router as auth_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(project_router)
router.include_router(agent_router)
router.include_router(chat_router)
router.include_router(workspace_router)
router.include_router(context_router)
router.include_router(orchestration_router)
router.include_router(shared_knowledge_router)
router.include_router(agent_memory_router)
router.include_router(audit_router)
router.include_router(theme_router)

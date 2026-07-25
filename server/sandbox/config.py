import os

DOCKER_IMAGE = "omvarma12/agent-sandbox-base:v2"
WORKSPACE_PATH_IN_CONTAINER = "/workspace"
# Using a local workspace inside the server folder for easier local development
HOST_PROJECTS_ROOT = os.environ.get("PROJECTS_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspaces")))

# Resource limits — keep these tight, this runs LLM-generated code
MEM_LIMIT = "512m"
CPU_QUOTA = 0.5          # half a core
CONTAINER_IDLE_TIMEOUT_SECONDS = 30 * 60   # auto-pause after 30 min idle
PREVIEW_PORT_RANGE = (8600, 8700)          # host ports mapped to container's 8501
COMMAND_TIMEOUT_SECONDS = 20               # kill any exec that runs longer than this

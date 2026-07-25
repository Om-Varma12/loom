import docker
import os
import time
import asyncio
from typing import Dict
from . import config

try:
    client = docker.from_env()
except Exception as e:
    # Just in case docker is not available during import, it can be handled later
    client = None

# In-memory store for tracking last_active timestamp per project
_last_active_tracker: Dict[str, float] = {}

class SandboxManager:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                self._client = docker.from_env()
            except Exception as e:
                raise RuntimeError(f"Docker client is not available: {str(e)}")
        return self._client

    def _container_name(self, project_id: str) -> str:
        return f"sandbox-{project_id}"

    def get_or_create(self, project_id: str):
        name = self._container_name(project_id)
        try:
            container = self.client.containers.get(name)

            print(f"\n[SANDBOX] Reusing {container.name}")
            print(f"ID      : {container.id}")
            print(f"Status  : {container.status}")

            if container.status != "running":
                print("[SANDBOX] Starting stopped container")
                container.start()

            container.reload()
            print(f"Mounts  : {container.attrs['Mounts']}")

            self.touch(project_id)
            return container

        except docker.errors.NotFound:
            print("\n[SANDBOX] Creating NEW container")


        host_path = f"{config.HOST_PROJECTS_ROOT}/{project_id}"
        os.makedirs(host_path, exist_ok=True)

        print("\n========== SANDBOX CREATE ==========")
        print(f"Project ID : {project_id}")
        print(f"Image      : {config.DOCKER_IMAGE}")
        print(f"Host Path  : {host_path}")
        print(f"Exists     : {os.path.exists(host_path)}")
        print(f"Container  : sandbox-{project_id}")
        print("====================================")

        container = self.client.containers.run(
            config.DOCKER_IMAGE,
            name=name,
            detach=True,
            tty=True,
            command="sleep infinity",       # keep alive; we exec into it for real work
            working_dir=config.WORKSPACE_PATH_IN_CONTAINER,
            volumes={host_path: {"bind": config.WORKSPACE_PATH_IN_CONTAINER, "mode": "rw"}},
            mem_limit=config.MEM_LIMIT,
            nano_cpus=int(config.CPU_QUOTA * 1e9),
            network_mode="none",
            labels={"project_id": project_id},
        )
        
        self.touch(project_id)
        
        container.reload()

        print("\n========== CONTAINER INFO ==========")
        print(f"ID         : {container.id}")
        print(f"Status     : {container.status}")
        print(f"Mounts     : {container.attrs['Mounts']}")
        print("====================================")
        
        
        import json

        print("\n========== MOUNTS ==========")
        print(json.dumps(container.attrs["Mounts"], indent=2))
        print("============================")
        
        
        return container

    def touch(self, project_id: str):
        """Update last-active timestamp."""
        _last_active_tracker[project_id] = time.time()

    def exec_run(self, project_id: str, cmd: list[str], timeout: int = None):
        container = self.get_or_create(project_id)
        self.touch(project_id)
        
        # We can implement a timeout via docker exec if supported, 
        # but docker-py exec_run does not have a native timeout parameter for the call itself in blocking mode.
        # We could use a thread/process or an async approach, but for MVP we will rely on blocking.
        # Another option is running `timeout {CMD_TIMEOUT} cmd...` in the shell inside.
        
        if timeout is None:
            timeout = config.COMMAND_TIMEOUT_SECONDS
            
        # Wrap cmd in timeout inside the container
        if isinstance(cmd, list):
            # If it's a list like ["grep", "foo"], wrap it
            cmd = ["timeout", str(timeout)] + cmd
        elif isinstance(cmd, str):
            cmd = f"timeout {timeout} {cmd}"

        print("\n========== EXEC ==========")
        print(f"Container : {container.name}")
        print(f"Command   : {cmd}")
        print("==========================")

        result = container.exec_run(
            cmd,
            workdir=config.WORKSPACE_PATH_IN_CONTAINER,
            demux=True
        )

        stdout, stderr = result.output

        print(f"Exit Code : {result.exit_code}")

        if stdout:
            print("\n----- STDOUT -----")
            print(stdout.decode("utf-8", errors="replace"))

        if stderr:
            print("\n----- STDERR -----")
            print(stderr.decode("utf-8", errors="replace"))

        # Show what files currently exist inside the sandbox
        verify = container.exec_run(
            ["find", ".", "-type", "f"],
            workdir=config.WORKSPACE_PATH_IN_CONTAINER
        )

        print("\n----- FILES IN SANDBOX -----")
        print(verify.output.decode("utf-8", errors="replace"))
        print("============================")

        return {
            "exit_code": result.exit_code,
            "stdout": (stdout or b"").decode("utf-8", errors="replace"),
            "stderr": (stderr or b"").decode("utf-8", errors="replace"),
        }
        
        
    def stop(self, project_id: str):
        try:
            container = self.client.containers.get(self._container_name(project_id))
            container.stop(timeout=5)
        except docker.errors.NotFound:
            pass

    def destroy(self, project_id: str):
        """Only call explicitly when a project is deleted by the user — never on idle."""
        import shutil
        try:
            container = self.client.containers.get(self._container_name(project_id))
            container.remove(force=True)
        except docker.errors.NotFound:
            pass
        
        # Clean up the host directory
        host_path = f"{config.HOST_PROJECTS_ROOT}/{project_id}"
        if os.path.exists(host_path):
            try:
                shutil.rmtree(host_path)
            except Exception as e:
                print(f"Warning: could not delete host path {host_path}: {e}")


async def _gc_loop():
    """Background task to stop idle containers."""
    mgr = SandboxManager()
    while True:
        try:
            now = time.time()
            for project_id, last_active in list(_last_active_tracker.items()):
                if now - last_active > config.CONTAINER_IDLE_TIMEOUT_SECONDS:
                    # Container idle, stop it
                    mgr.stop(project_id)
                    # Don't delete from tracker, so we don't spam stop, but it's fine
                    # Actually, better remove it from tracker once stopped to save memory and avoid repeated stops
                    _last_active_tracker.pop(project_id, None)
        except Exception as e:
            print(f"Error in sandbox GC loop: {e}")
        await asyncio.sleep(60)

# Global task reference to avoid garbage collection
_gc_task = None

def start_gc_loop():
    global _gc_task
    loop = asyncio.get_event_loop()
    if loop.is_running():
        _gc_task = loop.create_task(_gc_loop())

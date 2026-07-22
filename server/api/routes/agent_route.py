from uuid import UUID

from fastapi import APIRouter, Depends

from dependencies.auth_dep import CurrentUser, get_current_user
from db.user_agent import UserAgentRepository

from db.database import database

router = APIRouter(
    prefix="/agents",
    tags=["Agents"]
)

user_agent_repository = UserAgentRepository(database)

AGENT_METADATA = {
    "204cfaf9-aa29-430f-9309-4a97e81e7791": {
        "rating": "4.8",
        "icon": "speed",
        "tone": "amber",
        "category": "API",
        "synced": "Synced 2h ago",
        "installs": "12.4k",
    },
    "ee1b6b17-a05d-4e4f-a313-cdae446f62c0": {
        "rating": "4.7",
        "icon": "dashboard",
        "tone": "green",
        "category": "Data",
        "synced": "Synced 1h ago",
        "installs": "9.8k",
    },
    "fdcc23b6-0106-459e-8b0e-29072d34b28c": {
        "rating": "4.9",
        "icon": "database",
        "tone": "blue",
        "category": "Data",
        "synced": "Synced 3h ago",
        "installs": "15.2k",
    },
    "ef209bcf-caca-43d8-9d4d-33c47af59141": {
        "rating": "4.8",
        "icon": "storage",
        "tone": "violet",
        "category": "Data",
        "synced": "Synced 2h ago",
        "installs": "11.5k",
    },
    "7f52aad5-5292-436e-a7a7-e7056f0361bd": {
        "rating": "4.6",
        "icon": "memory",
        "tone": "sky",
        "category": "Data",
        "synced": "Synced 4h ago",
        "installs": "7.3k",
    },
    "8ac481f3-a4e9-4d95-b065-4726e7c1d0f8": {
        "rating": "4.7",
        "icon": "lock",
        "tone": "green",
        "category": "Security",
        "synced": "Synced 5h ago",
        "installs": "3.2k",
    },
    "ea173cc5-68ce-4711-9428-a09039e61e41": {
        "rating": "4.6",
        "icon": "account_tree",
        "tone": "blue",
        "category": "AI",
        "synced": "Synced 6h ago",
        "installs": "2.1k",
    },
    "4c38ec8e-b2b0-42c1-a78b-ded28fd14138": {
        "rating": "4.9",
        "icon": "smart_toy",
        "tone": "rose",
        "category": "AI",
        "synced": "Synced 8h ago",
        "installs": "5.6k",
    },
    "9d4bd9f2-263e-4f88-80c0-a83cd556f9de": {
        "rating": "4.5",
        "icon": "package",
        "tone": "sky",
        "category": "DevOps",
        "synced": "Synced 3h ago",
        "installs": "8.4k",
    },
    "00ac1046-fc5b-4c9b-a7a3-15f94545b1a2": {
        "rating": "4.6",
        "icon": "terminal",
        "tone": "green",
        "category": "DevOps",
        "synced": "Synced 4h ago",
        "installs": "6.1k",
    },
    "4cb0bc25-7486-4fc8-823b-cb2475f0fdd5": {
        "rating": "4.8",
        "icon": "verified_user",
        "tone": "amber",
        "category": "Security",
        "synced": "Synced 2h ago",
        "installs": "13.7k",
    },
    "99fb18b4-39b7-4b9f-848f-ec8c8e1c17b0": {
        "rating": "4.7",
        "icon": "psychology",
        "tone": "violet",
        "category": "AI",
        "synced": "Synced 5h ago",
        "installs": "10.2k",
    },
    "fb64a956-f8af-43f9-b6c8-c3b46626ee8a": {
        "rating": "4.4",
        "icon": "science",
        "tone": "rose",
        "category": "Testing",
        "synced": "Synced 7h ago",
        "installs": "5.6k",
    },
    "1f4ddc23-02c6-4e4a-8ca9-4b09bb37f198": {
        "rating": "4.5",
        "icon": "travel_explore",
        "tone": "blue",
        "category": "API",
        "synced": "Synced 8h ago",
        "installs": "4.9k",
    },
}

async def _build_agent_list(conn, user_id: str):
    agent_rows = await conn.fetch("SELECT * FROM agents")
    source_rows = await conn.fetch("SELECT agent_id, url FROM agent_sources WHERE is_active = TRUE")
    downloaded_agent_ids = await user_agent_repository.get_downloaded_agent_ids(conn, user_id)

    sources_by_agent = {}
    for source in source_rows:
        agent_id_str = str(source["agent_id"])
        sources_by_agent.setdefault(agent_id_str, []).append(source["url"])

    agents = []
    for row in agent_rows:
        agent_dict = dict(row)
        agent_id_str = str(agent_dict["id"])

        agent_type = "Core" if agent_dict.get("is_core", True) else "Community"

        version = agent_dict.get("version", "1.0.0")
        if version and not version.startswith("v"):
            version = f"v{version}"

        metadata = AGENT_METADATA.get(agent_id_str, {
            "rating": "4.5",
            "icon": "smart_toy",
            "tone": "blue",
            "category": "AI",
            "synced": "Synced just now",
            "installs": "0",
        })

        agents.append({
            "id": agent_id_str,
            "name": agent_dict["name"],
            "version": version,
            "type": agent_type,
            "description": agent_dict.get("description") or "",
            "sources": sources_by_agent.get(agent_id_str, []),
            "rating": metadata["rating"],
            "icon": metadata["icon"],
            "tone": metadata["tone"],
            "category": metadata["category"],
            "synced": metadata["synced"],
            "installs": metadata["installs"],
            "createdAt": agent_dict.get("created_at").isoformat() if agent_dict.get("created_at") else None,
            "syncedAt": (
                agent_dict.get("last_kb_update") or agent_dict.get("updated_at")
            ).isoformat() if (agent_dict.get("last_kb_update") or agent_dict.get("updated_at")) else None,
            "downloaded": agent_id_str in downloaded_agent_ids,
        })

    return agents


@router.get("")
async def get_agents(current_user: CurrentUser = Depends(get_current_user)):
    conn = await database.get_conn()
    try:
        return await _build_agent_list(conn, current_user.id)
    finally:
        await database.release_conn(conn)


@router.get("/downloaded")
async def get_downloaded_agents(current_user: CurrentUser = Depends(get_current_user)):
    conn = await database.get_conn()
    try:
        agents = await _build_agent_list(conn, current_user.id)
        return [agent for agent in agents if agent["downloaded"]]
    finally:
        await database.release_conn(conn)


@router.post("/{agent_id}/download")
async def download_agent(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user)
):
    conn = await database.get_conn()
    try:
        async with conn.transaction():
            await user_agent_repository.download_agent(conn, current_user.id, str(agent_id))
        return {"status": "downloaded", "agent_id": str(agent_id)}
    finally:
        await database.release_conn(conn)


@router.delete("/{agent_id}/download")
async def uninstall_agent(
    agent_id: UUID,
    current_user: CurrentUser = Depends(get_current_user)
):
    conn = await database.get_conn()
    try:
        async with conn.transaction():
            await user_agent_repository.uninstall_agent(conn, current_user.id, str(agent_id))
        return {"status": "uninstalled", "agent_id": str(agent_id)}
    finally:
        await database.release_conn(conn)

import os
import json
import re
from graph.llm_clients import get_groq_qa_llm
from graph.llm_utils import compact_text
from graph.state import LoomState
from db.database import database
from knowledge.memory_service import memory_service
from knowledge.memory_models import AgentMemoryEntry

QA_SYSTEM_PROMPT = """
You are a helpful technical assistant embedded in Loom, a multi-agent code generation platform.
The user has a project with a team of AI agents that will generate code for them.

Your job is to answer their question clearly and helpfully based on:
- The project goal they described
- The agents that are part of their team
- The precomputed repository context, when available
- Any retrieved memories/preferences of the user
- General software engineering knowledge

If the user is asking you to remember, store, or note a preference permanently for future use:
1. Acknowledge what you have stored in your conversational response.
2. At the very end of your response, output a JSON block wrapped in <memory> tags, e.g.:
<memory>
{
  "remember": true,
  "summary": "User prefers FastAPI framework",
  "learned_info": "User's favorite framework is FastAPI",
  "tags": ["preference", "framework"]
}
</memory>

Be concise, direct, and practical.
"""


async def qa_node(state: LoomState) -> LoomState:
    """
    Handles conversational / QnA queries.
    Calls the LLM with project context and stores the answer in state['qa_response'].
    No code is generated. No files are written.
    """
    print("\n[QA] Answering user query...")

    # 1. Resolve agent names to UUIDs and fetch relevant memories
    agent_memories = []
    name_to_id = {}
    try:
        conn = await database.get_conn()
        try:
            rows = await conn.fetch("SELECT id, name FROM agents")
            for r in rows:
                name_to_id[r["name"].lower()] = str(r["id"])
                key = r["name"].lower().replace(" agent", "").replace(" ", "_")
                if key == "authentication":
                    key = "auth"
                name_to_id[key] = str(r["id"])
        finally:
            await database.release_conn(conn)
    except Exception as exc:
        print(f"[QA] Failed to load agent name mappings: {exc}")

    # Fetch semantically similar memories for the selected agents
    user_id = state.get("user_id")
    for agent_key in state.get('selected_agents', []):
        aid = name_to_id.get(agent_key)
        if aid and user_id:
            try:
                sem_results = await memory_service.semantic_search_memories(
                    state['goal'],
                    user_id=user_id,
                    agent_id=aid,
                    limit=3,
                )
                for m, score in sem_results:
                    agent_memories.append(f"- Agent {agent_key} memory (similarity: {score:.2f}): {m.learned_info}")
            except Exception as exc:
                print(f"[QA] Failed to retrieve memories for agent {agent_key}: {exc}")

    memories_block = ""
    if agent_memories:
        memories_block = "\nRetrieved user preferences and memories:\n" + "\n".join(agent_memories)

    llm = get_groq_qa_llm()

    context_payload_text = compact_text(state.get('context_payload_text', ''), 7000)
    memories_block = compact_text(memories_block, 3000)

    user_message = f"""
Project Goal: {state['goal']}

Team Agents: {', '.join(state.get('selected_agents', []))}

Precomputed repository context:
{context_payload_text}
{memories_block}

User Question: {state['goal']}
"""

    messages = [
        {"role": "system", "content": QA_SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]

    try:
        response = llm.invoke(messages)
        answer = response.content
        
        # Check if the LLM output wants us to store a memory
        memory_match = re.search(r"<memory>(.*?)</memory>", answer, re.DOTALL)
        if memory_match:
            try:
                memory_data = json.loads(memory_match.group(1).strip())
                if memory_data.get("remember"):
                    summary = memory_data.get("summary", "User preference")
                    learned_info = memory_data.get("learned_info", state["goal"])
                    tags = memory_data.get("tags", ["user_preference"])
                    
                    # Store memory for all selected agents
                    for agent_key in state.get('selected_agents', []):
                        aid = name_to_id.get(agent_key)
                        if aid and user_id:
                            entry = AgentMemoryEntry(
                                agent_id=aid,
                                context=state["goal"],
                                summary=summary,
                                learned_info=learned_info,
                                tags=tags
                            )
                            await memory_service.save_memory(entry, user_id)
                            print(f"[QA] Saved memory permanently for agent {agent_key}")
            except Exception as mem_err:
                print(f"[QA] Failed to parse/save memory: {mem_err}")
            
            # Clean memory tags from user-facing answer
            answer = re.sub(r"<memory>.*?</memory>", "", answer, flags=re.DOTALL).strip()

        state["qa_response"] = answer
        print(f"[QA] Response generated. Length: {len(answer)} chars")
    except Exception as e:
        error_msg = f"QA node failed: {str(e)}"
        print(f"[QA] ERROR: {error_msg}")
        state["errors"].append(error_msg)
        state["qa_response"] = "Sorry, I could not answer your question right now."

    return state

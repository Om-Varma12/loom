import asyncio
import json
import os

from graph.state import LoomState
from graph.llm_clients import get_groq_planner_llm
from graph.llm_utils import compact_text
from observability.execution_logger import log_execution_event
from orchestration.planning.decomposition_engine import DecompositionEngine
from prompts.prompts import PLANNER_SYSTEM_PROMPT
from sandbox.manifest import load_manifest

TIER_MAP = {
    "postgresql":     1,
    "mongodb":        1,
    "supabase":       1,
    "redis":          1,
    "fastapi":        2,
    "auth":           2,
    "rag":            2,
    "openai":         2,
    "web_scraping":   2,
    "langchain":      2,
    "langgraph":      2,
    "pytest":         3,
    "streamlit":      4,
    "docker":         5,
    "github_actions": 5,
}


async def planner_node(state: LoomState) -> LoomState:
    """
    Calls Groq (qwen3-32b) to produce a full architecture blueprint and an
    ordered execution plan.

    Plans ONLY for state['active_agents'] — the subset the router decided is
    needed for this specific query. This prevents running mongodb/fastapi when
    the user only asked to generate the frontend.

    The plan now includes per-step fields:
      - architecture_notes : design decisions and integration points
      - coding_rules       : concrete rules the executor agent must follow
      - avoid              : anti-patterns the executor agent must skip
      - expected_output    : list of files and what each should contain

    After the LLM plan is built, the DecompositionEngine runs to produce a
    hierarchical TaskGraph stored in state['task_graph'] with per-node agent
    selection reasoning in state['task_graph_logs'].
    """
    print("\n[Planner] Generating architecture blueprint and execution plan...")

    # KEY FIX: use active_agents (what the router decided), not selected_agents (the full team)
    agents_to_plan = state.get("active_agents") or state["selected_agents"]
    print(f"[Planner] Planning for agents: {agents_to_plan}")

    llm = get_groq_planner_llm()

    tier_context = {
        agent: TIER_MAP.get(agent, 99)
        for agent in agents_to_plan
    }

    # Fetch historical context for agents to guide planning
    history_block = ""
    user_id = state.get("user_id")
    try:
        from knowledge.memory_service import memory_service
        history_items = []
        if user_id:
            for agent in agents_to_plan:
                resolved_aid = await memory_service.resolve_agent_id(agent)
                if not resolved_aid:
                    continue
                memories = await memory_service.get_memories(user_id=user_id, agent_id=resolved_aid)
                for m in memories[:3]:
                    history_items.append(
                        f"- Agent '{agent}' prior learning (Context: {m.context}): {m.learned_info}"
                    )
                executions = await memory_service.get_executions(
                    user_id=user_id,
                    agent_id=resolved_aid,
                    status="success",
                )
                for e in executions[:2]:
                    history_items.append(f"- Agent '{agent}' past successful task: '{e.task_id}'")
        if history_items:
            history_block = "\n\n## Historical Context & Prior Learnings:\n" + "\n".join(history_items)
    except Exception as he:
        print(f"[Planner] Failed to retrieve history for planner context: {he}")

    # Inject theme context so planner can reference it in architecture_notes and coding_rules
    theme = state.get("theme")
    theme_block = ""
    if theme:
        theme_block = (
            "\n\n## Selected UI Theme (pass relevant tokens into executor coding_rules):\n"
            + json.dumps(theme, indent=2)
        )

    project_id = state.get("project_id", "default")
    try:
        manifest_data = load_manifest(project_id)
    except Exception as e:
        manifest_data = {"files": {}, "conventions": []}
    
    manifest_block = (
        "\n\n## Current Project Files & Responsibilities:\n"
        + json.dumps(manifest_data, indent=2)
    )

    context_payload_text = compact_text(state.get('context_payload_text', ''), 5000)
    history_block        = compact_text(history_block, 2500)

    user_message = f"""
Project Goal: {state['goal']}

Agents to plan for (ONLY these, do not add others): {json.dumps(agents_to_plan)}

Precomputed repository context payload:
{context_payload_text}
{history_block}
{theme_block}
{manifest_block}

Use this context to choose agents and task order. Do not ask downstream agents
to rediscover the repository from scratch when the needed files are already
listed in the context payload.

Tier Map for these agents:
{json.dumps(tier_context, indent=2)}

Produce the architecture blueprint and execution plan now.
Return ONLY the JSON — no markdown, no explanation, no preamble.
"""

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user",   "content": "/think\n" + user_message},
    ]

    log_execution_event(
        "planner.input",
        {
            "project_id":     state.get("project_id"),
            "chat_session_id": state.get("chat_session_id"),
            "agents":          agents_to_plan,
            "theme":           theme,
            "messages":        messages,
        },
    )

    response = await llm.ainvoke(messages)
    raw = response.content

    # Strip <think>...</think> block if present (Qwen3 thinking mode)
    if "<think>" in raw and "</think>" in raw:
        raw = raw[raw.index("</think>") + len("</think>"):].strip()

    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    plan = []
    architecture_blueprint = {}
    try:
        parsed = json.loads(raw)
        plan = parsed.get("plan", [])
        # Store the whole parsed response as the architecture blueprint
        architecture_blueprint = parsed
    except json.JSONDecodeError as e:
        print(f"[Planner] Failed to parse plan JSON: {e}")
        print(f"[Planner] Raw output was:\n{raw}")
        state["errors"].append(f"Planner JSON parse error: {str(e)}")

    print(f"[Planner] Architecture overview: {architecture_blueprint.get('architecture_overview', 'N/A')}")
    print(f"[Planner] Plan generated with {len(plan)} steps:")
    for step in plan:
        agent = step.get('agent', '?')
        task  = step.get('task', '')[:80]
        rules = step.get('coding_rules', [])
        avoid = step.get('avoid', [])
        print(f"  Step {step.get('step')}: {agent} — {task}...")
        print(f"    Rules: {len(rules)} | Avoid: {len(avoid)}")

    state["execution_plan"]       = plan
    state["current_step"]         = 0
    state["architecture_blueprint"] = architecture_blueprint

    # --- Task Graph Decomposition ---
    try:
        engine = DecompositionEngine()
        context = {
            "project_id":        state.get("project_id"),
            "available_agents":  agents_to_plan,
            "selected_agents":   state.get("selected_agents", []),
        }
        task_graph = await engine.decompose(state["goal"], context)
        task_graph_logs = [
            f"[{node.id}] agent={node.agent_id} score={node.capability_score:.2f} | {node.selection_reasoning}"
            for node in task_graph.nodes
        ]
        state["task_graph"]      = task_graph.model_dump()
        state["task_graph_logs"] = task_graph_logs
        log_execution_event(
            "planner.task_graph_built",
            {
                "project_id":      state.get("project_id"),
                "chat_session_id": state.get("chat_session_id"),
                "node_count":      len(task_graph.nodes),
                "logs":            task_graph_logs,
            },
        )
        print(f"[Planner] Task graph built with {len(task_graph.nodes)} nodes.")
    except Exception as exc:
        state["task_graph"]      = None
        state["task_graph_logs"] = []
        log_execution_event(
            "planner.task_graph_skipped",
            {
                "project_id":      state.get("project_id"),
                "chat_session_id": state.get("chat_session_id"),
                "error":           str(exc),
            },
        )
        print(f"[Planner] Task graph skipped: {exc}")

    log_execution_event(
        "planner.output",
        {
            "project_id":            state.get("project_id"),
            "chat_session_id":       state.get("chat_session_id"),
            "plan_json":             plan,
            "architecture_blueprint": architecture_blueprint,
            "raw_output":            raw,
            "errors":                state.get("errors", []),
        },
    )
    return state

import json
import logging
import os

from graph.llm_clients import get_ollama_executor_llm
from graph.llm_utils import compact_text
from graph.state import LoomState
from observability.execution_logger import log_execution_event
from prompts.prompts import AGENT_PROMPT_MAP
from services.knowledge_service import knowledge_service

from tools.langgraph_tools import tool_list_files, tool_read_file, tool_grep, tool_edit_file, tool_write_new_file, tool_run_command
from sandbox.manifest import load_manifest
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)


def _build_theme_block(theme_content: str | None, theme: dict | None = None) -> str:
    """
    Build a comprehensive UI design-system prompt block for the executor.

    Priority order:
      1. theme_content (full Markdown from a theme .md file) — preferred.
      2. theme dict (legacy token map) — backward-compat fallback.
      3. Neither present → return empty string.

    When theme_content is available the function wraps the raw Markdown
    in a rich instructional scaffold so the Streamlit agent treats it as a
    *complete design system* rather than a list of colours.
    """
    if theme_content:
        return f"""

## ═══════════════════════════════════════════════════════
## DESIGN SYSTEM — Full Specification
## ═══════════════════════════════════════════════════════

You are building a Streamlit UI application that must **fully internalize** the
design system defined below.  This is not a style guide to reference — it is the
complete visual identity of this application.  Every screen, every component,
every interaction must embody this design language consistently.

### Theme Design System (Complete Specification)

{theme_content}

### ── Implementation Directives ─────────────────────────────────────────────

**VISUAL IDENTITY**
Apply the complete design language from top to bottom.  Every screen must feel
like it was crafted by the same experienced product designer.  Inconsistency is
a failure mode.

**COLOR SYSTEM**
• Use the primary color for main CTAs, active states, and key interactive elements.
• Honour the full surface hierarchy (canvas → card surface → elevated surface) to
  create depth and visual separation between layers.
• Use muted/ink tones for body text; reserve accent colors for intentional emphasis.
• Never invent colors outside the defined palette.

**TYPOGRAPHY**
• Apply the exact font families specified.  Import any web fonts via st.markdown().
• Scale headings (display → title → body → caption/label) precisely as defined.
• Typography IS the hierarchy — let it lead the reader's eye without needing icons.
• Set correct letter-spacing and line-height where Streamlit allows inline CSS.

**SPACING & LAYOUT**
• Apply the defined spacing units (padding, margin, gap) consistently throughout.
• Prefer generous whitespace over cramming content — this is a premium UI.
• Use columns and containers to mirror the grid system described by the theme.

**COMPONENT STYLING** (apply via st.markdown with injected CSS)
• Buttons: exact border-radius, padding, background, hover state.
• Cards / containers: exact shadow, border-radius, background surface color.
• Input fields: border style, focus ring color, placeholder color.
• All interactive controls must feel cohesive — no mismatched border radii.

**SHADOWS & ELEVATION**
Apply the shadow/elevation system faithfully.  Cards and modals should feel
lifted off the canvas; primary content surfaces should feel grounded.

**ANIMATIONS & MICRO-INTERACTIONS**
Where Streamlit allows CSS transitions, implement the motion principles defined
(prefer 150–300 ms ease-out transitions for hover and state changes).
Avoid abrupt or jarring changes.

**UX PHILOSOPHY**
Follow the UI philosophy section of the theme verbatim.  Prioritise clarity,
scannability, and delight in that order.

**ACCESSIBILITY**
Maintain WCAG AA contrast ratios using the defined palette.  Use semantic HTML
constructs within st.markdown() wherever possible.  Ensure interactive elements
have visible focus indicators.

**COHESION REQUIREMENT**
Every generated screen must feel like part of the same product.  Run a final
mental pass: "Does this look like it came from the same designer who specified
the theme?"  If not, reconcile it before outputting.

## ═══════════════════════════════════════════════════════
"""

    # ── Legacy fallback: dict of design tokens ────────────────────────────────
    if not theme:
        return ""

    return (
        "\n\n## UI Theme Tokens (apply these to all visual/UI code)\n"
        "The user has selected a custom theme. Use these design tokens exactly:\n"
        + json.dumps(theme, indent=2)
        + "\n\nApply: colors for backgrounds/buttons/text, font-family for all text elements, "
          "button_radius/button_size for interactive controls.\n"
    )


def _build_planner_rules_block(step: dict) -> str:
    """
    Format the planner's per-step architecture guidance into a prompt block.
    Empty sections are omitted gracefully.
    """
    parts = []

    arch = step.get("architecture_notes", "")
    if arch:
        parts.append(f"## Architecture Notes\n{arch}")

    rules = step.get("coding_rules", [])
    if rules:
        parts.append("## Coding Rules (MUST follow)\n" + "\n".join(f"- {r}" for r in rules))

    avoid = step.get("avoid", [])
    if avoid:
        parts.append("## Anti-patterns to Avoid\n" + "\n".join(f"- {a}" for a in avoid))

    target_files = step.get("target_files", [])
    if target_files:
        files_str = "\n".join(
            f"- `{f.get('path')}` ({f.get('action')}): {f.get('change')}" for f in target_files
        )
        parts.append("## Planned Files for this Step (MUST adhere to this structure)\n" + files_str)

    expected = step.get("expected_output", "")
    if expected:
        parts.append(f"## Expected Output\n{expected}")

    if not parts:
        return ""
    return "\n\n" + "\n\n".join(parts)


def _build_folder_structure_block(folder_structure: dict | None) -> str:
    """
    Format the pre-created project directory tree into a prompt block
    so Ollama knows exactly where to write each file.

    The block is injected into every executor step — agents must write
    files ONLY inside the listed directories.
    """
    if not folder_structure:
        return ""

    dirs       = folder_structure.get("dirs", [])
    file_hints = folder_structure.get("file_hints", {})

    if not dirs and not file_hints:
        return ""

    parts = []

    if dirs:
        dirs_str = "\n".join(f"  {d}/" for d in sorted(dirs))
        parts.append(
            "## Pre-created Project Structure (CRITICAL — write files ONLY inside these dirs)\n"
            "The following directories have been pre-created in the sandbox.\n"
            "You MUST place every file you create inside the appropriate directory below.\n"
            "Do NOT create arbitrary top-level files or folders outside this structure.\n"
            f"```\n{dirs_str}\n```"
        )

    if file_hints:
        hints_str = "\n".join(f"  {path}  →  {desc}" for path, desc in sorted(file_hints.items()))
        parts.append(
            "## Planned File Map (what goes where)\n"
            + hints_str
        )

    return "\n\n" + "\n\n".join(parts)


async def executor_node(state: LoomState) -> LoomState:
    """
    Executes the current step in the execution plan using Ollama Cloud.

    Per-step behaviour:
      1. Retrieves the current plan step (agent, task, context_keys, planner rules).
      2. Builds a rich user message that includes:
           - Project goal
           - Specific task
           - Repository context
           - Prior agent outputs (context_keys)
           - Planner architecture notes, coding rules, avoid list, expected output
           - UI theme tokens (if the user selected a theme)
           - Knowledge/memory context
      3. Calls Ollama Cloud (via OpenAI-compatible API) to generate code.
      4. Validates output; retries up to max_attempts on validation failure.
      5. Raises if validation still fails — NO hardcoded fallback.
      6. Stores output in state['agent_outputs'][agent_name].
      7. Records execution details in the knowledge/memory system.
    """
    plan       = state["execution_plan"]
    step_index = state["current_step"]

    if step_index >= len(plan):
        print(f"\n[Executor] No more steps to execute.")
        return state

    current_step = plan[step_index]
    agent_name   = current_step["agent"]
    task         = current_step["task"]
    context_keys = current_step.get("context_keys", [])

    print(f"\n[Executor] Step {step_index + 1}/{len(plan)}: Running agent '{agent_name}'")
    print(f"[Executor] Task: {task}")

    system_prompt = AGENT_PROMPT_MAP.get(agent_name)
    if not system_prompt:
        error_msg = f"No system prompt found for agent: {agent_name}"
        logger.error("[Executor] ERROR: %s", error_msg)
        state["errors"].append(error_msg)
        state["current_step"] = step_index + 1
        return state

    # ── Build context block from prior agent outputs ─────────────────────────
    context_block = ""
    if context_keys:
        context_parts = []
        for key in context_keys:
            prior_output = state["agent_outputs"].get(key)
            if prior_output:
                context_parts.append(
                    f"=== Output from {key} agent ===\n{compact_text(prior_output, 5000)}\n"
                )
        if context_parts:
            context_block = "\n\n## Context from prior agents:\n" + "\n".join(context_parts)

    # ── Prepare knowledge/memory context ─────────────────────────────────────
    chat_session_id = state.get("chat_session_id")
    user_id = state.get("user_id")
    knowledge_block = ""
    if chat_session_id:
        try:
            knowledge_block = await knowledge_service.prepare_agent_context(
                agent_name=agent_name,
                chat_session_id=chat_session_id,
                task=task,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("[Executor] Failed to prepare knowledge context: %s", exc)

    context_payload_text = compact_text(state.get('context_payload_text', ''), 10000)
    knowledge_block      = compact_text(knowledge_block, 5000)

    # ── Build planner rules block for this step ───────────────────────────────
    planner_rules_block = _build_planner_rules_block(current_step)

    # ── Build theme block if theme was selected ───────────────────────────────
    theme_block = _build_theme_block(
        theme_content=state.get("theme_content"),
        theme=state.get("theme"),
    )

    project_id = state.get("project_id", "default")
    try:
        manifest_data = load_manifest(project_id)
    except Exception:
        manifest_data = {"files": {}, "conventions": []}
        
    manifest_block = (
        "\n\n## Current Project Files & Responsibilities:\n"
        + json.dumps(manifest_data, indent=2)
    )

    # ── Build folder structure block from pre-created sandbox dirs ────────────
    folder_structure_block = _build_folder_structure_block(state.get("folder_structure"))

    user_message = f"""
Project Goal: {state['goal']}

Your specific task: {task}

Precomputed repository context:
{context_payload_text}

Use the relevant files, relationships, and change_surface above as your primary
repo map. Do not repeat broad repo scanning in your answer; write code against
this context and only infer missing details when the context has an explicit gap.
{context_block}
{knowledge_block}
{folder_structure_block}
{planner_rules_block}
{theme_block}
{manifest_block}

Always use your provided tools to list, read, edit, and create files. Do not generate raw markdown code blocks.
Project ID to use in your tool calls: {project_id}
"""

    llm = get_ollama_executor_llm()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    log_execution_event(
        "agent.input",
        {
            "project_id":      state.get("project_id"),
            "chat_session_id": state.get("chat_session_id"),
            "agent":           agent_name,
            "step_index":      step_index,
            "task":            task,
            "context_keys":    context_keys,
            "has_theme":       bool(state.get("theme_content") or state.get("theme")),
            "theme_id":        state.get("theme_id"),
            "messages":        messages,
        },
    )

    try:
        output = ""
        sandbox_tools = [tool_list_files, tool_read_file, tool_grep, tool_edit_file, tool_write_new_file, tool_run_command]
        tool_map = {t.name: t for t in sandbox_tools}
        llm_with_tools = llm.bind_tools(sandbox_tools)
        
        chat_history = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        print(f"[Executor] Calling Ollama Cloud for agent '{agent_name}' with tools...")
        max_tool_iterations = 15
        
        for iteration in range(max_tool_iterations):
            response = await llm_with_tools.ainvoke(chat_history)
            chat_history.append(response)
            
            if not response.tool_calls:
                output = response.content
                break
                
            for tool_call in response.tool_calls:
                t_name = tool_call["name"]
                t_args = tool_call["args"].copy()
                if "project_id" not in t_args:
                    t_args["project_id"] = project_id
                    
                print(f"  -> Agent called tool: {t_name}")
                try:
                    tool_func = tool_map.get(t_name)
                    if tool_func:
                        tool_result = tool_func.invoke(t_args)
                    else:
                        tool_result = f"Error: Tool {t_name} not found."
                except Exception as e:
                    tool_result = f"Error executing {t_name}: {str(e)}"
                    
                chat_history.append(ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"]))

        state["agent_outputs"][agent_name] = output
        print(f"[Executor] Agent '{agent_name}' completed successfully.")

        # ── Record successful execution in knowledge/memory system ───────────
        if chat_session_id:
            try:
                await knowledge_service.after_agent_execution(
                    agent_name=agent_name,
                    chat_session_id=chat_session_id,
                    task=task,
                    output=output,
                    user_id=user_id,
                )
            except Exception as db_exc:
                logger.warning("[Executor] Failed to record execution details: %s", db_exc)

        try:
            from knowledge.memory_service import memory_service
            from knowledge.memory_models import AgentExecutionEntry, AgentDecisionEntry, AgentMemoryEntry
            from knowledge.reflection import MemoryReflectionEngine

            resolved_aid = await memory_service.resolve_agent_id(agent_name)
            if resolved_aid and user_id:
                exec_entry = AgentExecutionEntry(
                    agent_id=resolved_aid,
                    task_id=task,
                    input_data=user_message,
                    output_data=output,
                    status="success",
                    metadata={"chat_session_id": chat_session_id or "local-run"}
                )
                saved_exec = await memory_service.save_execution(exec_entry, user_id)

                reflections = await MemoryReflectionEngine.extract_reflections(task, output)

                decision_entry = AgentDecisionEntry(
                    execution_id=saved_exec.id,
                    agent_id=resolved_aid,
                    decision=reflections["decision"],
                    reasoning=reflections["reasoning"],
                    outcome=reflections["outcome"]
                )
                await memory_service.save_decision(decision_entry, user_id)

                memory_entry = AgentMemoryEntry(
                    agent_id=resolved_aid,
                    context=task,
                    summary=f"Completed task '{task}'",
                    learned_info=reflections["learned_info"],
                    tags=["execution_learning", agent_name]
                )
                await memory_service.save_memory(memory_entry, user_id)

                try:
                    from knowledge.sync_manager import sync_manager
                    from datetime import datetime, timezone
                    import uuid

                    shared_entry = {
                        "id":           f"shared-{saved_exec.id or uuid.uuid4()}",
                        "content":      f"Agent '{agent_name}' learned from task '{task}': {reflections['learned_info']}",
                        "version":      1,
                        "timestamp":    datetime.now(timezone.utc).isoformat(),
                        "source_agent": agent_name,
                        "priority":     "medium",
                        "tags":         ["agent_sharing", agent_name]
                    }
                    await sync_manager.add_knowledge(shared_entry, user_id)
                except Exception as se:
                    logger.warning("[Executor] Failed to share knowledge dynamically: %s", se)
        except Exception as pe:
            logger.warning("[Executor] Failed to write Phase 2 execution/decision/memory logs: %s", pe)

        log_execution_event(
            "agent.output",
            {
                "project_id":      state.get("project_id"),
                "chat_session_id": state.get("chat_session_id"),
                "agent":           agent_name,
                "step_index":      step_index,
                "task":            task,
                "raw_output":      output,
                "errors":          state.get("errors", []),
            },
        )

    except Exception as e:
        error_msg = f"Agent '{agent_name}' failed: {str(e)}"
        logger.error("[Executor] ERROR: %s", error_msg)
        state["errors"].append(error_msg)
        state["agent_outputs"][agent_name] = ""

        # ── Record failed execution ──────────────────────────────────────────
        try:
            from knowledge.memory_service import memory_service
            from knowledge.memory_models import AgentExecutionEntry, AgentDecisionEntry, AgentMemoryEntry
            from knowledge.reflection import MemoryReflectionEngine

            resolved_aid = await memory_service.resolve_agent_id(agent_name)
            if resolved_aid and user_id:
                exec_entry = AgentExecutionEntry(
                    agent_id=resolved_aid,
                    task_id=task,
                    input_data=user_message,
                    output_data=f"ERROR: {error_msg}",
                    status="failure",
                    metadata={"chat_session_id": chat_session_id or "local-run"}
                )
                saved_exec = await memory_service.save_execution(exec_entry, user_id)

                reflections = await MemoryReflectionEngine.extract_reflections(
                    task, f"ERROR: {error_msg}", error_logs=error_msg
                )

                decision_entry = AgentDecisionEntry(
                    execution_id=saved_exec.id,
                    agent_id=resolved_aid,
                    decision=reflections["decision"],
                    reasoning=reflections["reasoning"],
                    outcome=reflections["outcome"]
                )
                await memory_service.save_decision(decision_entry, user_id)

                memory_entry = AgentMemoryEntry(
                    agent_id=resolved_aid,
                    context=task,
                    summary=f"Failed task '{task}'",
                    learned_info=reflections["learned_info"],
                    tags=["execution_failure", agent_name]
                )
                await memory_service.save_memory(memory_entry, user_id)
        except Exception as db_err:
            logger.warning("[Executor] Failed to write Phase 2 failure logs: %s", db_err)

        log_execution_event(
            "agent.error",
            {
                "project_id":      state.get("project_id"),
                "chat_session_id": state.get("chat_session_id"),
                "agent":           agent_name,
                "step_index":      step_index,
                "task":            task,
                "error":           str(e),
            },
        )

    state["current_step"] = step_index + 1
    return state

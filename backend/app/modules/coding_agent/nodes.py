import sys
import os
import json
import time
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from typing import Dict, Any, Union, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.core.llm import get_cached_llm, get_cached_coder_llm, resilient_llm_invoke
from app.core.storage import log_audit_event
from app.constants import (
    MAX_TOOL_CALLS_PER_TURN,
    MAX_REPAIR_RETRIES,
)
from app.integrations.tools import (
    ALL_TOOLS,
    DIRECT_ACTION_TOOLS,
    READ_ONLY_TOOLS,
    CODER_TOOLS,
)
from app.modules.coding_agent.state import CodingAgentState, TaskExecutionStatus, ToolExecutionRecord, TaskType
from app.modules.coding_agent.manifest import capture_workspace_manifest, verify_code_changes
from app.modules.coding_agent.test_runner import resolve_project_test_runner, execute_sandboxed_test_command
from app.modules.coding_agent.edges import classify_intent_with_fallback
from app.modules.coding_agent.prompts import (
    PLANNER_SYSTEM_PROMPT,
    CODER_SYSTEM_PROMPT,
    CONVERSATION_SYSTEM_PROMPT,
    TOOL_AGENT_SYSTEM_PROMPT,
    CODE_INSPECTOR_SYSTEM_PROMPT,
    FIXER_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    build_planner_prompt,
    build_coder_plan_context,
    build_fixer_prompt,
    build_fixer_instruction,
    build_summarizer_prompt,
)


def extract_text(content: Union[str, List[Any], Any]) -> str:
    """Safely extracts string text from LLM message content across different providers."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
        return "".join(parts)
    return str(content)


def get_actual_git_modified_files(workspace_root: str) -> List[str]:
    """Inspects live git status to discover all actually modified/created files."""
    import subprocess
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            lines = res.stdout.splitlines()
            files = []
            for line in lines:
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    files.append(parts[1])
            return files
    except Exception:
        pass
    return []


def create_tool_record(
    task_id: str,
    intent: TaskType,
    tool_name: str,
    input_args: Dict[str, Any],
    status: str,
    output_preview: str,
    workspace_root: str,
    error: Optional[str] = None,
    retry_attempt: int = 0,
) -> ToolExecutionRecord:
    """Creates a structured, disk-verified record of a physical tool execution."""
    artifact_path = None
    artifact_verified = False

    # Extract artifact path
    if tool_name == "generate_image":
        artifact_path = input_args.get("output_path") or ""
        if not artifact_path and "assets/" in output_preview:
            import re
            m = re.search(r"assets/[^\s\)\'\"\,]+", output_preview)
            if m:
                artifact_path = m.group(0)
    elif tool_name in ("write_file", "patch_file", "delete_file"):
        artifact_path = input_args.get("file_path")

    if artifact_path:
        full_p = Path(workspace_root) / artifact_path if not Path(artifact_path).is_absolute() else Path(artifact_path)
        artifact_verified = full_p.exists()
        # If tool was supposed to create an artifact and it does not exist, status should reflect failure
        if tool_name in ("generate_image", "write_file") and not artifact_verified and status == "success":
            status = "failed"
            if not error:
                error = f"Expected artifact {artifact_path} was not found on disk."

    return {
        "task_id": task_id,
        "intent": intent,
        "tool_name": tool_name,
        "input_args": input_args,
        "status": status,  # type: ignore
        "output_preview": output_preview[:400],
        "error": error,
        "artifact_path": artifact_path,
        "artifact_verified": artifact_verified,
        "timestamp": time.time(),
        "retry_attempt": retry_attempt,
    }


def _collect_new_tool_records(
    messages: List[BaseMessage],
    existing_history: List[ToolExecutionRecord],
    intent: TaskType,
    workspace_root: str,
) -> List[ToolExecutionRecord]:
    """Inspects recent ToolMessages in state and produces structured execution records."""
    records = list(existing_history)
    recorded_tool_ids = {r.get("task_id") for r in records}

    # Match AIMessages containing tool_calls with subsequent ToolMessages
    last_ai_calls: Dict[str, Dict[str, Any]] = {}
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                call_id = tc.get("id") or tc.get("name")
                if call_id:
                    last_ai_calls[call_id] = tc

        elif getattr(msg, "type", "") == "tool" or isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", "") or getattr(msg, "name", "")
            if tool_call_id and tool_call_id not in recorded_tool_ids:
                matching_call = last_ai_calls.get(tool_call_id, {})
                tool_name = matching_call.get("name") or getattr(msg, "name", "tool")
                input_args = matching_call.get("args", {})
                content_str = extract_text(getattr(msg, "content", ""))

                # Authoritative error detection from actual tool message status or structured output
                is_error = False
                error_detail: Optional[str] = None

                # 1. Check ToolMessage explicit status
                if getattr(msg, "status", None) == "error":
                    is_error = True
                    error_detail = content_str

                # 2. Check structured tool return (dict or JSON)
                if not is_error and content_str.strip().startswith("{") and content_str.strip().endswith("}"):
                    try:
                        parsed_output = json.loads(content_str)
                        if isinstance(parsed_output, dict):
                            if parsed_output.get("status") in ("error", "failed") or parsed_output.get("success") is False:
                                is_error = True
                                error_detail = parsed_output.get("error") or parsed_output.get("message") or content_str
                    except Exception:
                        pass

                rec = create_tool_record(
                    task_id=tool_call_id,
                    intent=intent,
                    tool_name=tool_name,
                    input_args=input_args,
                    status="failed" if is_error else "success",
                    output_preview=content_str,
                    workspace_root=workspace_root,
                    error=error_detail if is_error else None,
                )
                records.append(rec)
                recorded_tool_ids.add(tool_call_id)

    return records


# =====================================================================
# 1. Intent Classifier & Baseline Snapshot Node
# =====================================================================

def classifier_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Classifier Node:
    1. Captures workspace baseline manifest with a 2-second wall-clock timeout.
    2. Classifies task intent using multi-turn conversation context and tool records.
    3. Resolves follow-up actions (retries, refinements, status questions).
    """
    task = state.get("task", "")
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    messages = list(state.get("messages", []))
    active_task = state.get("active_task_context")
    active_intent = state.get("active_task_intent") or state.get("task_type")
    active_task_id = state.get("active_task_id")
    tool_history = list(state.get("tool_execution_history", []))

    # Derive active intent and task from tool history if missing on fresh invocation
    if not active_intent and tool_history:
        for rec in reversed(tool_history):
            if rec.get("intent") and rec["intent"] != "conversation":
                active_intent = rec["intent"]
                break

    if not active_task and tool_history:
        for rec in reversed(tool_history):
            args = rec.get("input_args", {})
            if args.get("prompt"):
                active_task = args["prompt"]
                break
            elif args.get("query"):
                active_task = args["query"]
                break

    # Capture hardened workspace baseline
    manifest = capture_workspace_manifest(workspace_root, timeout_sec=2.0)

    # Classify intent & resolve follow-up
    category, intent, resolved_task = classify_intent_with_fallback(
        task,
        messages,
        workspace_root,
        active_task=active_task,
        active_intent=active_intent,
        tool_history=tool_history,
    )

    effective_active_task = resolved_task if intent != "conversation" else active_task
    effective_active_intent = intent if intent != "conversation" else active_intent

    return {
        "task": resolved_task,
        "workspace_manifest": manifest,
        "task_type": intent,
        "follow_up_category": category,
        "active_task_context": effective_active_task,
        "active_task_intent": effective_active_intent,
        "active_task_id": active_task_id,
        "execution_status": "incomplete",
        "direct_tool_iterations": 0,
        "inspector_tool_iterations": 0,
        "coder_tool_iterations": 0,
        "retry_count": 0,
    }


# =====================================================================
# 2. Conversational Agent Node (Zero Tools, Authoritative Answers)
# =====================================================================

def conversation_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Conversation Node:
    Handles greetings, conversational follow-ups, and status questions directly.
    Answers truthfully based on authoritative ToolExecutionRecords without fabricating results.
    """
    messages = list(state.get("messages", []))
    tool_history = list(state.get("tool_execution_history", []))

    # Format recorded tool history for honest answers
    history_context = ""
    if tool_history:
        history_lines = ["\n\n### Authoritative Tool Execution Records:"]
        for idx, rec in enumerate(tool_history[-6:], 1):
            t_name = rec.get("tool_name", "tool")
            t_status = rec.get("status", "unknown")
            args_str = json.dumps(rec.get("input_args", {}))
            art_p = rec.get("artifact_path") or "None"
            verified = rec.get("artifact_verified", False)
            out_prev = rec.get("output_preview", "")
            history_lines.append(
                f"- Attempt {idx}: Tool '{t_name}' | Status: {t_status} | Input: {args_str} | Artifact: {art_p} (Verified on disk: {verified}) | Output: {out_prev[:200]}"
            )
        history_context = "\n".join(history_lines)

    sys_content = CONVERSATION_SYSTEM_PROMPT + history_context
    formatted_messages = [SystemMessage(content=sys_content)] + messages

    try:
        response = resilient_llm_invoke(formatted_messages)
    except Exception:
        llm = get_cached_llm()
        response = llm.invoke(formatted_messages)

    return {
        "messages": [response],
        "execution_status": "completed",
    }


# =====================================================================
# 3. Direct Tool Agent Node (Media / Web / Browser)
# =====================================================================

def tool_agent_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Tool Agent Node:
    Executes direct single-turn or multi-turn tool actions (image generation, web search, doc scrape).
    Enforces per-cycle batch limit (max 8) and iteration cap (max 5).
    """
    messages = list(state.get("messages", []))
    iterations = state.get("direct_tool_iterations", 0) + 1
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    tool_history = list(state.get("tool_execution_history", []))
    intent = state.get("task_type", "image_generation")

    # Collect tool records from previous tool executions
    updated_history = _collect_new_tool_records(messages, tool_history, intent, workspace_root)

    formatted_messages = [SystemMessage(content=TOOL_AGENT_SYSTEM_PROMPT)] + messages

    try:
        response = resilient_llm_invoke(formatted_messages, tools=DIRECT_ACTION_TOOLS)
    except Exception:
        llm = get_cached_coder_llm(DIRECT_ACTION_TOOLS)
        response = llm.invoke(formatted_messages)

    valid_tool_names = {t.name for t in DIRECT_ACTION_TOOLS}
    status: TaskExecutionStatus = "incomplete"

    if hasattr(response, "tool_calls") and response.tool_calls:
        if len(response.tool_calls) > MAX_TOOL_CALLS_PER_TURN:
            response.tool_calls = []
            return {
                "messages": [AIMessage(content=f"❌ Request exceeded maximum allowed tool calls per turn ({MAX_TOOL_CALLS_PER_TURN}). Operation aborted.")],
                "direct_tool_iterations": iterations,
                "execution_status": "incomplete",
                "tool_execution_history": updated_history,
            }

        sanitized_calls = [tc for tc in response.tool_calls if tc.get("name") in valid_tool_names]
        response.tool_calls = sanitized_calls
    else:
        status = "completed"

    return {
        "messages": [response],
        "direct_tool_iterations": iterations,
        "execution_status": status,
        "tool_execution_history": updated_history,
    }


# =====================================================================
# 4. Code Inspector Node (Strictly Read-Only Analysis)
# =====================================================================

def code_inspector_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Code Inspector Node:
    Inspects and explains existing repository code using strictly read-only tools.
    Cannot write, patch, or delete files.
    """
    messages = list(state.get("messages", []))
    iterations = state.get("inspector_tool_iterations", 0) + 1
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    tool_history = list(state.get("tool_execution_history", []))
    intent = state.get("task_type", "code_question")

    updated_history = _collect_new_tool_records(messages, tool_history, intent, workspace_root)

    formatted_messages = [SystemMessage(content=CODE_INSPECTOR_SYSTEM_PROMPT)] + messages

    try:
        response = resilient_llm_invoke(formatted_messages, tools=READ_ONLY_TOOLS)
    except Exception:
        llm = get_cached_coder_llm(READ_ONLY_TOOLS)
        response = llm.invoke(formatted_messages)

    valid_tool_names = {t.name for t in READ_ONLY_TOOLS}
    status: TaskExecutionStatus = "incomplete"

    if hasattr(response, "tool_calls") and response.tool_calls:
        if len(response.tool_calls) > MAX_TOOL_CALLS_PER_TURN:
            response.tool_calls = []
            return {
                "messages": [AIMessage(content=f"❌ Request exceeded maximum allowed tool calls per turn ({MAX_TOOL_CALLS_PER_TURN}). Operation aborted.")],
                "inspector_tool_iterations": iterations,
                "execution_status": "incomplete",
                "tool_execution_history": updated_history,
            }

        sanitized_calls = [tc for tc in response.tool_calls if tc.get("name") in valid_tool_names]
        response.tool_calls = sanitized_calls
    else:
        status = "completed"

    return {
        "messages": [response],
        "inspector_tool_iterations": iterations,
        "execution_status": status,
        "tool_execution_history": updated_history,
    }


# =====================================================================
# 5. Planner Node (Senior Software Architect)
# =====================================================================

def planner_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Planner Node (Senior Software Architect):
    Designs architectural blueprints and test specifications for code_change tasks.
    Never modifies files directly.
    """
    task = state.get("task", "")
    repo_tree = state.get("repository_tree", "")
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))

    planner_prompt = build_planner_prompt(task, repo_tree, workspace_root)

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=planner_prompt),
    ]

    try:
        response = resilient_llm_invoke(messages)
    except Exception:
        llm = get_cached_llm()
        response = llm.invoke(messages)

    plan_text = extract_text(response.content)

    log_audit_event({
        "agent": "planner_node",
        "task": task[:200],
        "plan_length": len(plan_text),
    }, workspace_root=workspace_root)

    return {
        "plan": plan_text,
        "retry_count": 0,
        "test_passed": False,
        "test_results": None,
        "fixer_analysis": None,
    }


# =====================================================================
# 6. Coder Node (Implementation & Surgical Patching)
# =====================================================================

def coder_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Coder Node:
    Implements approved blueprints, manages git operations, patches code files,
    and runs allowed terminal commands under workspace sandboxing.
    """
    task = state.get("task", "")
    plan = state.get("plan", "")
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    messages: List[BaseMessage] = list(state.get("messages", []))
    findings = list(state.get("coder_findings", []))
    modified_files = list(state.get("modified_files", []))
    iterations = state.get("coder_tool_iterations", 0) + 1
    tool_history = list(state.get("tool_execution_history", []))
    intent = state.get("task_type", "code_change")

    updated_history = _collect_new_tool_records(messages, tool_history, intent, workspace_root)

    # Prepend architectural blueprint context if coming from Planner
    if plan and not any("Architect Blueprint:" in getattr(m, "content", "") for m in messages if isinstance(m, HumanMessage)):
        plan_context = HumanMessage(content=build_coder_plan_context(plan))
        messages.append(plan_context)

    formatted_messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + messages

    try:
        response = resilient_llm_invoke(formatted_messages, tools=CODER_TOOLS)
    except Exception:
        llm = get_cached_coder_llm(CODER_TOOLS)
        response = llm.invoke(formatted_messages)

    valid_tool_names = {t.name for t in CODER_TOOLS}
    if hasattr(response, "tool_calls") and response.tool_calls:
        if len(response.tool_calls) > MAX_TOOL_CALLS_PER_TURN:
            response.tool_calls = []
            return {
                "messages": [AIMessage(content=f"❌ Request exceeded maximum allowed tool calls per turn ({MAX_TOOL_CALLS_PER_TURN}). Operation aborted.")],
                "coder_tool_iterations": iterations,
                "execution_status": "incomplete",
                "tool_execution_history": updated_history,
            }

        sanitized_calls = [tc for tc in response.tool_calls if tc.get("name") in valid_tool_names]
        response.tool_calls = sanitized_calls

        for tool_call in response.tool_calls:
            name = tool_call.get("name", "")
            args = tool_call.get("args", {})
            if name in ("write_file", "patch_file", "delete_file"):
                file_path = args.get("file_path")
                if file_path and file_path not in modified_files:
                    modified_files.append(file_path)

            log_audit_event({
                "agent": "coder_node",
                "action": "tool_call",
                "tool": name,
                "args": {k: str(v)[:100] for k, v in args.items()},
            }, workspace_root=workspace_root)

    content_str = extract_text(response.content).strip()
    if content_str and not (hasattr(response, "tool_calls") and response.tool_calls):
        findings.append(content_str)

    return {
        "messages": [response],
        "coder_findings": findings,
        "modified_files": modified_files,
        "coder_tool_iterations": iterations,
        "tool_execution_history": updated_history,
    }


# =====================================================================
# 7. Dedicated Physical Tool Nodes
# =====================================================================

direct_action_tool_node = ToolNode(DIRECT_ACTION_TOOLS)
read_only_tool_node = ToolNode(READ_ONLY_TOOLS)
coder_tool_node = ToolNode(CODER_TOOLS)
tool_node = coder_tool_node  # Backwards-compatibility alias


# =====================================================================
# 8. Project-Aware Test Validation Node
# =====================================================================

def validation_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Validation Node:
    Detects project test runner and executes verification suite in an allowlist-isolated subprocess.
    """
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    test_cmd = state.get("test_command")

    if not test_cmd:
        runner_cmd, error = resolve_project_test_runner(workspace_root)
        if error:
            return {
                "test_passed": False,
                "test_results": f"⚠️ Validation unavailable: {error}",
                "execution_status": "failed",
                "detected_test_runner": None,
            }
        test_cmd = runner_cmd

    passed, output, status = execute_sandboxed_test_command(test_cmd, workspace_root)

    return {
        "test_passed": passed,
        "test_results": output,
        "execution_status": status,
        "detected_test_runner": test_cmd,
    }


# Backwards compatibility alias
validator_node = validation_node


# =====================================================================
# 9. Dedicated Test Runner Node (for explicit test requests)
# =====================================================================

def dedicated_test_runner_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Dedicated Test Runner Node:
    Directly handles explicit user test requests ('run pytest', 'run tests') independently of code edits.
    """
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    task = state.get("task", "")
    test_cmd = state.get("test_command")

    if not test_cmd:
        runner_cmd, error = resolve_project_test_runner(workspace_root)
        if error:
            return {
                "test_passed": False,
                "test_results": f"⚠️ Test runner unavailable: {error}",
                "execution_status": "failed",
                "final_summary": f"Could not execute tests: {error}",
            }
        test_cmd = runner_cmd

    passed, output, status = execute_sandboxed_test_command(test_cmd, workspace_root)

    return {
        "test_passed": passed,
        "test_results": output,
        "execution_status": status,
        "final_summary": output,
    }


# =====================================================================
# 10. Fixer Node (Diagnostic Root-Cause Debugger)
# =====================================================================

def fixer_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Fixer Node:
    Analyzes failure tracebacks and returns precise surgical fix instructions.
    Increments retry_count exactly once when entering repair.
    """
    llm = get_cached_llm()
    task = state.get("task", "")
    plan = state.get("plan", "")
    test_results = state.get("test_results", "")
    current_retry = state.get("retry_count", 0) + 1
    max_retries = getattr(settings, "MAX_RETRY_COUNT", MAX_REPAIR_RETRIES)

    prompt_content = build_fixer_prompt(task, plan, test_results, current_retry, max_retries)

    messages = [
        SystemMessage(content=FIXER_SYSTEM_PROMPT),
        HumanMessage(content=prompt_content),
    ]

    response = llm.invoke(messages)
    fix_text = extract_text(response.content)

    fix_instruction = HumanMessage(content=build_fixer_instruction(current_retry, fix_text))

    return {
        "retry_count": current_retry,
        "fixer_analysis": fix_text,
        "messages": [fix_instruction],
    }


# =====================================================================
# 11. Summarizer Node (Technical Reporter & Streamer)
# =====================================================================

def summarizer_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Summarizer Node:
    Compiles verified findings and streams the final completion report based on task_type and execution_status.
    """
    llm = get_cached_llm()
    task = state.get("task", "")
    plan = state.get("plan", "")
    task_type = state.get("task_type", "conversation")
    execution_status = state.get("execution_status", "completed")
    test_results = state.get("test_results", "")
    test_passed = state.get("test_passed", True)
    modified_files = state.get("modified_files", [])
    coder_findings = state.get("coder_findings", [])
    tool_history = list(state.get("tool_execution_history", []))

    # Collect tool records from conversation
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    updated_history = _collect_new_tool_records(state.get("messages", []), tool_history, task_type, workspace_root)

    # Extract all relevant conversation insights
    conversation_highlights: List[str] = []
    for msg in state.get("messages", []):
        if isinstance(msg, AIMessage):
            content_str = extract_text(msg.content).strip()
            if content_str and not (hasattr(msg, "tool_calls") and msg.tool_calls):
                conversation_highlights.append(content_str)
        elif getattr(msg, "type", "") == "tool":
            tool_name = getattr(msg, "name", "tool")
            content_str = extract_text(getattr(msg, "content", "")).strip()
            if content_str:
                preview = content_str[:600] + ("..." if len(content_str) > 600 else "")
                conversation_highlights.append(f"Tool Output ({tool_name}): {preview}")

    findings_summary = "\n\n".join(conversation_highlights) if conversation_highlights else "\n\n".join(coder_findings)

    is_code_modified = bool(modified_files) and task_type == "code_change"

    summary_prompt = build_summarizer_prompt(
        task=task,
        findings_summary=findings_summary,
        plan=plan,
        modified_files=modified_files,
        test_passed=test_passed,
        test_results=test_results,
        is_code_modified=is_code_modified,
    )

    messages = [
        SystemMessage(content=SUMMARIZER_SYSTEM_PROMPT),
        HumanMessage(content=summary_prompt),
    ]

    try:
        from app.ui.markdown_stream import stream_live_markdown

        def _token_generator():
            for chunk in llm.stream(messages):
                token = extract_text(chunk.content)
                if token:
                    yield token

        full_summary = stream_live_markdown(_token_generator())
    except Exception:
        response = llm.invoke(messages)
        full_summary = extract_text(response.content)

    return {
        "final_summary": full_summary,
        "execution_status": execution_status,
        "tool_execution_history": updated_history,
    }

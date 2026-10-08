import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from typing import Dict, Any, Union, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.core.llm import get_cached_llm, get_cached_coder_llm, resilient_llm_invoke
from app.core.storage import log_audit_event
from app.integrations.tools import ALL_TOOLS
from app.integrations.tools.terminal_tools import run_pytest
from app.modules.coding_agent.state import CodingAgentState
from app.modules.coding_agent.prompts import (
    PLANNER_SYSTEM_PROMPT,
    CODER_SYSTEM_PROMPT,
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


def planner_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Planner Node (Senior Software Architect):
    Inspects repository tree context and designs a comprehensive implementation blueprint.
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


def coder_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Coder Node (Senior Software Engineer):
    Directly inspects repository files with tools, implements code changes,
    or formulates explanations based on real evidence.
    """
    task = state.get("task", "")
    plan = state.get("plan", "")
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    messages: List[BaseMessage] = list(state.get("messages", []))
    findings = list(state.get("coder_findings", []))
    modified_files = list(state.get("modified_files", []))

    # Prepend architectural blueprint context if coming from Planner
    if plan and not any("Architect Blueprint:" in getattr(m, "content", "") for m in messages if isinstance(m, HumanMessage)):
        plan_context = HumanMessage(content=build_coder_plan_context(plan))
        messages.append(plan_context)

    # Format execution history for the LLM
    formatted_messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + messages

    try:
        response = resilient_llm_invoke(formatted_messages, tools=ALL_TOOLS)
    except Exception:
        llm = get_cached_coder_llm(ALL_TOOLS)
        response = llm.invoke(formatted_messages)

    # Sanitize tool calls to protect ToolNode against hallucinated tool names
    valid_tool_names = {t.name for t in ALL_TOOLS}
    if hasattr(response, "tool_calls") and response.tool_calls:
        sanitized_calls = [tc for tc in response.tool_calls if tc.get("name") in valid_tool_names]
        response.tool_calls = sanitized_calls

        # Track any newly modified files if valid write/patch/delete tool calls are requested
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

    # Record text insights
    content_str = extract_text(response.content).strip()
    if content_str and not (hasattr(response, "tool_calls") and response.tool_calls):
        findings.append(content_str)

    return {
        "messages": [response],
        "coder_findings": findings,
        "modified_files": modified_files,
    }



# LangGraph Prebuilt Tool Node
tool_node = ToolNode(ALL_TOOLS)


def validator_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Validator Node (QA & Test Inspector):
    Executes pytest in a background subprocess to verify implementation correctness.
    """
    test_cmd = state.get("test_command", "")
    task = state.get("task", "")

    # Execute pytest suite
    test_output = run_pytest.invoke({"test_path": test_cmd})
    passed = "✅ Tests passed" in test_output

    return {
        "test_passed": passed,
        "test_results": test_output,
    }


def fixer_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Fixer Node (Diagnostic Root-Cause Debugger):
    Triggered upon test failure. Analyzes failure tracebacks, isolates the root bug,
    and returns precise surgical fix instructions back to the Coder.
    """
    llm = get_cached_llm()
    task = state.get("task", "")
    plan = state.get("plan", "")
    test_results = state.get("test_results", "")
    current_retry = state.get("retry_count", 0) + 1
    max_retries = getattr(settings, "MAX_RETRY_COUNT", 3)

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


def summarizer_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Summarizer Node (Pure Backend Cognitive Worker):
    Compiles verified workflow results and queries the LLM for the final structured response.
    """
    llm = get_cached_llm()
    task = state.get("task", "")
    plan = state.get("plan", "")
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))
    test_results = state.get("test_results", "")
    test_passed = state.get("test_passed", True)
    retry_count = state.get("retry_count", 0)
    coder_findings = state.get("coder_findings", [])

    # Extract all relevant conversation insights & tool results
    conversation_highlights: List[str] = []
    for msg in state.get("messages", []):
        if isinstance(msg, AIMessage):
            content_str = extract_text(msg.content).strip()
            if content_str and not (hasattr(msg, "tool_calls") and msg.tool_calls):
                conversation_highlights.append(f"Coder Analysis:\n{content_str}")
        elif getattr(msg, "type", "") == "tool":
            tool_name = getattr(msg, "name", "tool")
            content_str = extract_text(getattr(msg, "content", "")).strip()
            if content_str:
                preview = content_str[:600] + ("..." if len(content_str) > 600 else "")
                conversation_highlights.append(f"Tool Result ({tool_name}):\n{preview}")

    findings_summary = "\n\n".join(conversation_highlights)
    if not findings_summary and coder_findings:
        findings_summary = "\n\n".join(coder_findings)

    # Reconcile agent claimed files with actual disk/git modifications
    claimed_files = list(state.get("modified_files", []))
    actual_git_files = get_actual_git_modified_files(workspace_root)
    
    # Merge and deduplicate
    all_modified = list(claimed_files)
    for af in actual_git_files:
        if af not in all_modified:
            all_modified.append(af)

    is_code_modified = bool(all_modified)

    summary_prompt = build_summarizer_prompt(
        task=task,
        findings_summary=findings_summary,
        plan=plan,
        modified_files=all_modified,
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

    log_audit_event({
        "agent": "summarizer_node",
        "task": task[:200],
        "claimed_files": claimed_files,
        "actual_git_files": actual_git_files,
        "test_passed": test_passed,
        "summary_length": len(full_summary),
    }, workspace_root=workspace_root)

    return {"final_summary": full_summary, "modified_files": all_modified}






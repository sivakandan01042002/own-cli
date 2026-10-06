import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from typing import Dict, Any, Union, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.core.llm import get_cached_llm, get_cached_coder_llm
from app.integrations.tools import ALL_TOOLS
from app.integrations.tools.terminal_tools import run_pytest
from app.modules.coding_agent.state import CodingAgentState
from app.modules.coding_agent.prompts import (
    PLANNER_SYSTEM_PROMPT,
    CODER_SYSTEM_PROMPT,
    FIXER_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
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
    llm = get_cached_llm()
    task = state.get("task", "")
    repo_tree = state.get("repository_tree", "")
    workspace_root = state.get("workspace_root", str(settings.WORKSPACE_ROOT))

    planner_prompt = (
        f"Workspace Root: {workspace_root}\n\n"
        f"Repository Structure:\n{repo_tree}\n\n"
        f"User Task to Plan:\n{task}"
    )

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=planner_prompt),
    ]

    response = llm.invoke(messages)
    plan_text = extract_text(response.content)

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
    llm = get_cached_coder_llm(ALL_TOOLS)
    task = state.get("task", "")
    plan = state.get("plan", "")
    messages: List[BaseMessage] = list(state.get("messages", []))
    findings = list(state.get("coder_findings", []))
    modified_files = list(state.get("modified_files", []))

    # Prepend architectural blueprint context if coming from Planner
    if plan and not any("Architect Blueprint:" in getattr(m, "content", "") for m in messages if isinstance(m, HumanMessage)):
        plan_context = HumanMessage(
            content=f"Architect Blueprint for Implementation:\n{plan}\n\nPlease inspect the relevant files and implement the requested changes or unit tests."
        )
        messages.append(plan_context)

    # Format execution history for the LLM
    formatted_messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + messages

    response = llm.invoke(formatted_messages)

    # Track any newly modified files if tool calls are requested
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls:
            name = tool_call.get("name", "")
            args = tool_call.get("args", {})
            if name in ("write_file", "delete_file"):
                file_path = args.get("file_path")
                if file_path and file_path not in modified_files:
                    modified_files.append(file_path)

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
    Fixer Node (Root-Cause Debugger):
    Triggered upon test failure. Analyzes tracebacks, isolates true root causes,
    and returns precise fix instructions back to the Coder.
    """
    llm = get_cached_llm()
    task = state.get("task", "")
    plan = state.get("plan", "")
    test_results = state.get("test_results", "")
    current_retry = state.get("retry_count", 0) + 1

    prompt_content = (
        f"User Task: {task}\n\n"
        f"Implementation Plan:\n{plan}\n\n"
        f"Pytest Failure Output:\n{test_results}\n\n"
        f"Attempt Number: {current_retry}\n\n"
        f"Please analyze the failure traceback, identify the exact bug in the codebase, and provide precise fix instructions for the Coder."
    )

    messages = [
        SystemMessage(content=FIXER_SYSTEM_PROMPT),
        HumanMessage(content=prompt_content),
    ]

    response = llm.invoke(messages)
    fix_text = extract_text(response.content)

    fix_instruction = HumanMessage(
        content=f"⚠️ Test Failure Analysis & Fix Instructions (Attempt {current_retry}):\n{fix_text}"
    )

    return {
        "retry_count": current_retry,
        "fixer_analysis": fix_text,
        "messages": [fix_instruction],
    }


def summarizer_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Summarizer Node (Pure Backend Worker):
    Compiles verified workflow results and queries the LLM for the final structured response.
    Returns state without performing any terminal I/O.
    """
    llm = get_cached_llm()
    task = state.get("task", "")
    plan = state.get("plan", "")
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

    modified_files = state.get("modified_files", [])
    is_code_modified = bool(modified_files)

    if not is_code_modified and not test_results:
        summary_prompt = (
            f"User Request:\n{task}\n\n"
            f"Verified Codebase Inspection & Findings:\n{findings_summary or 'No specific output recorded.'}\n\n"
            f"Instruction: Directly answer the user's inquiry with clear, structured Markdown (bullet points, bold highlights, code formatting, and component comparisons). Do NOT output empty boilerplate headers like '## Changes: None' or '## Validation: None'."
        )
    else:
        summary_prompt = (
            f"User Request:\n{task}\n\n"
            f"Architecture Plan:\n{plan or 'N/A'}\n\n"
            f"Implementation Findings:\n{findings_summary or 'Completed.'}\n\n"
            f"Modified Files: {', '.join(modified_files) if modified_files else 'None'}\n"
            f"Test Verification: {'Passed ✅' if test_passed else 'Failed ❌'}\n"
            f"Test Execution Output:\n{test_results or 'N/A'}\n\n"
            f"Instruction: Present a clear completion report with implemented features, changed files, and test results."
        )

    messages = [
        SystemMessage(content=SUMMARIZER_SYSTEM_PROMPT),
        HumanMessage(content=summary_prompt),
    ]

    response = llm.invoke(messages)
    full_summary = extract_text(response.content)

    return {"final_summary": full_summary}

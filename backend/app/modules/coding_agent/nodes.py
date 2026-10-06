import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from typing import Dict, Any, Union, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.prebuilt import ToolNode
from rich.console import Console

from app.ui.markdown_stream import stream_live_markdown

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

console = Console()


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
    Architect Node: Analyzes the user's task in context of the workspace root
    and repository tree, producing a structured implementation blueprint.
    """
    llm = get_cached_llm()
    workspace_root = state.get("workspace_root") or str(settings.WORKSPACE_ROOT)
    repo_tree = state.get("repository_tree") or "Not available."
    task = state.get("task", "")

    prompt_content = (
        f"Workspace Root: {workspace_root}\n\n"
        f"Repository Structure:\n{repo_tree}\n\n"
        f"User Task:\n{task}"
    )

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=prompt_content),
    ]

    response = llm.invoke(messages)
    plan_text = extract_text(response.content)

    return {
        "plan": plan_text,
        "messages": [response],
        "retry_count": 0,
        "test_passed": False,
        "modified_files": [],
        "coder_findings": [],
    }


def coder_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Coder Node: Inspects repository files, executes the blueprint, or performs code modifications.
    Uses singleton cached tool-bound LLM instance.
    """
    coder_llm = get_cached_coder_llm(ALL_TOOLS)
    system_msg = SystemMessage(content=CODER_SYSTEM_PROMPT)

    history: List[BaseMessage] = list(state.get("messages", []))
    if not history:
        workspace_root = state.get("workspace_root") or str(settings.WORKSPACE_ROOT)
        repo_tree = state.get("repository_tree") or ""
        task = state.get("task", "")
        context_str = (
            f"Workspace Root: {workspace_root}\n\n"
            f"Repository Structure:\n{repo_tree}\n\n"
            f"User Task:\n{task}"
        )
        history = [HumanMessage(content=context_str)]

    messages = [system_msg] + history
    response = coder_llm.invoke(messages)

    # Track coder text findings for summarizer
    response_text = extract_text(response.content)
    findings = list(state.get("coder_findings", []))
    if response_text.strip() and not (hasattr(response, "tool_calls") and response.tool_calls):
        findings.append(response_text.strip())

    return {
        "messages": [response],
        "coder_findings": findings,
    }


# Prebuilt LangGraph ToolNode that executes any tool calls on disk/web
tool_node = ToolNode(ALL_TOOLS)


def validator_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Validator Node: Reads test target from state and executes pytest in the workspace.
    """
    target_test = state.get("test_command") or ""
    test_output = run_pytest.invoke({"test_path": target_test})

    # Check if pytest exited with code 0 and has no failure keywords
    passed = "Exit Code: 0" in test_output and "failed" not in test_output.lower()

    # If exit code 5 (no tests collected) and no specific test target was given, pass cleanly
    if not passed and "Exit Code: 5" in test_output and not target_test:
        passed = True

    return {
        "test_results": test_output,
        "test_passed": passed,
    }


def fixer_node(state: CodingAgentState) -> Dict[str, Any]:
    """
    Fixer / Debugger Node: Analyzes test failure tracebacks and provides root-cause diagnosis.
    """
    llm = get_cached_llm()
    current_retry = state.get("retry_count", 0) + 1
    test_results = state.get("test_results", "No test output available.")

    prompt_content = (
        f"The tests failed on attempt {current_retry}.\n\n"
        f"Here is the pytest failure output and traceback:\n"
        f"```text\n{test_results}\n```\n\n"
        f"Please analyze the exact root cause and give the Coder precise fix instructions."
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
    Summarizer Node with Real-Time Token Streaming:
    Streams completion report tokens directly to stdout while accumulating the full
    response for state and Redis persistence.
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

    def token_generator():
        try:
            for chunk in llm.stream(messages):
                token = extract_text(chunk.content)
                if token:
                    yield token
        except Exception:
            response = llm.invoke(messages)
            yield extract_text(response.content)

    full_summary = stream_live_markdown(token_generator(), console=console)
    return {"final_summary": full_summary}

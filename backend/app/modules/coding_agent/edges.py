from typing import Literal
from app.core.config import settings
from app.modules.coding_agent.state import CodingAgentState


def route_initial_intent(state: CodingAgentState) -> str:
    """
    Analyzes user task intent:
    - If pure question, explanation, or code inspection: route directly to 'coder' to answer without planning blueprint.
    - If coding, feature creation, refactoring, or bug fixing: route to 'planner'.
    """
    task = state.get("task", "").strip().lower()

    # Question & explanation intent indicators
    question_starters = (
        "what", "how", "why", "where", "can you tell", "tell me",
        "explain", "describe", "show me", "help me understand",
        "list the", "what's the purpose", "what is the purpose"
    )

    is_question = any(task.startswith(qs) or f" {qs}" in task for qs in question_starters)
    is_build_action = any(act in task for act in ("build", "create", "implement", "add", "write", "fix", "refactor", "delete", "remove"))

    if is_question and not is_build_action:
        return "coder"

    return "planner"


def should_continue_coder(state: CodingAgentState) -> str:
    """
    Checks if Coder emitted tool calls, or if done, decides whether to validate with pytest.
    
    Returns:
        - 'tools': If tool calls are pending execution.
        - 'validator': If code files were created/modified and need pytest verification.
        - 'summarizer': If no files were modified (read-only Q&A or explanation), skipping pytest completely.
    """
    messages = state.get("messages", [])
    if not messages:
        return "summarizer"

    last_message = messages[-1]

    # If the LLM requested a tool execution (e.g. write_file, read_file)
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tools"

    # Check if any file was written or modified in the conversation
    has_file_writes = False
    for msg in messages:
        # Check tool calls on AI messages
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                if tc.get("name") in ("write_file", "delete_file"):
                    has_file_writes = True
                    break
        if has_file_writes:
            break

    # If code was actually modified or a test command is specified, validate with pytest
    if has_file_writes or state.get("test_command"):
        return "validator"

    # Otherwise, it was an inquiry/explanation: skip pytest and go directly to summarizer!
    return "summarizer"


def should_retry_or_finish(state: CodingAgentState) -> str:
    """
    Checks if tests passed or if maximum retry count is reached.
    
    Returns:
        'summarizer' if tests passed or max retries reached, otherwise 'fixer'.
    """
    # If tests passed successfully, go straight to summary
    if state.get("test_passed", False):
        return "summarizer"

    # Safety guardrail: stop after max retries
    if state.get("retry_count", 0) >= getattr(settings, "MAX_RETRY_COUNT", 3):
        return "summarizer"

    # Otherwise, diagnose failure and fix
    return "fixer"

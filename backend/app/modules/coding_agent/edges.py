from app.core.config import settings
from app.modules.coding_agent.state import CodingAgentState


def should_continue_coder(state: CodingAgentState) -> str:
    """
    Checks if the Coder agent wants to execute a tool call, or is ready for validation.
    
    Returns:
        'tools' if there are tool calls to execute, otherwise 'validator'.
    """
    messages = state.get("messages", [])
    if not messages:
        return "validator"

    last_message = messages[-1]

    # If the LLM requested a tool execution (e.g. write_file, read_file)
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tools"

    # Otherwise, the coder is finished writing files; proceed to testing
    return "validator"


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
    if state.get("retry_count", 0) >= settings.MAX_RETRY_COUNT:
        return "summarizer"

    # Otherwise, diagnose failure and fix
    return "fixer"


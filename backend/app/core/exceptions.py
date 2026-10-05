"""
Centralized exception classes and clean 2-line error formatting for QueryNest.
"""

class QueryNestBaseException(Exception):
    """Base exception for all QueryNest application errors."""
    def __init__(self, message: str, resolution_hint: str = ""):
        super().__init__(message)
        self.message = message
        self.resolution_hint = resolution_hint


class ModelProviderError(QueryNestBaseException):
    """Raised when an LLM provider encounters an API, 404, or 429 rate limit error."""
    pass


class SafetyGuardrailError(QueryNestBaseException):
    """Raised when an input violates safety rules or attempts prompt injection."""
    pass


class ToolExecutionError(QueryNestBaseException):
    """Raised when a file or terminal tool fails during execution."""
    pass


def format_error_for_user(error: Exception) -> str:
    """
    Translates raw Python/API exceptions into clean, 2-line actionable user messages.
    """
    err_str = str(error)

    if "tool_use_failed" in err_str or "Failed to parse tool call" in err_str:
        return (
            "Tool Call Error: The model produced a malformed command string.\n"
            "   [dim]Suggestion:[/] Ask to inspect specific files directly, or switch with [bold cyan]/model gemini[/bold cyan]."
        )

    elif "404" in err_str or "model_not_found" in err_str:
        return (
            "Model Unavailable: The configured model ID is currently offline or retired.\n"
            "   [dim]Suggestion:[/] Switch active provider with [bold cyan]/model gemini[/bold cyan] or [bold cyan]/model groq[/bold cyan]."
        )

    elif "429" in err_str or "rate_limit" in err_str.lower():
        return (
            "Rate Limit: Request quota temporarily reached on free tier.\n"
            "   [dim]Suggestion:[/] Switch with [bold cyan]/model gemini[/bold cyan] or wait a few seconds."
        )

    elif "api_key" in err_str.lower() or "authentication" in err_str.lower() or "401" in err_str:
        return (
            "Authentication Error: The API key in backend/.env is missing or invalid.\n"
            "   [dim]Suggestion:[/] Verify GEMINI_API_KEY or GROQ_API_KEY in backend/.env."
        )

    elif isinstance(error, QueryNestBaseException):
        return error.message

    # Truncate unexpected long errors to a concise 2-line preview
    preview = err_str.split("\n")[0][:120]
    return f"Execution Error: {preview}\n   [dim]Suggestion:[/] Try rephrasing your request or inspecting specific files."

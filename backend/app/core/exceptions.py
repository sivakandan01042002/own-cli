"""
Centralized exception classes and error formatting for QueryNest.
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
    Translates raw Python/API exceptions into clean, actionable user messages.
    """
    err_str = str(error)

    if "404" in err_str or "model_not_found" in err_str:
        return "The configured model ID is unavailable or retired. Switch with [bold cyan]/model gemini[/bold cyan] or [bold cyan]/model groq[/bold cyan]."

    elif "429" in err_str or "rate_limit" in err_str.lower():
        return "The free tier request quota was temporarily reached. Switch with [bold cyan]/model gemini[/bold cyan] or wait a moment."

    elif "api_key" in err_str.lower() or "authentication" in err_str.lower():
        return "The API key in .env is missing or invalid. Verify GEMINI_API_KEY or GROQ_API_KEY."

    elif isinstance(error, QueryNestBaseException):
        return error.message

    return f"Unexpected Error: {err_str}"



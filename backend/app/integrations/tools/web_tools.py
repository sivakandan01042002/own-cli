import hashlib
import os
import sys
import contextlib
import warnings

# Suppress library deprecation and runtime warnings globally
warnings.filterwarnings("ignore")

from langchain_core.tools import tool
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from app.core.redis_client import get_cached_response, set_cached_response


@contextlib.contextmanager
def silence_stderr():
    """Redirects stderr to devnull to silence forced library warnings."""
    old_stderr = sys.stderr
    try:
        with open(os.devnull, "w") as null:
            sys.stderr = null
            yield
    finally:
        sys.stderr = old_stderr


@tool
def search_web(query: str, max_results: int = 5) -> str:
    """
    Searches the internet via DuckDuckGo for up-to-date documentation, API references, or bug fixes.
    Use this tool when you need information not available in the local project codebase.
    Results are automatically cached in Redis to conserve network and rate limits.
    
    Args:
        query: The search query string (e.g., 'FastAPI middleware CORS example' or 'pytest fixture syntax').
        max_results: Maximum number of search results to return (default 5).
        
    Returns:
        A formatted string containing titles, snippets, and URLs of the top search results.
    """
    # Check Redis cache first
    cache_hash = hashlib.md5(f"websearch:{query}:{max_results}".encode("utf-8")).hexdigest()
    cached = get_cached_response(cache_hash)
    if cached:
        return cached

    try:
        results = []
        with silence_stderr():
            with DDGS() as ddgs:
                raw_results = ddgs.text(query, max_results=max_results)
            for r in raw_results:
                title = r.get("title", "No Title")
                href = r.get("href", "No URL")
                body = r.get("body", "No Summary")
                results.append(
                    f"📌 Title: {title}\n"
                    f"🔗 URL: {href}\n"
                    f"📝 Summary: {body}\n"
                )

        if not results:
            return f"No search results found for query: '{query}'."

        formatted_output = "\n---\n".join(results)
        # Cache in Redis for 2 hours (7200 seconds)
        set_cached_response(cache_hash, formatted_output, ttl=7200)
        return formatted_output

    except Exception as e:
        return f"Error executing web search for '{query}': {str(e)}"

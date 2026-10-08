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
                    f"Title: {title}\n"
                    f"URL: {href}\n"
                    f"Summary: {body}\n"
                )

        if not results:
            return f"No search results found for query: '{query}'."

        formatted_output = "\n---\n".join(results)
        # Cache in Redis for 2 hours (7200 seconds)
        set_cached_response(cache_hash, formatted_output, ttl=7200)
        return formatted_output

    except Exception as e:
        return f"Error executing web search for '{query}': {str(e)}"


@tool
def read_doc_url(url: str, max_length: int = 5000) -> str:
    """
    Fetches online documentation, GitHub READMEs, API guides, or web pages and extracts structured text.
    Use this tool when you need full documentation from a specific web link.
    Results are cached in Redis to prevent duplicate network calls.

    Args:
        url: The web URL to fetch (e.g. 'https://raw.githubusercontent.com/...' or 'https://fastapi.tiangolo.com/...').
        max_length: Maximum characters of text to return (default 5000).

    Returns:
        Structured text content extracted from the webpage.
    """
    import re
    import urllib.request

    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        return f"Error: Invalid URL '{url}'. Must start with http:// or https://"

    cache_hash = hashlib.md5(f"docurl:{clean_url}".encode("utf-8")).hexdigest()
    cached = get_cached_response(cache_hash)
    if cached:
        return f"[Cached Documentation for {clean_url}]\n{cached}"

    try:
        req = urllib.request.Request(
            clean_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QueryNest/1.0",
                "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status != 200:
                return f"Error: Failed to fetch URL (HTTP status {response.status})."
            raw_bytes = response.read()

        text = raw_bytes.decode("utf-8", errors="replace")

        # Strip scripts, styles, and tags if HTML
        if "<html" in text.lower() or "<body" in text.lower():
            text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"<nav[\s\S]*?</nav>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"<footer[\s\S]*?</footer>", "", text, flags=re.IGNORECASE)
            # Replace breaks and headers
            text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n### \1\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
            # Remove remaining tags
            text = re.sub(r"<[^>]+>", "", text)
            # Unescape entities
            text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')

        # Clean up excessive blank lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned = "\n".join(lines)

        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length] + f"\n\n... (truncated, total length {len(text)} chars)"

        # Cache in Redis for 24 hours
        set_cached_response(cache_hash, cleaned, ttl=86400)
        return cleaned

    except Exception as e:
        return f"Error fetching documentation from '{url}': {str(e)}"


from langchain_core.tools import tool
from duckduckgo_search import DDGS

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """
    Searches the internet via DuckDuckGo for up-to-date documentation, API references, or bug fixes.
    Use this tool when you need information not available in the local project codebase.
    
    Args:
        query: The search query string (e.g., 'FastAPI middleware CORS example' or 'pytest fixture syntax').
        max_results: Maximum number of search results to return (default 5).
        
    Returns:
        A formatted string containing titles, snippets, and URLs of the top search results.
    """
    try:
        results = []
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

        return "\n---\n".join(results)

    except Exception as e:
        return f"Error executing web search for '{query}': {str(e)}"

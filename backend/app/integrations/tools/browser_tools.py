"""Browser interaction and automated UI inspection tools for QueryNest CLI."""
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any
from langchain_core.tools import tool

from app.core.config import settings

# Global active browser state cache
_ACTIVE_BROWSER_STATE: Dict[str, Any] = {
    "current_url": None,
    "last_page_content": None,
    "last_screenshot_path": None,
}


def _get_playwright_page():
    """Lazily initializes Playwright Chromium browser page if available."""
    try:
        from playwright.sync_api import sync_playwright
        if "_pw_instance" not in _ACTIVE_BROWSER_STATE:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            _ACTIVE_BROWSER_STATE["_pw_instance"] = pw
            _ACTIVE_BROWSER_STATE["_pw_browser"] = browser
            _ACTIVE_BROWSER_STATE["_pw_page"] = page
        return _ACTIVE_BROWSER_STATE.get("_pw_page")
    except ImportError:
        return None
    except Exception:
        return None


@tool
def browser_open(url: str, wait_seconds: int = 2) -> str:
    """
    Opens a web page, live web application, or local development server (e.g. 'http://localhost:3000') in a headless browser.
    Use this tool to test frontend web UIs, verify running local servers, or interact with web apps.

    Args:
        url: The URL to navigate to (e.g. 'http://localhost:5173' or 'https://example.com').
        wait_seconds: Number of seconds to wait for network/DOM rendering (default 2).

    Returns:
        Summary of the loaded page title, HTTP status, and DOM layout structure.
    """
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = f"http://{clean_url}"

    _ACTIVE_BROWSER_STATE["current_url"] = clean_url

    # 1. Try Playwright for real JS execution
    page = _get_playwright_page()
    if page is not None:
        try:
            page.goto(clean_url, timeout=30000, wait_until="networkidle")
            time.sleep(wait_seconds)
            title = page.title()
            content = page.content()
            _ACTIVE_BROWSER_STATE["last_page_content"] = content
            return f"Successfully opened '{clean_url}' (Title: '{title}'). DOM rendered and ready for interaction."
        except Exception as e:
            return f"Error opening '{clean_url}' with browser: {str(e)}"

    # 2. Lightweight HTTP fallback
    try:
        req = urllib.request.Request(
            clean_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QueryNest/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            raw_html = resp.read().decode("utf-8", errors="replace")

        _ACTIVE_BROWSER_STATE["last_page_content"] = raw_html
        return f"Successfully loaded '{clean_url}' (HTTP {status}, {len(raw_html)} bytes). [Note: Install 'playwright' for full JavaScript rendering]"
    except Exception as e:
        return f"Error connecting to '{clean_url}': {str(e)}"


@tool
def browser_screenshot(output_path: str = "") -> str:
    """
    Captures a high-resolution screenshot of the currently active browser page and saves it to disk.
    The captured image can then be inspected with 'inspect_image' to detect visual layout bugs or styling issues.

    Args:
        output_path: Optional relative file path to save the screenshot (e.g. 'assets/ui_screen.png').

    Returns:
        File path of the saved screenshot image.
    """
    from app.core.guardrails import assert_inside_workspace

    if not output_path or not output_path.strip():
        timestamp = int(time.time())
        target_rel = Path("assets") / f"screenshot_{timestamp}.png"
        target_file = (settings.WORKSPACE_ROOT / target_rel).resolve()
    else:
        target_file = assert_inside_workspace(output_path)

    target_file.parent.mkdir(parents=True, exist_ok=True)

    page = _get_playwright_page()
    if page is not None:
        try:
            page.screenshot(path=str(target_file), full_page=True)
            _ACTIVE_BROWSER_STATE["last_screenshot_path"] = str(target_file)
            rel_path = target_file.relative_to(root).as_posix()
            return f"Successfully captured browser screenshot and saved to '{rel_path}'."
        except Exception as e:
            return f"Error capturing browser screenshot: {str(e)}"

    return (
        "Notice: Headless screenshot capture requires Playwright. "
        "Run 'pip install playwright && playwright install chromium' in your terminal to enable live browser screenshots."
    )


@tool
def browser_click(selector: str) -> str:
    """
    Clicks on an interactive button, link, tab, or input element on the currently open browser page.

    Args:
        selector: CSS selector, button text, or element text to click (e.g. '#submit-btn', 'button:has-text(\"Login\")', or 'a.nav-link').

    Returns:
        Confirmation of click action.
    """
    page = _get_playwright_page()
    if page is None:
        return "Notice: Browser element clicks require Playwright ('pip install playwright && playwright install chromium')."

    try:
        page.click(selector, timeout=10000)
        time.sleep(1)
        return f"Successfully clicked element matching '{selector}'."
    except Exception as e:
        return f"Error clicking element '{selector}': {str(e)}"


@tool
def browser_type(selector: str, text: str) -> str:
    """
    Types text into a form input, textarea, or search box on the currently open browser page.

    Args:
        selector: CSS selector of the input field (e.g. 'input[name=\"search\"]' or '#email').
        text: The string to type into the field.

    Returns:
        Confirmation of text entry.
    """
    page = _get_playwright_page()
    if page is None:
        return "Notice: Browser text input requires Playwright ('pip install playwright && playwright install chromium')."

    try:
        page.fill(selector, text, timeout=10000)
        return f"Successfully typed text into '{selector}'."
    except Exception as e:
        return f"Error typing into '{selector}': {str(e)}"

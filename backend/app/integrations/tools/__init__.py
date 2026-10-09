from typing import TypedDict, Optional, Any, Dict

from app.integrations.tools.file_tools import (
    list_directory,
    read_file,
    write_file,
    delete_file,
    search_code,
    patch_file,
)
from app.integrations.tools.git_tools import (
    run_git_command,
    run_git_read_only,
)
from app.integrations.tools.terminal_tools import (
    run_terminal_command,
    run_pytest,
)
from app.integrations.tools.web_tools import (
    search_web,
    read_doc_url,
)
from app.integrations.tools.image_tools import (
    inspect_image,
    generate_image,
)
from app.integrations.tools.browser_tools import (
    browser_open,
    browser_screenshot,
    browser_click,
    browser_type,
)

class ToolResult(TypedDict, total=False):
    success: bool
    output: str
    error: Optional[str]
    metadata: Optional[Dict[str, Any]]


# 1. Direct Action Tools (Media / Web / Browser) - Zero file writes, zero shell execution
DIRECT_ACTION_TOOLS = [
    generate_image,
    search_web,
    read_doc_url,
    inspect_image,
    browser_open,
    browser_screenshot,
    browser_click,
    browser_type,
]

# 2. Read-Only Code Inspection Tools - Strictly read-only queries
READ_ONLY_TOOLS = [
    read_file,
    search_code,
    list_directory,
    run_git_read_only,
]

# 3. Full 17-Tool Suite for Coder Agent
CODER_TOOLS = [
    list_directory,
    read_file,
    write_file,
    delete_file,
    search_code,
    patch_file,
    run_git_command,
    run_terminal_command,
    run_pytest,
    search_web,
    read_doc_url,
    inspect_image,
    generate_image,
    browser_open,
    browser_screenshot,
    browser_click,
    browser_type,
]

ALL_TOOLS = CODER_TOOLS

__all__ = [
    "DIRECT_ACTION_TOOLS",
    "READ_ONLY_TOOLS",
    "CODER_TOOLS",
    "ALL_TOOLS",
    "list_directory",
    "read_file",
    "write_file",
    "delete_file",
    "search_code",
    "patch_file",
    "run_git_command",
    "run_git_read_only",
    "run_terminal_command",
    "run_pytest",
    "search_web",
    "read_doc_url",
    "inspect_image",
    "generate_image",
    "browser_open",
    "browser_screenshot",
    "browser_click",
    "browser_type",
]

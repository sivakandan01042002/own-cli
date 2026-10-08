from typing import Tuple
from rich.console import Console

from rich.prompt import Prompt

console = Console()


def prompt_plan_permission() -> Tuple[str, str]:
    """
    Renders an interactive 3-option permission dialog after plan generation using arrow-key navigation.
    
    Returns:
        tuple: (action: 'proceed' | 'all' | 'cancel', feedback: str)
    """
    from app.ui.menu import show_interactive_menu

    items = [
        ("proceed", "1. Yes, Do It", "(Execute tools & code)"),
        ("all", "2. Yes, Do for All Upcoming in this Session", "(Auto-accept all remaining steps)"),
        ("cancel", "3. No, Cancel", "(Abort workflow)"),
    ]

    choice = show_interactive_menu(
        title="Proceed with this implementation plan?",
        items=items,
        instruction="Use ↑/↓ to navigate, Enter to select, Esc to cancel",
    )

    if not choice or choice == "cancel":
        return "cancel", ""

    return choice, ""


def prompt_tool_permission(tools: list) -> Tuple[str, str]:
    """
    Renders tool action badges and an interactive 3-option arrow-key permission picker before tool execution.
    
    Returns:
        tuple: (action: 'proceed' | 'all' | 'cancel', feedback: str)
    """
    from app.ui.renderers import render_action_badge
    from app.ui.menu import show_interactive_menu

    for tc in tools:
        name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
        args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
        render_action_badge(name, args)

    items = [
        ("proceed", "1. Yes, Do It", "(Execute tools)"),
        ("all", "2. Yes, Do for All Upcoming in this Session", "(Auto-accept all remaining steps)"),
        ("cancel", "3. No, Cancel", "(Skip tools and stop)"),
    ]

    choice = show_interactive_menu(
        title="Allow agent to execute these tools?",
        items=items,
        instruction="Use ↑/↓ to navigate, Enter to select, Esc to cancel",
    )

    if not choice or choice == "cancel":
        return "cancel", ""

    return choice, ""



def prompt_confirmation(message: str, default: bool = True) -> bool:
    """Renders a simple yes/no confirmation dialog."""
    try:
        choice = Prompt.ask(
            f"[white]{message}[/white]",
            choices=["y", "n", "yes", "no"],
            default="y" if default else "n",
        ).strip().lower()
        return choice in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def prompt_workspace_trust(workspace_path) -> bool:
    """
    Renders the streamlined workspace trust gate on first launch in an untrusted folder.
    """
    from pathlib import Path
    from app.ui.menu import show_interactive_menu

    native_path = str(Path(workspace_path).resolve())
    styled_title = [
        ("class:ws-title", "Accessing workspace:\n"),
        ("class:ws-path", f"{native_path}\n\n"),
        ("class:ws-desc", "QueryNest requires permission to read, edit, and execute files here.\n"),
    ]

    items = [
        ("trust", "Yes, I trust this folder", ""),
        ("exit", "No, exit", ""),
    ]

    choice = show_interactive_menu(
        title=styled_title,
        items=items,
        instruction="",
        indent_pointer=False,
    )

    return choice == "trust"



def ensure_workspace_trusted_gate(workspace_path: str = "") -> bool:
    """
    Orchestrates the workspace trust gate dialog and updates storage.
    Exits cleanly if trust is not granted.
    """
    import os
    import sys
    from app.core.storage import is_workspace_trusted, trust_workspace, get_canonical_workspace_path

    target_path = get_canonical_workspace_path(workspace_path or os.getcwd())
    if is_workspace_trusted(target_path):
        return True

    trusted = prompt_workspace_trust(target_path)
    if trusted:
        trust_workspace(target_path)
        return True
    else:
        sys.exit(0)




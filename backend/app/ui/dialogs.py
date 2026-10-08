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
    Renders an interactive workspace trust permission picker on first launch in a new folder.
    """
    from app.ui.menu import show_interactive_menu

    items = [
        ("trust", "1. Yes, Trust this folder", "(Store sessions & enable tools)"),
        ("restricted", "2. No, Restricted mode", "(Read-only / temporary session)"),
    ]

    choice = show_interactive_menu(
        title=f"Trust this workspace folder?\n  {str(workspace_path)}",
        items=items,
        instruction="Use ↑/↓ to navigate, Enter to select, Esc to cancel",
    )

    return choice == "trust"


def ensure_workspace_trusted_gate(workspace_path: str = "") -> bool:
    """
    Orchestrates the workspace trust gate dialog and updates storage.
    Keeps CLI startup logic decoupled from dialog rendering.
    """
    import os
    from app.core.storage import is_workspace_trusted, trust_workspace, get_canonical_workspace_path

    target_path = get_canonical_workspace_path(workspace_path or os.getcwd())
    if is_workspace_trusted(target_path):
        return True

    trusted = prompt_workspace_trust(target_path)
    if trusted:
        trust_workspace(target_path)
        console.print("[dim green]✔ Workspace added to trusted list.[/dim green]\n")
        return True
    else:
        console.print("[yellow]Workspace trust not granted. Running in restricted mode.[/yellow]\n")
        return False


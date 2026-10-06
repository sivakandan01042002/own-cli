from typing import Tuple
from rich.console import Console

from rich.prompt import Prompt

console = Console()


def prompt_plan_permission() -> Tuple[str, str]:
    """
    Renders an interactive 2-option permission dialog after plan generation using arrow-key navigation.
    
    Returns:
        tuple: (action: 'proceed' | 'cancel', feedback: str)
    """
    from app.ui.menu import show_interactive_menu

    items = [
        ("proceed", "1. Yes, Do It", "(Execute tools & code)"),
        ("cancel", "2. No, Cancel", "(Abort workflow)"),
    ]

    choice = show_interactive_menu(
        title="Proceed with this implementation plan?",
        items=items,
        instruction="Use ↑/↓ to navigate, Enter to select, Esc to cancel",
    )

    if not choice or choice == "cancel":
        return "cancel", ""

    return "proceed", ""


def prompt_tool_permission(tools: list) -> Tuple[str, str]:
    """
    Renders tool action badges and an interactive 2-option arrow-key permission picker before tool execution.
    
    Returns:
        tuple: (action: 'proceed' | 'cancel', feedback: str)
    """
    from app.ui.renderers import render_action_badge
    from app.ui.menu import show_interactive_menu

    for tc in tools:
        name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
        args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
        render_action_badge(name, args)

    items = [
        ("proceed", "1. Yes, Do It", "(Execute tools)"),
        ("cancel", "2. No, Cancel / Skip", "(Skip tools and stop)"),
    ]

    choice = show_interactive_menu(
        title="Allow agent to execute these tools?",
        items=items,
        instruction="Use ↑/↓ to navigate, Enter to select, Esc to cancel",
    )

    if not choice or choice == "cancel":
        return "cancel", ""

    return "proceed", ""



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

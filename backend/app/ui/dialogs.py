"""Interactive UI dialogs and permission prompt components using Rich."""
from typing import Tuple
from rich.console import Console
from rich.prompt import Prompt

console = Console()


def prompt_plan_permission() -> Tuple[str, str]:
    """
    Renders an interactive permission and confirmation dialog after plan generation.
    
    Returns:
        tuple: (action: 'proceed' | 'cancel' | 'adjust', feedback: str)
    """
    console.print("[bold cyan]Proceed with this implementation plan?[/bold cyan]")
    console.print("  [bold green]1.[/bold green] [white]Yes, Do It[/white] [dim](Execute tools & code)[/dim]")
    console.print("  [bold red]2.[/bold red] [white]No, Cancel[/white] [dim](Abort workflow)[/dim]")
    console.print("  [bold yellow]3.[/bold yellow] [white]Tell me what to do / Adjust plan[/white] [dim](Provide custom instructions)[/dim]\n")

    try:
        choice = Prompt.ask(
            "[bold white]Choice[/bold white]",
            choices=["1", "2", "3", "yes", "no", "cancel", "adjust", "edit", "feedback"],
            default="1",
            show_choices=False,
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "cancel", ""

    if choice in ("2", "no", "cancel"):
        return "cancel", ""
    elif choice in ("3", "adjust", "edit", "feedback"):
        try:
            feedback = Prompt.ask("\n[bold yellow]Enter instructions / adjustments[/bold yellow]").strip()
        except (EOFError, KeyboardInterrupt):
            feedback = ""
        return "adjust", feedback

    return "proceed", ""


def prompt_confirmation(message: str, default: bool = True) -> bool:
    """Renders a simple yes/no confirmation dialog."""
    try:
        choice = Prompt.ask(
            f"[bold cyan]{message}[/bold cyan]",
            choices=["y", "n", "yes", "no"],
            default="y" if default else "n",
        ).strip().lower()
        return choice in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False

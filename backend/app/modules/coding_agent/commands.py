import sys
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from app.core.config import settings
from app.core.redis_client import get_session_records, clear_session_records
from app.integrations.tools import ALL_TOOLS

console = Console()

# Session task history tracking
task_history: List[str] = []

# List of available slash commands for autocompletion
SLASH_COMMANDS = [
    "/help",
    "/model",
    "/model gemini",
    "/model groq",
    "/session",
    "/sessions",
    "/tools",
    "/history",
    "/clear",
    "/exit",
    "/quit",
]


def record_task_in_history(task: str):
    """Records an executed coding task into in-memory session history."""
    task_history.append(task)


def handle_help(args: str = ""):
    """Displays the command reference guide."""
    help_text = (
        "| Command | Description |\n"
        "| :--- | :--- |\n"
        "| `/help` | Display this command reference guide |\n"
        "| `/session` or `/sessions` | List previous coding sessions stored in Redis |\n"
        "| `/model [gemini\|groq]` | Switch LLM provider on the fly (e.g. `/model gemini`) |\n"
        "| `/tools` | Inspect all available agent tools and capabilities |\n"
        "| `/history` | View coding tasks submitted in the current live session |\n"
        "| `/clear` | Clear the terminal screen |\n"
        "| `/exit` or `/quit` | Close QueryNest session |"
    )
    console.print(Panel(Markdown(help_text), title="[bold]Help & Commands[/bold]", border_style="cyan"))


def handle_model(args: str = ""):
    """Switches the active LLM provider live on the fly."""
    target = args.strip().lower()
    if target in ("gemini", "groq"):
        settings.DEFAULT_PROVIDER = target
        model_name = settings.GEMINI_MODEL if target == "gemini" else settings.GROQ_MODEL
        console.print(f"[bold green]✔ Active provider switched to:[/] [bold yellow]{target.upper()}[/bold yellow] ({model_name})")
    else:
        current_model = settings.GEMINI_MODEL if settings.DEFAULT_PROVIDER == "gemini" else settings.GROQ_MODEL
        console.print(
            f"[bold yellow]Current Provider:[/] [bold cyan]{settings.DEFAULT_PROVIDER.upper()}[/bold cyan] ({current_model})\n"
            f"[dim]Usage: /model gemini  OR  /model groq[/dim]"
        )


def handle_sessions(args: str = ""):
    """Displays past coding sessions stored in Redis."""
    arg_clean = args.strip().lower()
    if arg_clean == "clear":
        clear_session_records()
        console.print("[bold yellow]✔ Session records cleared from Redis.[/bold yellow]")
        return

    sessions = get_session_records(limit=15)
    if not sessions:
        console.print("[dim]No previous sessions found in Redis.[/dim]")
        return

    lines = []
    for idx, s in enumerate(sessions, 1):
        status_badge = "[bold green]Passed ✅[/bold green]" if s.get("test_passed") else "[bold red]Failed ❌[/bold red]"
        created_at = s.get("created_at", "Unknown time")
        task_desc = s.get("task", "No description")
        model = s.get("model", "default")
        retries = s.get("retries", 0)

        lines.append(
            f"• [bold cyan]#{idx}[/bold cyan] [dim]{created_at}[/dim] │ {status_badge} │ [dim yellow]{model.upper()}[/dim yellow] (Retries: {retries})\n"
            f"  [dim]Task:[/] {task_desc}\n"
        )

    content = "\n".join(lines)
    console.print(Panel(
        content,
        title=f"[bold]Stored Redis Sessions ({len(sessions)})[/bold]",
        border_style="cyan",
        subtitle="[dim]Type /session clear to reset history[/dim]"
    ))


def handle_tools(args: str = ""):
    """Inspects all registered tools."""
    tool_lines = []
    for t in ALL_TOOLS:
        desc = t.description.strip().splitlines()[0] if t.description else "No description"
        tool_lines.append(f"• [bold green]{t.name}[/bold green]: [dim]{desc}[/dim]")

    console.print(Panel(
        "\n".join(tool_lines),
        title=f"[bold]Registered Agent Tools ({len(ALL_TOOLS)})[/bold]",
        border_style="green"
    ))


def handle_history(args: str = ""):
    """Displays tasks executed in the current session."""
    if not task_history:
        console.print("[dim]No tasks executed in this live session yet.[/dim]")
        return
    history_md = "\n".join([f"{idx + 1}. {task}" for idx, task in enumerate(task_history)])
    console.print(Panel(Markdown(history_md), title="[bold]Current Session Tasks[/bold]", border_style="magenta"))


# Command dispatcher table
COMMAND_DISPATCHER = {
    "/help": handle_help,
    "/model": handle_model,
    "/session": handle_sessions,
    "/sessions": handle_sessions,
    "/tools": handle_tools,
    "/history": handle_history,
    "/clear": lambda _: console.clear(),
    "/exit": lambda _: sys.exit(0),
    "/quit": lambda _: sys.exit(0),
}


def dispatch_command(user_input: str) -> bool:
    """
    Executes a slash command if present.
    Returns True if handled, False if it is a regular task for agents.
    """
    if not user_input.startswith("/"):
        return False

    parts = user_input.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in COMMAND_DISPATCHER:
        COMMAND_DISPATCHER[cmd](args)
        return True

    console.print(f"[bold red]Unknown command:[/] '{cmd}'. Type [bold cyan]/help[/bold cyan] for available commands.")
    return True

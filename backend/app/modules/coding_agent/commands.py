import sys
from typing import List
from rich.console import Console
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
    console.print("\n[bold cyan]Help & Slash Commands[/bold cyan]\n")
    commands_info = [
        ("/help", "Display this command reference guide"),
        ("/session", "List recent coding sessions (e.g. /session 10 or /session all)"),
        ("/session clear", "Reset session history in Redis"),
        ("/model", "Show or switch active LLM provider (/model gemini or /model groq)"),
        ("/tools", "Inspect all registered agent tools and signatures"),
        ("/history", "View tasks submitted in the current live terminal session"),
        ("/clear", "Clear terminal screen"),
        ("/exit", "Close QueryNest session"),
    ]
    for cmd, desc in commands_info:
        console.print(f"  [bold cyan]{cmd:<18}[/] [dim]•[/dim]  {desc}")
    console.print()


def handle_model(args: str = ""):
    """Switches the active LLM provider live on the fly."""
    target = args.strip().lower()
    if target in ("gemini", "groq"):
        settings.DEFAULT_PROVIDER = target
        model_name = settings.GEMINI_MODEL if target == "gemini" else settings.GROQ_MODEL
        console.print(f"\n[bold green]✔ Active provider switched to:[/] [bold yellow]{target.upper()}[/bold yellow] ({model_name})\n")
    else:
        current_model = settings.GEMINI_MODEL if settings.DEFAULT_PROVIDER == "gemini" else settings.GROQ_MODEL
        console.print(
            f"\n[bold yellow]Current Provider:[/] [bold cyan]{settings.DEFAULT_PROVIDER.upper()}[/bold cyan] ({current_model})\n"
            f"[dim]Usage: /model gemini  OR  /model groq[/dim]\n"
        )


def handle_sessions(args: str = ""):
    """Displays past coding sessions stored in Redis with limit controls and clean typography."""
    arg_clean = args.strip().lower()
    if arg_clean == "clear":
        clear_session_records()
        console.print("\n[bold yellow]✔ Session records cleared from Redis.[/bold yellow]\n")
        return

    limit = 5
    if arg_clean == "all":
        limit = 50
    elif arg_clean.isdigit():
        limit = min(int(arg_clean), 50)

    sessions = get_session_records(limit=limit)
    if not sessions:
        console.print("\n[dim]No previous sessions found in Redis.[/dim]\n")
        return

    console.print(f"\n[bold cyan]📋 Stored Sessions[/bold cyan] [dim]({len(sessions)} recent)[/dim]\n")
    for idx, s in enumerate(sessions, 1):
        status_badge = "[bold green]Passed ✅[/bold green]" if s.get("test_passed") else "[bold red]Failed ❌[/bold red]"
        created_at = s.get("created_at", "Unknown time")
        task_desc = s.get("task", "No description")
        model = s.get("model", "default").upper()
        retries = s.get("retries", 0)

        console.print(f"• [bold cyan]#{idx}[/bold cyan] [bold white]Task:[/] {task_desc}")
        console.print(f"  [dim]{created_at}[/dim] │ {status_badge} │ [dim yellow]{model}[/dim yellow] (Retries: {retries})\n")

    console.print("[dim]Type /session 10 to see more, or /session clear to reset.[/dim]\n")


def handle_tools(args: str = ""):
    """Inspects all registered tools."""
    console.print(f"\n[bold green]🛠️  Registered Agent Tools ({len(ALL_TOOLS)})[/bold green]\n")
    for t in ALL_TOOLS:
        desc = t.description.strip().splitlines()[0] if t.description else "No description"
        console.print(f"  • [bold cyan]{t.name:<22}[/] [dim]{desc}[/dim]")
    console.print()


def handle_history(args: str = ""):
    """Displays tasks executed in the current session."""
    if not task_history:
        console.print("\n[dim]No tasks executed in this live session yet.[/dim]\n")
        return
    console.print(f"\n[bold magenta]📜 Current Session Tasks ({len(task_history)})[/bold magenta]\n")
    for idx, task in enumerate(task_history, 1):
        console.print(f"  {idx}. [white]{task}[/white]")
    console.print()


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
    """Parses and executes a slash command."""
    parts = user_input.strip().split(maxsplit=1)
    if not parts:
        return False

    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = COMMAND_DISPATCHER.get(cmd)
    if handler:
        handler(args)
        return True

    console.print(f"\n[bold red]Unknown command:[/] {cmd}. Type [bold cyan]/help[/bold cyan] for available commands.\n")
    return False

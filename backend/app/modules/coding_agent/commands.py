from datetime import datetime
from typing import List, Any, Optional, Tuple, Dict
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


def format_relative_time(dt_input: Any) -> str:
    """Formats a timestamp string or datetime into concise relative units (e.g., '40m ago', '23h ago', '1d ago', 'Oct 2')."""
    if not dt_input:
        return "recently"
    now = datetime.now()
    parsed_dt = None
    if isinstance(dt_input, datetime):
        parsed_dt = dt_input
    elif isinstance(dt_input, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed_dt = datetime.strptime(dt_input[:19], fmt)
                break
            except Exception:
                continue
    if not parsed_dt:
        return str(dt_input)

    delta = now - parsed_dt
    seconds = max(0, int(delta.total_seconds()))

    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    return parsed_dt.strftime("%b %d")


def record_task_in_history(task: str):
    """Records an executed coding task into in-memory session history."""
    task_history.append(task)


def handle_help(args: str = "") -> Optional[str]:
    """Displays the command reference guide with interactive selection."""
    from app.ui.menu import show_interactive_menu
    commands_info = [
        ("/help", "/help", "Display this command reference guide"),
        ("/model gemini", "/model gemini", "Switch active LLM provider to Gemini"),
        ("/model groq", "/model groq", "Switch active LLM provider to Groq"),
        ("/sessions", "/sessions", "List recent coding sessions stored in Redis"),
        ("/session clear", "/session clear", "Reset session history in Redis"),
        ("/tools", "/tools", "Inspect all registered agent tools and signatures"),
        ("/history", "/history", "View tasks submitted in the current live terminal session"),
        ("/clear", "/clear", "Clear terminal screen"),
        ("/exit", "/exit", "Close QueryNest session"),
    ]
    return show_interactive_menu(
        items=commands_info,
        instruction="Use ↑/↓ to navigate, Enter to select, Esc to cancel",
    )


def handle_model(args: str = "") -> Optional[str]:
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
    return None


def handle_sessions(args: str = "") -> Optional[str]:
    """Displays past coding sessions stored in Redis with interactive selection."""
    from app.ui.menu import show_interactive_menu
    arg_clean = args.strip().lower()
    if arg_clean == "clear":
        clear_session_records()
        console.print("\n[bold yellow]✔ Session records cleared from Redis.[/bold yellow]\n")
        return None

    limit = 6
    if arg_clean == "all":
        limit = 50
    elif arg_clean.isdigit():
        limit = min(int(arg_clean), 50)

    sessions = get_session_records(limit=limit)
    if not sessions:
        console.print("\n[dim]No recent session records found in Redis.[/dim]\n")
        return None

    menu_items = []
    for s in sessions:
        task_str = s.get("task", "").strip().replace("\n", " ")
        ts = s.get("created_at") or s.get("timestamp") or s.get("time")
        rel_time = format_relative_time(ts)
        menu_items.append((task_str, task_str, rel_time))


    return show_interactive_menu(
        items=menu_items,
        instruction="Use ↑/↓ to navigate, Enter to load into prompt, Esc to cancel",
    )



def handle_tools(args: str = "") -> Optional[str]:
    """Inspects all registered tools."""
    console.print(f"\n[bold green]🛠️  Registered Agent Tools ({len(ALL_TOOLS)})[/bold green]\n")
    for t in ALL_TOOLS:
        desc = t.description.strip().splitlines()[0] if t.description else "No description"
        console.print(f"  • [bold cyan]{t.name:<22}[/] [dim]{desc}[/dim]")
    console.print()
    return None


def handle_history(args: str = "") -> Optional[str]:
    """Displays tasks executed in the current session."""
    if not task_history:
        console.print("\n[dim]No tasks executed in this live session yet.[/dim]\n")
        return None
    console.print(f"\n[bold magenta]📜 Current Session Tasks ({len(task_history)})[/bold magenta]\n")
    for idx, task in enumerate(task_history, 1):
        console.print(f"  {idx}. [white]{task}[/white]")
    console.print()
    return None


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


def dispatch_command(user_input: str) -> Optional[str]:
    """Parses and executes a slash command. Returns prefill text if an item was selected."""
    parts = user_input.strip().split(maxsplit=1)
    if not parts:
        return None

    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = COMMAND_DISPATCHER.get(cmd)
    if handler:
        return handler(args)

    console.print(f"\n[bold red]Unknown command:[/] {cmd}. Type [bold cyan]/help[/bold cyan] for available commands.\n")
    return None


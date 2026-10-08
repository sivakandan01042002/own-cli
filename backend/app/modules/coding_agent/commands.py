from datetime import datetime
from typing import List, Any, Optional
from rich.console import Console


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
    "/mode",
    "/mode normal",
    "/mode accept-edits",
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
        ("/model", "/model", "Interactively select and switch active AI model"),
        ("/mode", "/mode", "Toggle execution mode (Normal Safe vs Auto Accept-All)"),
        ("/sessions", "/sessions", "List & restore past coding sessions from Redis"),
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
    """Switches the active LLM model interactively and persists choice to config.json."""
    from app.ui.menu import show_interactive_menu
    from app.core.user_config import AVAILABLE_MODELS, save_config, get_config

    target = args.strip().lower()

    # Direct argument mode: e.g. /model gemini or /model groq
    if target in ("gemini", "groq"):
        found = next((m for m in AVAILABLE_MODELS if m["provider"] == target), None)
        if found:
            save_config({
                "provider": found["provider"],
                "model": found["name"],
                "model_display": found["display"],
            })
            console.print(f"\n[bold green]✔ Model switched to:[/] [bold yellow]{found['display']}[/bold yellow] ({found['desc']})\n")
            return None

    # Interactive menu mode
    current_cfg = get_config()
    current_model = current_cfg.get("model", "")

    menu_items = []
    for m in AVAILABLE_MODELS:
        is_active = " (Active)" if m["name"] == current_model else ""
        menu_items.append((
            m["id"],
            f"{m['display']}{is_active}",
            m["desc"],
        ))

    choice = show_interactive_menu(
        title="Select Active AI Model",
        items=menu_items,
        instruction="Use ↑/↓ to navigate, Enter to select, Esc to cancel",
    )

    if choice:
        selected_model = next((m for m in AVAILABLE_MODELS if m["id"] == choice), None)
        if selected_model:
            save_config({
                "provider": selected_model["provider"],
                "model": selected_model["name"],
                "model_display": selected_model["display"],
            })
            console.print(f"\n[bold green]✔ Active Model updated to:[/] [bold yellow]{selected_model['display']}[/bold yellow]\n")

    return None


def handle_mode(args: str = "") -> Optional[str]:
    """Toggles or sets the execution mode (normal or accept-edits)."""
    from app.core.user_config import get_active_mode, set_active_mode

    arg_clean = args.strip().lower()
    if arg_clean in ("accept-edits", "accept_edits", "auto", "accept-all", "all"):
        new_mode = set_active_mode("accept-edits")
    elif arg_clean in ("normal", "safe"):
        new_mode = set_active_mode("normal")
    else:
        current = get_active_mode()
        new_mode = set_active_mode("accept-edits" if current == "normal" else "normal")

    badge = "[bold green]accept-edits[/]" if new_mode == "accept-edits" else "[#a0a0a0]normal[/]"
    console.print(f"[dim]Mode switched to:[/] {badge}")
    return None


def handle_new(args: str = "") -> str:
    """Starts a clean new multi-turn conversation session."""
    return "__new_session__"


def handle_sessions(args: str = "") -> Optional[str]:
    """Displays past session threads stored in Redis. Selecting any thread restores its full conversation memory."""
    from app.ui.menu import show_interactive_menu
    from app.core.redis_client import list_session_threads, clear_session_records

    arg_clean = args.strip().lower()
    if arg_clean == "clear":
        clear_session_records()
        console.print("[bold yellow]Session records and threads cleared.[/bold yellow]")
        return None

    limit = 10
    if arg_clean == "all":
        limit = 50
    elif arg_clean.isdigit():
        limit = min(int(arg_clean), 50)

    threads = list_session_threads(limit=limit)
    if not threads:
        console.print("[dim]No past session threads found.[/dim]")
        return None

    menu_items = []
    for t in threads:
        sid = t.get("session_id", "")
        title = t.get("title", "Untitled Session").strip().replace("\n", " ")
        turn_count = t.get("turn_count", len(t.get("messages", [])) // 2 or 1)
        turn_label = f"{turn_count} turns" if turn_count != 1 else "1 turn"
        ts = t.get("updated_at") or t.get("created_at")
        rel_time = f"{turn_label} · {format_relative_time(ts)}"
        menu_items.append((sid, title, rel_time))

    selected_sid = show_interactive_menu(
        items=menu_items,
        instruction="Use ↑/↓ to navigate, Enter to restore, Esc to cancel",
    )
    if selected_sid:
        return f"__restore_session__:{selected_sid}"
    return None



def handle_tools(args: str = "") -> Optional[str]:
    """Inspects all registered tools."""
    console.print(f"\n[bold green]Registered Agent Tools ({len(ALL_TOOLS)})[/bold green]\n")
    for t in ALL_TOOLS:
        desc = t.description.strip().splitlines()[0] if t.description else "No description"
        console.print(f"  • [bold cyan]{t.name:<22}[/] [dim]{desc}[/dim]")
    console.print()
    return None


def handle_history(args: str = "") -> Optional[str]:
    """Displays tasks executed in the current session."""
    if not task_history:
        console.print("[dim]No tasks executed in this live session yet.[/dim]")
        return None
    console.print(f"\n[bold magenta]Current Session Tasks ({len(task_history)})[/bold magenta]\n")
    for idx, task in enumerate(task_history, 1):
        console.print(f"  {idx}. [white]{task}[/white]")
    console.print()
    return None


# Command dispatcher table
COMMAND_DISPATCHER = {
    "/help": handle_help,
    "/model": handle_model,
    "/mode": handle_mode,
    "/new": handle_new,
    "/session": handle_sessions,
    "/sessions": handle_sessions,
    "/tools": handle_tools,
    "/history": handle_history,
    "/clear": lambda _: console.clear(),
    "/exit": lambda _: sys.exit(0),
    "/quit": lambda _: sys.exit(0),
}


def dispatch_command(user_input: str) -> Optional[str]:
    """Parses and executes a slash command. Returns prefill text or action code."""
    parts = user_input.strip().split(maxsplit=1)
    if not parts:
        return None

    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = COMMAND_DISPATCHER.get(cmd)
    if handler:
        return handler(args)

    console.print(f"[bold red]Unknown command:[/] {cmd}. Type [bold cyan]/help[/bold cyan] for available commands.")
    return None


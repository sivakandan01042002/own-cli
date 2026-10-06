"""Presentation and rendering components for QueryNest CLI."""
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from app.core.config import settings
from app.core.theme import COLORS

console = Console()


def render_command_guide(commands_info: List[Tuple[str, str]]):
    """Renders the slash command guide in a clean 2-column layout."""
    for idx, (cmd, desc) in enumerate(commands_info):
        prefix = "[bold #0099ff]>[/] " if idx == 0 else "  "
        cmd_styled = f"[bold white]{cmd:<18}[/bold white]" if idx == 0 else f"[white]{cmd:<18}[/white]"
        console.print(f"{prefix}{cmd_styled}  [#a0a0a0]{desc}[/#a0a0a0]")


def render_session_list(sessions: List[Dict[str, Any]], format_time_fn, limit: int = 6):
    """Renders stored sessions in a clean 2-column format with responsive spacing."""
    if not sessions:
        console.print("[dim]No previous sessions found in Redis.[/dim]")
        return

    term_width = console.size.width or 80
    time_col_width = 12

    for idx, s in enumerate(sessions):
        prefix = "[bold #0099ff]>[/] " if idx == 0 else "  "
        raw_task = s.get("task", "Untitled Task").strip().replace("\n", " ")
        time_str = format_time_fn(s.get("created_at"))

        available_title_width = max(20, term_width - time_col_width - 8)
        if len(raw_task) > available_title_width:
            task_title = raw_task[:available_title_width - 3] + "..."
        else:
            task_title = raw_task

        title_styled = f"[bold white]{task_title}[/bold white]" if idx == 0 else f"[white]{task_title}[/white]"
        spacing_count = max(2, term_width - 4 - len(task_title) - len(time_str))
        spacing = " " * spacing_count

        console.print(f"{prefix}{title_styled}{spacing}[#a0a0a0]{time_str}[/#a0a0a0]")


def render_action_badge(tool_name: str, args: Dict[str, Any]):
    """Renders permanent action badges for executed tools."""
    if tool_name == "read_file":
        path = _format_full_path(args.get("file_path", ""))
        console.print(f"[bold yellow]Read:[/] [white]{path}[/white]")
    elif tool_name == "write_file":
        path = _format_full_path(args.get("file_path", ""))
        console.print(f"[bold yellow]Write:[/] [white]{path}[/white]")
    elif tool_name == "delete_file":
        path = _format_full_path(args.get("file_path", ""))
        console.print(f"[bold yellow]Delete:[/] [white]{path}[/white]")
    elif tool_name == "run_git_command":
        subcmd = args.get("subcommand", "").strip()
        if subcmd.lower().startswith("git "):
            subcmd = subcmd[4:]
        console.print(f"[bold yellow]Git:[/] [white]git {subcmd}[/white]")
    elif tool_name == "run_terminal_command":
        cmd = args.get("command", "")
        console.print(f"[bold yellow]Bash:[/] [white]{cmd}[/white]")


def _format_full_path(path_str: str) -> str:
    """Formats path to normalized full absolute path with forward slashes."""
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.is_absolute():
        p = (settings.WORKSPACE_ROOT / p).resolve()
    else:
        p = p.resolve()
    return str(p).replace("\\", "/")

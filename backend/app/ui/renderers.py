"""Presentation and rendering components for QueryNest CLI."""
from pathlib import Path
from typing import List, Tuple, Dict, Any
from rich.console import Console

from app.core.config import settings

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


def _extract_path_payload(args: Dict[str, Any]) -> str:
    """Extracts and formats file paths."""
    return _format_full_path(args.get("file_path") or args.get("path") or "")


def _extract_git_payload(args: Dict[str, Any]) -> str:
    """Extracts and normalizes git commands."""
    subcmd = args.get("subcommand", "").strip()
    if subcmd.lower().startswith("git "):
        subcmd = subcmd[4:]
    return f"git {subcmd}"


def _extract_bash_payload(args: Dict[str, Any]) -> str:
    """Extracts commands, search queries, directory listings, or primary values."""
    if "command" in args:
        return str(args["command"])
    if "query" in args:
        return str(args["query"])
    if "dir_path" in args:
        return f"ls {args['dir_path']}"
    return next(iter(args.values())) if len(args) == 1 else str(args)


def _extract_image_payload(args: Dict[str, Any]) -> str:
    """Extracts and formats image file paths, rendering #Image for clipboard screenshots."""
    raw_path = str(args.get("image_path") or args.get("file_path") or "").replace("\\", "/")
    if ".querynest_cache" in raw_path and "clipboard" in raw_path:
        return "#Image"
    return _format_full_path(raw_path)


def _extract_image_gen_payload(args: Dict[str, Any]) -> str:
    """Extracts output path or prompt summary for image generation."""
    out_p = args.get("output_path", "")
    if out_p:
        return _format_full_path(out_p)
    prompt = args.get("prompt", "")
    return f"'{prompt[:40]}...'" if len(prompt) > 40 else f"'{prompt}'"


# Tools that only display dynamic shimmers and never print permanent badges
SHIMMER_ONLY_TOOLS = {"list_directory", "search_web"}

# Smart Tool Category Registry for permanent action badges
TOOL_BADGE_REGISTRY: Dict[str, Tuple[str, Any]] = {
    "read_file": ("Read", _extract_path_payload),
    "write_file": ("Write", _extract_path_payload),
    "patch_file": ("Patch", _extract_path_payload),
    "delete_file": ("Delete", _extract_path_payload),
    "run_git_command": ("Git", _extract_git_payload),
    "run_terminal_command": ("Bash", _extract_bash_payload),
    "inspect_image": ("Vision", _extract_image_payload),
    "generate_image": ("Image", _extract_image_gen_payload),
    "search_code": ("Search", lambda args: f"grep \"{args.get('query', '')}\""),
    "read_doc_url": ("Fetch", lambda args: str(args.get("url", ""))),
}


def render_action_badge(tool_name: str, args: Dict[str, Any]):
    """Renders permanent action badges dynamically via smart registry lookup."""
    if tool_name in SHIMMER_ONLY_TOOLS or tool_name not in TOOL_BADGE_REGISTRY:
        return

    prefix, extractor = TOOL_BADGE_REGISTRY[tool_name]
    payload = extractor(args) if extractor else str(args)
    if not payload or payload == "{}":
        return

    console.print(f"[bold yellow]{prefix}:[/] [white]{payload}[/white]")


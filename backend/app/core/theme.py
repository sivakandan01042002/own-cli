"""Centralized design system, styles, colors, and UI components for QueryNest CLI."""

from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

# ---------------------------------------------------------
# Global Visual Separators & Dimensions
# ---------------------------------------------------------
DIVIDER = "──────────────────────────────────────────────────────────────────────────"

# ---------------------------------------------------------
# Semantic Color Palette (Rich & Terminal)
# ---------------------------------------------------------
COLORS = {
    "primary": "cyan",
    "accent": "#00d2ff",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "muted": "dim",
    "muted_fg": "#666666",
    "bg_dark": "#1e1e1e",
    "bg_meta": "#282828",
    "border": "cyan",
}

# ---------------------------------------------------------
# Prompt Toolkit Theme (Centralized Autocomplete & Prompt CSS)
# ---------------------------------------------------------
CLI_STYLE = Style.from_dict({
    # Prompt symbol style
    "prompt": "ansicyan bold",
    
    # Inline bottom divider attached directly beneath the prompt
    "divider": f"fg:{COLORS['muted_fg']}",
    
    # Autocomplete popup menu container
    "completion-menu": f"bg:{COLORS['bg_dark']} #ffffff",
    
    # Inactive candidate items
    "completion-menu.completion": f"bg:{COLORS['bg_dark']} #d4d4d4",
    
    # Selected / Active candidate item
    "completion-menu.completion.current": f"bg:{COLORS['accent']} #000000 bold",
    
    # Meta / Description tag for inactive items
    "completion-menu.meta.completion": f"bg:{COLORS['bg_meta']} #888888",
    
    # Meta / Description tag for active item
    "completion-menu.meta.completion.current": "bg:#0099cc #ffffff italic",
    
    # Autocomplete scrollbar
    "scrollbar.background": f"bg:{COLORS['bg_dark']}",
    "scrollbar.button": "bg:#555555",
})


# ---------------------------------------------------------
# Welcome Banner Panel (Kept Boxed as requested)
# ---------------------------------------------------------
def create_banner_panel(workspace_root: str, active_provider: str, active_model: str) -> Panel:
    """Creates the standard welcome banner panel."""
    banner_text = (
        "[dim]Autonomous coding, testing & self-healing state machine powered by LangGraph[/dim]\n\n"
        f"• [bold green]Workspace Root:[/] {workspace_root}\n\n"
        f"• [bold yellow]Active Model:[/] {active_provider.upper()} ({active_model})\n\n"
        "[dim]Type [bold cyan]/[/bold cyan] for commands[/dim]"
    )
    return Panel(
        banner_text,
        padding=(1, 2),
        border_style=COLORS["border"],
        title="[bold]QueryNest Assistant[/bold]",
        title_align="left",
    )


# ---------------------------------------------------------
# Sleek, Borderless UI Output Headers
# ---------------------------------------------------------
def print_planner_header(console: Console) -> None:
    """Renders clean borderless header for Architect Blueprint."""
    console.print("\n[bold green]🏗️  Architect Blueprint[/bold green]\n")


def print_summary_header(console: Console) -> None:
    """Renders clean borderless header for Summary Report."""
    console.print("\n[bold cyan]📋 Summary Report[/bold cyan]\n")


def print_error_badge(console: Console, error_text: str) -> None:
    """Renders clean inline error badge without heavy boxed frames."""
    console.print(f"\n[bold red]❌ Error:[/] [dim red]{error_text}[/dim red]\n")


def print_top_divider(console: Console) -> None:
    """Renders the top framing divider before user prompt."""
    console.print(f"\n[dim]{DIVIDER}[/dim]")


def print_bottom_divider(console: Console) -> None:
    """Renders the bottom framing divider in console history after message submission."""
    console.print(f"[dim]{DIVIDER}[/dim]\n")

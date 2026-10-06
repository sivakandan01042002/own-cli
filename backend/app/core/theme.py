"""Centralized design system, styles, colors, and UI components for QueryNest CLI."""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme


# ---------------------------------------------------------
# Semantic Color Palette & Rich Theme
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

RICH_THEME = Theme({
    "markdown.h1": "bold white",
    "markdown.h2": "bold white",
    "markdown.h3": "bold white",
    "markdown.h4": "bold white",
    "markdown.h5": "bold white",
    "markdown.h6": "bold white",
    "markdown.link": "bold #0099ff",
    "markdown.link_url": "dim #a0a0a0",
})


# ---------------------------------------------------------
# Prompt Toolkit Theme (Centralized Autocomplete & Prompt CSS)
# ---------------------------------------------------------
CLI_STYLE = Style.from_dict({
    # Prompt symbol style
    "prompt": "ansicyan bold",
    
    # Inline divider attached directly above and beneath the prompt
    "divider": f"fg:{COLORS['muted_fg']}",
    
    # Autocomplete popup menu container - flat, clean
    "completion-menu": "bg:#1e1e1e",
    
    # Inactive candidate items - white command text
    "completion-menu.completion": "fg:#ffffff",
    
    # Selected / Active candidate item - blue highlight with bold white text
    "completion-menu.completion.current": "bg:#0099ff fg:#ffffff bold",
    
    # Meta / Description tag for inactive items - silver / cement
    "completion-menu.meta.completion": "fg:#a0a0a0",
    
    # Meta / Description tag for active item - light white italic on blue
    "completion-menu.meta.completion.current": "bg:#0099ff fg:#ffffff italic",
    
    # Autocomplete scrollbar
    "scrollbar.background": "bg:#1e1e1e",
    "scrollbar.button": "bg:#555555",
    
    # Active bottom divider toolbar directly below prompt input
    "bottom-toolbar": "bg:default",
    "bottom-divider": f"fg:{COLORS['muted_fg']}",
})



# ---------------------------------------------------------
# Welcome Banner Panel (Kept Boxed as requested)
# ---------------------------------------------------------
def create_banner_panel(workspace_root: str, active_provider: str, active_model: str) -> Panel:
    """Creates the standard welcome banner panel with responsive fitting."""
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
        expand=False,
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
    console.print(f"\n[bold red]❌ Error:[/] {error_text}\n")

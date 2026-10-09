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

    # Bottom status bar elements
    "status-mode-normal": "fg:#a0a0a0",
    "status-mode-accept-edits": "fg:#50fa7b bold",
    "status-model": "fg:#a0a0a0",
})



# ---------------------------------------------------------
# Welcome Banner Panel (with QueryNest ASCII Art)
# ---------------------------------------------------------
QUERYNEST_ASCII_ART = """[bold #00d2ff]   ____                              _   _           _   
  / __ \\                            | \\ | |         | |  
 | |  | |_   _  ___ _ __ _   _ _____|  \\| | ___  ___| |_ 
 | |  | | | | |/ _ \\ '__| | | |_____| . ` |/ _ \\/ __| __|
 | |__| | |_| |  __/ |  | |_| |     | |\\  |  __/\\__ \\ |_ 
  \\___\\_\\\\__,_|\\___|_|   \\__, |     |_| \\_|\\___||___/\\__|
                          __/ |                          
                         |___/                           [/]"""


from rich.align import Align
from rich.console import Group
from rich.text import Text


def create_banner_panel(workspace_root: str, active_provider: str, active_model: str) -> Panel:
    """Creates the standard welcome banner panel with centered ASCII art and clean left-aligned metadata."""
    ascii_centered = Align.center(Text.from_markup(QUERYNEST_ASCII_ART))

    content = Group(
        ascii_centered,
        Text(""),
        Text.from_markup("[dim]Autonomous multi-agent coding, testing & self-healing state machine[/dim]"),
        Text(""),
        Text.from_markup(f"• [bold green]Workspace Root:[/] {workspace_root}"),
        Text.from_markup(f"• [bold yellow]Active Model:[/] {active_provider.upper()} ({active_model})"),
        Text(""),
        Text.from_markup("[dim]Type [bold cyan]/[/bold cyan] for commands or enter your task below[/dim]"),
    )

    return Panel(
        content,
        padding=(1, 2),
        border_style=COLORS["border"],
        expand=True,
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

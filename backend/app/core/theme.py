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
    "primary": "#2dd4bf",      # Modern Seafoam (Unified theme for UI, logo, prompt '❯', selection '>', shimmer, and markdown)
    "accent": "#14b8a6",       # Deep Seafoam Teal
    "seafoam": "#2dd4bf",      # Modern Seafoam
    "text": "#f8fafc",         # Crisp White
    "success": "#2dd4bf",      # Seafoam Green
    "warning": "#eab308",      # Gold / Yellow for tool badges
    "error": "#ef4444",        # Red
    "muted": "#a0a0a0",        # Readable Silver/Gray for secondary text
    "muted_fg": "#666666",     # Divider & border gray
    "divider": "#404040",      # Subtle session divider line
    "border": "#444444",       # Clean Neutral Border
    "bg_dark": "#1e1e1e",
    "bg_meta": "#282828",
    # Shimmer animation gradient colors (Seafoam sweep)
    "shimmer_base": "#707070",
    "shimmer_peak": "bold #2dd4bf",
    "shimmer_glow": "bold #5eead4",
    "shimmer_trail": "#0d9488",
}

RICH_THEME = Theme({
    "primary": "bold #2dd4bf",
    "brand": "bold #2dd4bf",
    "accent": "#2dd4bf",
    "success": "bold #2dd4bf",
    "warning": "bold #eab308",
    "error": "bold #ef4444",
    "muted": "#a0a0a0",
    "divider": "#404040",
    "prompt": "bold #2dd4bf",
    "title": "bold #f8fafc",
    "label": "bold #f8fafc",
    "cmd": "#2dd4bf",
    "value": "#f8fafc",
    # Rich Markdown Styles (Unified Seafoam #2dd4bf)
    "markdown.h1": "bold #f8fafc",
    "markdown.h2": "bold #f8fafc",
    "markdown.h3": "bold #f8fafc",
    "markdown.h4": "bold #f8fafc",
    "markdown.h5": "bold #f8fafc",
    "markdown.h6": "bold #f8fafc",
    "markdown.code": "#2dd4bf",
    "markdown.code_block": "#f8fafc",
    "markdown.strong": "bold #f8fafc",
    "markdown.emph": "italic #f8fafc",
    "markdown.link": "bold #2dd4bf",
    "markdown.link_url": "dim #a0a0a0",
    "markdown.item.bullet": "dim #a0a0a0",
    "markdown.item.number": "dim #a0a0a0",
    "markdown.block_quote": "#2dd4bf",
})


# ---------------------------------------------------------
# Prompt Toolkit Theme (Centralized Autocomplete & Prompt CSS)
# ---------------------------------------------------------
CLI_STYLE = Style.from_dict({
    "prompt": f"{COLORS['seafoam']} bold",
    "divider": f"fg:{COLORS['muted_fg']}",
    "completion-menu": f"bg:{COLORS['bg_dark']}",
    "completion-menu.completion": f"fg:{COLORS['text']}",
    "completion-menu.completion.current": f"bg:{COLORS['seafoam']} fg:#000000 bold",
    "completion-menu.meta.completion": f"fg:{COLORS['muted']}",
    "completion-menu.meta.completion.current": f"bg:{COLORS['seafoam']} fg:#000000 italic",
    "scrollbar.background": f"bg:{COLORS['bg_dark']}",
    "scrollbar.button": "bg:#555555",
    "bottom-toolbar": "bg:default",
    "bottom-divider": f"fg:{COLORS['muted_fg']}",
    "status-mode-normal": f"fg:{COLORS['muted']}",
    "status-mode-accept-edits": f"{COLORS['seafoam']} bold",
    "status-model": f"fg:{COLORS['muted']}",
})


# ---------------------------------------------------------
# Interactive Menu Theme (Prompt Toolkit Layout Styles)
# ---------------------------------------------------------
MENU_STYLE = Style.from_dict({
    "menu-title": f"fg:{COLORS['text']}",
    "menu-instruction": f"fg:{COLORS['muted_fg']}",
    "active-pointer": f"bold {COLORS['seafoam']}",
    "active-label": f"fg:{COLORS['text']}",
    "active-desc": f"fg:{COLORS['muted']}",
    "inactive-pointer": "",
    "inactive-label": "fg:#cccccc",
    "inactive-desc": f"fg:{COLORS['muted_fg']}",
    "ws-path": f"bold {COLORS['seafoam']}",
    "ws-title": f"fg:{COLORS['text']}",
    "ws-desc": f"fg:{COLORS['muted']}",
})


# ---------------------------------------------------------
# Welcome Banner Panel (with Seafoam QueryNest ASCII Art)
# ---------------------------------------------------------
QUERYNEST_ASCII_ART = f"[{COLORS['seafoam']} bold]   ____                              _   _           _   \n" \
                      f"  / __ \\                            | \\ | |         | |  \n" \
                      f" | |  | |_   _  ___ _ __ _   _ _____|  \\| | ___  ___| |_ \n" \
                      f" | |  | | | | |/ _ \\ '__| | | |_____| . ` |/ _ \\/ __| __|\n" \
                      f" | |__| | |_| |  __/ |  | |_| |     | |\\  |  __/\\__ \\ |_ \n" \
                      f"  \\___\\_\\\\__,_|\\___|_|   \\__, |     |_| \\_|\\___||___/\\__|\n" \
                      f"                          __/ |                          \n" \
                      f"                         |___/                           [/{COLORS['seafoam']} bold]"


from rich.align import Align
from rich.console import Group
from rich.text import Text


def create_banner_panel(workspace_root: str, active_provider: str, active_model: str) -> Panel:
    """Creates a modern, developer-first welcome banner panel with clean layout and dynamic greeting."""
    from app.core.auth import get_current_user
    user = get_current_user()

    ascii_centered = Align.center(Text.from_markup(QUERYNEST_ASCII_ART))

    elements = [
        ascii_centered,
        Text(""),
    ]

    if user and user.get("name"):
        first_name = user["name"].split()[0] if user["name"] else "there"
        elements.append(Text.from_markup(f"[title]Hi {first_name}, what are we building today?[/title]"))
    else:
        elements.append(Text.from_markup("[title]Welcome to QueryNest[/title]"))

    elements.extend([
        Text.from_markup("[dim]Autonomous AI pair programmer & codebase intelligence engine[/dim]"),
        Text(""),
        Text.from_markup(f"[label]📁 Workspace:[/]  {workspace_root}"),
        Text.from_markup(f"[label]⚡ Engine:[/]     {active_provider.upper()} ({active_model})"),
    ])

    if user and user.get("email"):
        elements.append(Text.from_markup(f"[label]👤 Account:[/]    {user.get('email')}"))

    elements.extend([
        Text(""),
        Text.from_markup(f"[dim]Tip: Type [cmd]/[/cmd] for slash commands or describe any task below[/dim]"),
    ])

    return Panel(
        Group(*elements),
        padding=(1, 2),
        border_style=COLORS["border"],
        expand=True,
    )


# ---------------------------------------------------------
# Sleek, Borderless UI Output Headers
# ---------------------------------------------------------
def print_planner_header(console: Console) -> None:
    """Renders clean borderless header for Architect Blueprint."""
    console.print("\n[primary]🏗️  Architect Blueprint[/primary]\n")


def print_summary_header(console: Console) -> None:
    """Renders clean borderless header for Summary Report."""
    console.print("\n[primary]📋 Summary Report[/primary]\n")


def print_error_badge(console: Console, error_text: str) -> None:
    """Renders clean inline error badge without heavy boxed frames."""
    console.print(f"\n[error]❌ Error:[/] {error_text}\n")

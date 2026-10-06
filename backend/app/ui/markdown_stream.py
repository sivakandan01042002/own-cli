from typing import Iterable, Optional, List
from rich import box
from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.markdown import (
    Markdown,
    MarkdownElement,
    TableHeaderElement,
    TableBodyElement,
    MarkdownContext,
)
from rich.table import Table
from rich.panel import Panel
from rich.text import Text


class ResponsiveTableElement(MarkdownElement):
    """
    Adaptive Table Element:
    - On Wide / Normal screens (available_width >= 65): Renders a full rounded boxed grid with folded columns.
    - On Narrow screens (available_width < 65): Automatically transforms table rows into clean vertical key-value cards
      so text never gets crushed into 2-character columns on narrow split panes.
    """
    def __init__(self) -> None:
        self.header: Optional[TableHeaderElement] = None
        self.body: Optional[TableBodyElement] = None

    def on_child_close(self, context: MarkdownContext, child: MarkdownElement) -> bool:
        if isinstance(child, TableHeaderElement):
            self.header = child
        elif isinstance(child, TableBodyElement):
            self.body = child
        return False

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        headers: List[Text] = []
        if self.header and self.header.row:
            headers = [col.content.copy() for col in self.header.row.cells]

        rows: List[List[Text]] = []
        if self.body:
            for row in self.body.rows:
                rows.append([element.content for element in row.cells])

        if not headers and not rows:
            return

        available_width = options.max_width
        num_cols = max(len(headers), len(rows[0]) if rows else 1)

        # Narrow threshold: less than 22 chars per column or screen width < 65
        is_narrow = (available_width / num_cols) < 22 or available_width < 65

        if not is_narrow:
            # 1. Standard Wide Boxed Grid
            table = Table(
                box=box.ROUNDED,
                pad_edge=True,
                show_edge=True,
                show_lines=True,
                header_style="bold cyan",
                border_style="dim",
                expand=False,
            )
            for h in headers:
                h.stylize("bold cyan")
                table.add_column(h, overflow="fold")
            for r in rows:
                table.add_row(*r)
            yield table
        else:
            # 2. Responsive Narrow Card Layout
            for idx, r in enumerate(rows):
                card_text = Text()
                for c_idx, cell in enumerate(r):
                    h_text = headers[c_idx].plain if c_idx < len(headers) else f"Field {c_idx+1}"
                    card_text.append(f"• {h_text}: ", style="bold cyan")
                    card_text.append(cell)
                    if c_idx < len(r) - 1:
                        card_text.append("\n")
                yield Panel(card_text, border_style="dim", padding=(0, 1), expand=True)


# Register adaptive boxed table renderer globally for Markdown parsing
Markdown.elements["table_open"] = ResponsiveTableElement


def stream_live_markdown(
    token_stream: Iterable[str],
    console: Optional[Console] = None,
    refresh_per_second: int = 15,
) -> str:
    """
    Reusable UI Component:
    Streams text tokens in real time while rendering formatted Rich Markdown with adaptive responsive tables.
    Accumulates and returns the full generated text for state and session storage.
    """
    console = console or Console()
    accumulated_text = ""
    console.print()

    with Live(
        Markdown(accumulated_text),
        console=console,
        refresh_per_second=refresh_per_second,
        transient=False,
    ) as live:
        for token in token_stream:
            if token:
                accumulated_text += token
                live.update(Markdown(accumulated_text))

    console.print()
    return accumulated_text

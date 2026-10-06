from typing import Iterable, Optional
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


from app.core.theme import RICH_THEME


class BoxedTableElement(MarkdownElement):
    """
    Renders standard Markdown tables as a unified, full rounded-border table
    with column headers, row dividers, and clean word-wrapping.
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
        table = Table(
            box=box.ROUNDED,
            pad_edge=True,
            show_edge=True,
            show_lines=True,
            header_style="bold white",
            border_style="dim",
            expand=False,
        )

        if self.header is not None and self.header.row is not None:
            for column in self.header.row.cells:
                heading = column.content.copy()
                heading.stylize("bold white")
                table.add_column(heading, overflow="fold")

        if self.body is not None:
            for row in self.body.rows:
                row_content = [element.content for element in row.cells]
                table.add_row(*row_content)

        yield table


# Register full boxed table renderer globally for all Markdown parsing
Markdown.elements["table_open"] = BoxedTableElement


def stream_live_markdown(
    token_stream: Iterable[str],
    console: Optional[Console] = None,
    refresh_per_second: int = 15,
) -> str:
    """
    Reusable UI Component:
    Streams text tokens in real time while rendering formatted Rich Markdown with full rounded tables.
    Accumulates and returns the full generated text for state and session storage.
    """
    console = console or Console(theme=RICH_THEME)

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

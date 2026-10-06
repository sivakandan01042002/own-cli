from typing import Iterable, Optional
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown


def stream_live_markdown(
    token_stream: Iterable[str],
    console: Optional[Console] = None,
    refresh_per_second: int = 15,
) -> str:
    """
    Reusable UI Component:
    Streams text tokens in real time while rendering formatted Rich Markdown.
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

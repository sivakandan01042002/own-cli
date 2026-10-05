from typing import Optional
from rich.console import Console
from rich.live import Live
from rich.text import Text


class ShimmerText:
    """
    Renders a cement-colored base text with a glowing light/shimmer beam
    that sweeps from left to right across the text repeatedly.
    """
    def __init__(
        self,
        message: str = "",
        base_color: str = "#707070",
        beam_width: int = 4,
    ):
        self.message = message
        self.base_color = base_color
        self.beam_width = beam_width
        self.pos = -beam_width
        self.msg_len = len(message)

    def set_message(self, message: str):
        self.message = message
        self.msg_len = len(message)
        self.pos = -self.beam_width

    def __rich__(self) -> Text:
        text = Text()
        # Cement base: #707070 (dim grey)
        # Highlight ramp: #707070 -> #a8a8a8 -> #e0e0e0 -> bold #ffffff (peak) -> #e0e0e0 -> #a8a8a8 -> #707070
        for i, char in enumerate(self.message):
            dist = abs(i - self.pos)
            if dist == 0:
                text.append(char, style="bold #ffffff")
            elif dist == 1:
                text.append(char, style="bold #e0e0e0")
            elif dist == 2:
                text.append(char, style="#a8a8a8")
            else:
                text.append(char, style=self.base_color)
        
        self.pos += 1
        if self.pos > self.msg_len + self.beam_width + 4:
            self.pos = -self.beam_width
        return text


class ShimmerLoader:
    """
    Reusable context manager and controller for animated cement/shimmer loaders.
    Automatically clears its display line upon completion (transient=True).
    """
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._shimmer = ShimmerText("")
        self._live: Optional[Live] = None

    def start(self, message: str):
        """Starts the animated shimmering text loader with the given message."""
        self.stop()
        self._shimmer.set_message(message)
        self._live = Live(
            self._shimmer,
            console=self.console,
            refresh_per_second=20,
            transient=True,
        )
        self._live.start()

    def update(self, message: str):
        """Updates the active loader message dynamically."""
        if self._live is not None:
            self._shimmer.set_message(message)
        else:
            self.start(message)

    def stop(self):
        """Stops the loader and cleanly clears the active line."""
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

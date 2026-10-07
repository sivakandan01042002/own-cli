from typing import Optional
from rich.console import Console
from rich.live import Live
from rich.text import Text


class ShimmerText:
    """
    Renders a neutral scrolling dot spinner followed by cement-colored text
    with an animated glowing green light/shimmer beam that sweeps across the text.
    """
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

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
        self.frame_idx = 0

    def set_message(self, message: str):
        self.message = message
        self.msg_len = len(message)
        self.pos = -self.beam_width

    def __rich__(self) -> Text:
        text = Text()

        # 1. Neutral scrolling dot spinner (no color / dim as requested)
        spinner_char = self.SPINNER_FRAMES[self.frame_idx % len(self.SPINNER_FRAMES)]
        text.append(f"{spinner_char} ", style="dim")
        self.frame_idx += 1

        # 2. Cement base with Glowing Green Shimmer Wave
        # Base: #707070 (cement grey)
        # Gradient peak: bold #22c55e (vivid green)
        # Inner glow: bold #86efac (light green)
        # Outer glow: #4b7a63 (soft muted green transition)
        for i, char in enumerate(self.message):
            dist = abs(i - self.pos)
            if dist == 0:
                text.append(char, style="bold #22c55e")
            elif dist == 1:
                text.append(char, style="bold #86efac")
            elif dist == 2:
                text.append(char, style="#4b7a63")
            else:
                text.append(char, style=self.base_color)

        self.pos += 1
        if self.pos > self.msg_len + self.beam_width + 4:
            self.pos = -self.beam_width
        return text


class ShimmerLoader:
    """
    Reusable context manager and controller for animated green shimmer loaders.
    Automatically clears its display line upon completion (transient=True).
    """
    _ACTIVE_LOADER: Optional["ShimmerLoader"] = None

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._shimmer = ShimmerText("")
        self._live: Optional[Live] = None

    @classmethod
    def stop_active(cls):
        """Stops any currently running global shimmer loader."""
        if cls._ACTIVE_LOADER is not None:
            cls._ACTIVE_LOADER.stop()

    def start(self, message: str):
        """Starts the animated shimmering text loader with the given message."""
        self.stop()
        ShimmerLoader._ACTIVE_LOADER = self
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
        if ShimmerLoader._ACTIVE_LOADER is self:
            ShimmerLoader._ACTIVE_LOADER = None
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

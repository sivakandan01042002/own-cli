"""Interactive framed prompt session component using Prompt Toolkit."""
import shutil
import sys
from typing import Optional

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer
from prompt_toolkit.data_structures import Size
from prompt_toolkit.filters import has_completions
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout.containers import Float, FloatContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.output import create_output
from prompt_toolkit.output.vt100 import Vt100_Output
from rich.console import Console

from app.core.theme import CLI_STYLE

console = Console()


def _get_safe_output():
    """Returns the most compatible output device (Win32Output or Vt100 fallback)."""
    try:
        return create_output()
    except Exception:
        return Vt100_Output(
            sys.stdout,
            lambda: Size(
                rows=shutil.get_terminal_size((80, 24)).lines,
                columns=shutil.get_terminal_size((80, 24)).columns,
            ),
        )


class FramedPromptSession:
    """
    Interactive prompt with dynamic line wrapping, history recall,
    and responsive Prompt Toolkit native window dividers framing the input.
    """
    def __init__(self, completer: Optional[Completer] = None, style=None):
        self.completer = completer
        self.style = style or CLI_STYLE
        self.history = InMemoryHistory()

    def prompt(self, default: str = "") -> str:
        """Prompts user for input with tight top and bottom dividers and optional default pre-fill."""
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            buf = event.app.current_buffer
            if buf.complete_state and buf.complete_state.current_completion:
                buf.apply_completion(buf.complete_state.current_completion)
                return
            text = buf.text
            if not text.strip():
                return
            self.history.append_string(text.strip())
            event.app.exit(result=text)

        @kb.add("up", filter=has_completions)
        def _(event):
            event.app.current_buffer.auto_up()

        @kb.add("down", filter=has_completions)
        def _(event):
            event.app.current_buffer.auto_down()

        @kb.add("up", filter=~has_completions)
        def _(event):
            event.app.current_buffer.history_backward()

        @kb.add("down", filter=~has_completions)
        def _(event):
            event.app.current_buffer.history_forward()

        @kb.add("c-c")
        @kb.add("c-d")
        def _(event):
            event.app.exit(exception=KeyboardInterrupt)

        all_kb = merge_key_bindings([load_key_bindings(), kb])

        buf = Buffer(
            completer=self.completer,
            complete_while_typing=True,
            history=self.history,
            enable_history_search=True,
        )

        if default:
            buf.text = default
            buf.cursor_position = len(default)

        def _get_line_prefix(line_no: int, wrap_count: int):
            if line_no == 0 and wrap_count == 0:
                return [("class:prompt", "❯ ")]
            return [("class:prompt", "  ")]

        # Use native Window(char="─") top and bottom dividers directly framing the input line
        root = HSplit([
            Window(char="─", style="class:divider", height=1, dont_extend_height=True),
            FloatContainer(
                content=Window(
                    BufferControl(buffer=buf),
                    get_line_prefix=_get_line_prefix,
                    wrap_lines=True,
                    dont_extend_height=True,
                ),
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        content=CompletionsMenu(max_height=8, scroll_offset=1),
                    )
                ],
            ),
            Window(char="─", style="class:divider", height=1, dont_extend_height=True),
        ])

        app = Application(
            layout=Layout(root),
            key_bindings=all_kb,
            style=self.style,
            full_screen=False,
            erase_when_done=False,
            output=_get_safe_output(),
        )

        return app.run()

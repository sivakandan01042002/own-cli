from typing import Optional
from prompt_toolkit.layout.containers import HSplit, Window, FloatContainer, Float
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.application import Application
from prompt_toolkit.completion import Completer

from app.core.theme import DIVIDER, CLI_STYLE


class FramedPromptSession:
    """Interactive prompt with dynamic line wrapping, history recall, and locked framing dividers."""
    def __init__(self, completer: Optional[Completer] = None, style=None):
        self.completer = completer
        self.style = style or CLI_STYLE
        self.history = InMemoryHistory()

    def prompt(self) -> str:
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            text = event.app.current_buffer.text
            if text.strip():
                self.history.append_string(text.strip())
            event.app.exit(result=text)

        @kb.add("up")
        def _(event):
            event.app.current_buffer.history_backward()

        @kb.add("down")
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

        def _get_line_prefix(line_no: int, wrap_count: int):
            if line_no == 0 and wrap_count == 0:
                return [("class:prompt", "❯ ")]
            return [("class:prompt", "  ")]

        root = HSplit([
            Window(FormattedTextControl([("class:divider", DIVIDER)]), height=1, dont_extend_height=True),
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
            Window(FormattedTextControl([("class:divider", DIVIDER)]), height=1, dont_extend_height=True),
        ])

        app = Application(
            layout=Layout(root),
            key_bindings=all_kb,
            style=self.style,
            full_screen=False,
            erase_when_done=False,
        )

        return app.run()

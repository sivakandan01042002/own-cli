"""Interactive framed prompt session component using Prompt Toolkit."""
import shutil
import sys
from typing import Optional

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer
from prompt_toolkit.data_structures import Size
from prompt_toolkit.filters import Condition, has_completions
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.output import create_output
from prompt_toolkit.output.vt100 import Vt100_Output
from rich.console import Console

from app.core.theme import CLI_STYLE
from app.core.user_config import (
    get_active_mode,
    set_active_mode,
    get_active_model_display,
)

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
    status bar bottom frame (mode ... model), and responsive Prompt Toolkit dividers.
    """
    def __init__(self, completer: Optional[Completer] = None, style=None):
        self.completer = completer
        self.style = style or CLI_STYLE
        self.history = InMemoryHistory()

    def prompt(self, default: str = "") -> str:
        """Prompts user for input with dynamic status header and optional default pre-fill."""
        kb = KeyBindings()
        is_active = [True]

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
            is_active[0] = False
            event.app.invalidate()
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

        # Shift + Tab or Ctrl + T to toggle Normal <-> Accept-Edits execution modes
        @kb.add("s-tab")
        @kb.add("c-t")
        def _(event):
            curr_mode = get_active_mode()
            new_mode = "accept-edits" if curr_mode == "normal" else "normal"
            set_active_mode(new_mode)
            event.app.invalidate()

        @kb.add("c-c")
        @kb.add("c-d")
        def _(event):
            is_active[0] = False
            event.app.invalidate()
            event.app.exit(exception=KeyboardInterrupt)

        # Alt + V (or Esc + V) to paste screenshot/image directly from clipboard
        @kb.add("escape", "v")
        def _(event):
            try:
                import time
                from pathlib import Path
                from PIL import ImageGrab, Image
                from app.core.config import settings
                from app.core.guardrails import register_clipboard_image

                clipboard_data = ImageGrab.grabclipboard()

                if isinstance(clipboard_data, Image.Image):
                    cache_dir = settings.WORKSPACE_ROOT / ".querynest_cache" / "clipboard"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    timestamp = int(time.time() * 1000)
                    img_path = cache_dir / f"clip_{timestamp}.png"
                    clipboard_data.save(img_path, format="PNG")
                    tag = register_clipboard_image(str(img_path))
                    event.app.current_buffer.insert_text(f"{tag} ")
                elif isinstance(clipboard_data, list):
                    # Windows Explorer copied files
                    for item in clipboard_data:
                        p = Path(item)
                        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
                            tag = register_clipboard_image(str(p))
                            event.app.current_buffer.insert_text(f"{tag} ")
            except Exception:
                pass

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

        def _get_bottom_status_bar():
            if not is_active[0]:
                return []
            cols = shutil.get_terminal_size((80, 24)).columns
            mode = get_active_mode()
            model_disp = get_active_model_display()

            left_str = f" {mode}"
            right_str = f"{model_disp} "

            occupied = len(left_str) + len(right_str)
            spacing_count = max(1, cols - occupied)

            mode_style = "class:status-mode-accept-edits" if mode == "accept-edits" else "class:status-mode-normal"

            return [
                (mode_style, left_str),
                ("class:divider", " " * spacing_count),
                ("class:status-model", right_str),
            ]

        # Top divider + input container + bottom divider + status bar underneath (hidden when submitted)
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
            ConditionalContainer(
                content=Window(
                    content=FormattedTextControl(_get_bottom_status_bar),
                    height=1,
                    dont_extend_height=True,
                ),
                filter=Condition(lambda: is_active[0]),
            ),
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

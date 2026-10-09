"""Interactive arrow-key navigation menu picker using Prompt Toolkit."""
import shutil
import sys
from typing import List, Optional, Tuple, Any, Union


from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Size
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.output import create_output
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.styles import Style


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


from app.core.theme import MENU_STYLE


def show_interactive_menu(
    items: List[Tuple[str, str, str]],  # (return_value, label, description)
    instruction: str = "Use ↑/↓ to navigate, Enter to select, Esc to cancel",
    title: Any = "",
    indent_pointer: bool = True,
    max_visible: int = 6,
) -> Optional[str]:
    """
    Renders an interactive terminal menu with up/down arrow navigation.
    Limits visible items to max_visible (default: 6) with a smooth sliding window.
    """
    if not items:
        return None

    selected_index = [0]  # list for closure mutation

    ptr_active = "  > " if indent_pointer else "> "
    ptr_inactive = "    " if indent_pointer else "  "

    def get_formatted_text() -> StyleAndTextTuples:
        lines: StyleAndTextTuples = []

        if title:
            lines.append(("", "\n"))
            if isinstance(title, list):
                lines.extend(title)
            else:
                lines.append(("class:menu-title", f"{title}\n"))

        term_width = shutil.get_terminal_size((80, 24)).columns
        total_items = len(items)

        # Sliding window calculation for max_visible items
        if total_items > max_visible:
            half = max_visible // 2
            start_idx = max(0, min(selected_index[0] - half, total_items - max_visible))
            end_idx = start_idx + max_visible
        else:
            start_idx = 0
            end_idx = total_items

        visible_indices = list(range(start_idx, end_idx))

        is_inline_subtitle = any(bool(desc and desc.startswith("(")) for _, _, desc in items)

        if is_inline_subtitle:
            for idx in visible_indices:
                val, label, desc = items[idx]
                is_active = idx == selected_index[0]
                pointer_class = "class:active-pointer" if is_active else "class:inactive-pointer"
                label_class = "class:active-label" if is_active else "class:inactive-label"
                desc_class = "class:active-desc" if is_active else "class:inactive-desc"
                pointer_str = ptr_active if is_active else ptr_inactive

                lines.append((pointer_class, pointer_str))
                lines.append((label_class, f"{label} "))
                if desc:
                    lines.append((desc_class, f"{desc}"))
                lines.append(("", "\n"))
        else:
            is_wide_list = any(len(label) > 25 for _, label, _ in items)
            if is_wide_list:
                time_width = 12
                max_label_width = max(20, term_width - time_width - 8)
                for idx in visible_indices:
                    val, label, desc = items[idx]
                    is_active = idx == selected_index[0]
                    clean_label = label if len(label) <= max_label_width else (label[:max_label_width - 3] + "...")
                    space_count = max(2, term_width - 6 - len(clean_label) - len(desc or ""))
                    spacing = " " * space_count
                    if is_active:
                        lines.append(("class:active-pointer", ptr_active))
                        lines.append(("class:active-label", clean_label))
                        lines.append(("", spacing))
                        lines.append(("class:active-desc", f"{desc}\n"))
                    else:
                        lines.append(("class:inactive-pointer", ptr_inactive))
                        lines.append(("class:inactive-label", clean_label))
                        lines.append(("", spacing))
                        lines.append(("class:inactive-desc", f"{desc}\n"))
            else:
                max_label_len = max(len(label) for _, label, _ in items) if items else 15
                pad = max(max_label_len + 3, 18)
                for idx in visible_indices:
                    val, label, desc = items[idx]
                    is_active = idx == selected_index[0]
                    if is_active:
                        lines.append(("class:active-pointer", ptr_active))
                        lines.append(("class:active-label", f"{label:<{pad}}"))
                        lines.append(("class:active-desc", f"{desc}\n"))
                    else:
                        lines.append(("class:inactive-pointer", ptr_inactive))
                        lines.append(("class:inactive-label", f"{label:<{pad}}"))
                        lines.append(("class:inactive-desc", f"{desc}\n"))

        if instruction:
            lines.append(("", "\n"))
            if total_items > max_visible:
                counter = f"{selected_index[0] + 1}/{total_items} · "
                lines.append(("class:menu-instruction", f"  ({counter}{instruction})\n"))
            else:
                lines.append(("class:menu-instruction", f"  ({instruction})\n"))

        return lines



    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _(event):
        selected_index[0] = (selected_index[0] - 1) % len(items)

    @kb.add("down")
    @kb.add("j")
    def _(event):
        selected_index[0] = (selected_index[0] + 1) % len(items)

    @kb.add("enter")
    def _(event):
        event.app.exit(result=items[selected_index[0]][0])

    @kb.add("escape")
    @kb.add("c-c")
    @kb.add("q")
    def _(event):
        event.app.exit(result=None)

    control = FormattedTextControl(get_formatted_text, show_cursor=False)
    window = Window(content=control)
    layout = Layout(HSplit([window]))


    app = Application(
        layout=layout,
        key_bindings=kb,
        style=MENU_STYLE,
        full_screen=False,
        erase_when_done=True,
        output=_get_safe_output(),
    )


    try:
        return app.run()
    except Exception:
        return None

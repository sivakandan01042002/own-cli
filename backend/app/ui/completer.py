import os
import re
from pathlib import Path
from typing import List, Tuple, Optional
from prompt_toolkit.completion import Completer, Completion

from app.core.config import settings
from app.constants.workspace import DEFAULT_IGNORE_DIRS
from app.constants.commands import SLASH_COMMANDS_META



class SmartPromptCompleter(Completer):
    """
    Unified autocomplete component supporting:
    1. Slash commands when typing '/'
    2. Real-time workspace file and directory completion when typing '@'
    """
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = (workspace_root or settings.WORKSPACE_ROOT).resolve()

    def _get_workspace_files(self, prefix: str) -> List[Tuple[str, str]]:
        """Scans workspace for matching files and directories with intelligent ranking."""
        target = prefix.lstrip("@").replace("\\", "/").strip().lower()
        matches = []
        try:
            root = self.workspace_root
            if not root.exists():
                return []

            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS]
                rel_dir = Path(dirpath).relative_to(root)
                rel_dir_str = "" if str(rel_dir) == "." else f"{rel_dir}/".replace("\\", "/")

                for d in dirnames:
                    full_rel = f"{rel_dir_str}{d}/"
                    base = d.lower()
                    full_low = full_rel.lower()
                    if not target:
                        if "/" not in full_rel.rstrip("/"):
                            matches.append((1, f"@{full_rel}", "folder"))
                    else:
                        if base.startswith(target):
                            matches.append((1, f"@{full_rel}", "folder"))
                        elif full_low.startswith(target):
                            matches.append((2, f"@{full_rel}", "folder"))
                        elif target in base:
                            matches.append((3, f"@{full_rel}", "folder"))
                        elif target in full_low:
                            matches.append((4, f"@{full_rel}", "folder"))

                for f in filenames:
                    full_rel = f"{rel_dir_str}{f}"
                    base = f.lower()
                    full_low = full_rel.lower()
                    suffix = Path(f).suffix or "file"
                    if not target:
                        if "/" not in full_rel:
                            matches.append((1, f"@{full_rel}", suffix))
                    else:
                        if base.startswith(target):
                            matches.append((1, f"@{full_rel}", suffix))
                        elif full_low.startswith(target):
                            matches.append((2, f"@{full_rel}", suffix))
                        elif target in base:
                            matches.append((3, f"@{full_rel}", suffix))
                        elif target in full_low:
                            matches.append((4, f"@{full_rel}", suffix))

            matches.sort(key=lambda x: (x[0], len(x[1]), x[1]))
        except Exception:
            pass

        return [(m[1], m[2]) for m in matches[:30]]

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor

        # 1. Slash commands at start of prompt
        if text_before_cursor.startswith("/"):
            query = text_before_cursor.lower()
            for cmd, desc in SLASH_COMMANDS_META:
                if cmd.lower().startswith(query):
                    yield Completion(
                        cmd,
                        start_position=-len(text_before_cursor),
                        display=cmd,
                        display_meta=desc,
                    )
            return

        # 2. Workspace file & directory mentions anywhere in text (@file)
        match = re.search(r"@([^\s]*)$", text_before_cursor)
        if match:
            tag_text = match.group(0)
            prefix = match.group(1)
            candidates = self._get_workspace_files(prefix)
            for file_tag, meta_desc in candidates:
                yield Completion(
                    file_tag,
                    start_position=-len(tag_text),
                    display=file_tag,
                    display_meta=meta_desc,
                )


# Backward compatibility alias
SlashCommandCompleter = SmartPromptCompleter


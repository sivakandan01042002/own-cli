from typing import Optional
from prompt_toolkit.completion import Completer, Completion


class SlashCommandCompleter(Completer):
    """Autocomplete for slash commands with rich metadata descriptions."""
    COMMANDS = [
        ("/help", "Display command guide"),
        ("/session", "List past coding sessions stored in Redis"),
        ("/sessions", "List past coding sessions stored in Redis"),
        ("/model", "Show active LLM provider"),
        ("/model gemini", "Switch to Google Gemini 3.8 Flash"),
        ("/model groq", "Switch to Groq GPT-OSS 120B"),
        ("/tools", "Inspect registered agent tools"),
        ("/history", "View session task history"),
        ("/clear", "Clear terminal screen"),
        ("/exit", "Quit QueryNest"),
    ]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd, desc in self.COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display_meta=desc)

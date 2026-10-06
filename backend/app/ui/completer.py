from prompt_toolkit.completion import Completer, Completion



class SlashCommandCompleter(Completer):
    """Autocomplete for slash commands with rich metadata descriptions."""
    COMMANDS = [
        ("/help", "Display command reference guide"),
        ("/model", "Show active LLM provider"),
        ("/model gemini", "Switch to Google Gemini"),
        ("/model groq", "Switch to Groq GPT-OSS 120B"),
        ("/session", "List past coding sessions stored in Redis"),
        ("/sessions", "List past coding sessions stored in Redis"),
        ("/session clear", "Reset session history in Redis"),
        ("/tools", "Inspect all registered agent tools"),
        ("/history", "View session task history"),
        ("/clear", "Clear terminal screen"),
        ("/exit", "Close QueryNest session"),
    ]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd, desc in self.COMMANDS:
                if cmd.lower().startswith(text.lower()):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta=desc,
                    )

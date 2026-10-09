"""Slash commands definitions, instructions, and autocomplete metadata."""
from typing import List, Tuple

# Full command specifications: (command, invocation_syntax, description)
COMMAND_DEFINITIONS: List[Tuple[str, str, str]] = [
    ("/help", "/help", "Display command reference guide"),
    ("/login", "/login", "Sign in with Google OAuth 2.0"),
    ("/me", "/me", "View active user profile and email"),
    ("/whoami", "/whoami", "Inspect current user profile and workspace trust"),
    ("/logout", "/logout", "Sign out and clear local credentials"),
    ("/model", "/model", "Interactively select and switch active AI model"),
    ("/mode", "/mode", "Toggle execution mode (Normal Safe vs Auto Accept-All)"),
    ("/mode normal", "/mode normal", "Set mode to normal (safe permission gate)"),
    ("/mode accept-edits", "/mode accept-edits", "Set mode to accept-edits (auto execution)"),
    ("/new", "/new", "Start a fresh multi-turn conversation thread"),
    ("/sessions", "/sessions", "List & restore past coding sessions from local storage"),
    ("/session clear", "/session clear", "Reset session history"),
    ("/tools", "/tools", "Inspect all registered agent tools and signatures"),
    ("/history", "/history", "View tasks submitted in the current live terminal session"),
    ("/clear", "/clear", "Clear terminal screen"),
    ("/exit", "/exit", "Close QueryNest session"),
    ("/quit", "/quit", "Close QueryNest session"),
]

# Autocomplete metadata tuples: (command_prefix, short_description)
SLASH_COMMANDS_META: List[Tuple[str, str]] = [
    (cmd, desc) for cmd, _, desc in COMMAND_DEFINITIONS
]

# List of command strings for direct lookups
SLASH_COMMANDS_LIST: List[str] = [cmd for cmd, _, _ in COMMAND_DEFINITIONS]

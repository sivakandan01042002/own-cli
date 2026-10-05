import re
from typing import Tuple, Literal, Optional

# Keywords for casual greetings
GREETING_PATTERNS = [
    r"^hi\b",
    r"^hello\b",
    r"^hey\b",
    r"^who are you\b",
    r"^what can you do\b",
    r"^help\b",
    r"^good (morning|afternoon|evening)\b",
]

# Prompt injection, destructive, or NSFW / off-topic patterns
BLOCKED_PATTERNS = [
    # Injections
    r"ignore (all )?previous instructions",
    r"disregard (all )?system (prompts|rules)",
    r"reveal (your )?system prompt",
    r"leak (your )?instructions",
    # Destructive
    r"format\s+[a-z]:",
    r"rmdir\s+/s",
    r"del\s+/f\s+/s\s+/q",
    r"drop\s+database",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",
    # NSFW / Inappropriate
    r"\b(sex|porn|nude|nsfw|xxx|khalifa)\b",
]


def is_greeting(text: str) -> bool:
    """Checks if input is a casual greeting."""
    cleaned = text.strip().lower()
    return any(re.search(p, cleaned) for p in GREETING_PATTERNS)


def get_greeting_response() -> str:
    """Returns a simple, clean greeting message."""
    return "👋 **Hi! I'm QueryNest.** I can help you plan architecture, write code, run unit tests, and auto-fix bugs.\n\nType a coding task to begin, or **/help** for commands."



def check_safety_guardrails(text: str) -> Optional[str]:
    """
    Scans input for prompt injection, destructive commands, or off-topic/NSFW queries.
    """
    cleaned = text.strip().lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cleaned):
            return "I am an AI coding assistant focused on software engineering. Please provide a programming or technical task."
    return None



def triage_user_input(text: str) -> Tuple[Literal["command", "greeting", "unsafe", "task"], str]:
    """
    Classifies user input:
    - 'command': Starts with '/'
    - 'greeting': Casual greeting
    - 'unsafe': Violates safety rules or off-topic
    - 'task': Valid coding task
    """
    trimmed = text.strip()
    if not trimmed:
        return "greeting", get_greeting_response()

    if trimmed.startswith("/"):
        return "command", trimmed

    safety_error = check_safety_guardrails(trimmed)
    if safety_error:
        return "unsafe", safety_error

    if is_greeting(trimmed):
        return "greeting", get_greeting_response()

    return "task", trimmed

import re
from typing import Tuple, Literal, Optional, Dict, Any

# Strict regex patterns for standalone greetings (entire text must match greeting intent)
PURE_GREETING_PATTERNS = [
    r"^(hi|hello|hey|howdy|greetings|sup|yo)(\s+(there|querynest|bot|assistant|friend|everyone))?[\s!.]*$",
    r"^(who\s+are\s+you|what\s+can\s+you\s+do|what\s+is\s+your\s+name)[\s?!.]*$",
    r"^good\s+(morning|afternoon|evening|day)[\s!.]*$",
    r"^help[\s!.]*$",
]

# Conversational prefix stripper (e.g. "Hi, ...", "Hey QueryNest, ...")
CONVERSATIONAL_PREFIX_REGEX = re.compile(
    r"^(hi|hello|hey|howdy|good\s+(morning|afternoon|evening))\s*[,!.:-]*\s*(querynest\s*[,!.:-]*\s*)?",
    re.IGNORECASE,
)

# High-risk destructive or prompt-injection patterns
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
    # Inappropriate / NSFW
    r"\b(sex|porn|nude|nsfw|xxx|khalifa)\b",
]

# Technical indicators that strongly signal a coding task/question
TECHNICAL_KEYWORDS = {
    "cli.py", "main.py", "config.py", "nodes.py", "state.py", "edges.py", "prompts.py",
    "python", "fastapi", "pytest", "redis", "langgraph", "endpoint", "api", "function",
    "class", "method", "test", "build", "create", "fix", "debug", "run", "why", "what",
    "how", "purpose", "explain", "refactor", "import", "package", "module", "code",
    "docker", "database", "schema", "table", "crud", "query", "route", "git",
}


def calculate_intent_scores(text: str) -> Dict[str, float]:
    """
    JEV-style Calibrated Intent Analysis:
    Calculates weighted confidence percentages for 'greeting' vs 'task'
    rather than blind keyword matching.
    """
    cleaned = text.strip().lower()
    words = re.findall(r"\b\w+(?:\.\w+)?\b", cleaned)
    total_words = len(words)

    if total_words == 0:
        return {"greeting": 1.0, "task": 0.0}

    # 1. Check if the entire input matches a standalone greeting
    for pattern in PURE_GREETING_PATTERNS:
        if re.match(pattern, cleaned):
            return {"greeting": 0.99, "task": 0.01}

    # 2. Count technical / actionable words
    tech_count = sum(1 for w in words if w in TECHNICAL_KEYWORDS or "." in w or "_" in w)
    question_marks = text.count("?")

    # 3. Calculate ratios
    greeting_prefix_match = CONVERSATIONAL_PREFIX_REGEX.match(cleaned)
    greeting_prefix_len = len(greeting_prefix_match.group(0).split()) if greeting_prefix_match else 0

    actionable_words = total_words - greeting_prefix_len
    task_ratio = (actionable_words + (tech_count * 2) + (question_marks * 2)) / (total_words + 2)

    task_confidence = min(0.99, max(0.01, task_ratio))
    greeting_confidence = 1.0 - task_confidence

    return {
        "greeting": round(greeting_confidence, 2),
        "task": round(task_confidence, 2),
    }


def is_pure_greeting(text: str) -> bool:
    """Checks if input is strictly a casual greeting with no technical inquiry."""
    scores = calculate_intent_scores(text)
    return scores["greeting"] > 0.70


def get_greeting_response() -> str:
    """Returns a simple, clean greeting message."""
    return "👋 **Hi! I'm QueryNest.** I can help you plan architecture, write code, run unit tests, and auto-fix bugs.\n\nType a coding task to begin, or **/help** for commands."


def check_safety_guardrails(text: str) -> Optional[str]:
    """Scans input for destructive commands or malicious injections."""
    cleaned = text.strip().lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cleaned):
            return "I am an AI coding assistant focused on software engineering. Please provide a programming or technical task."
    return None


def triage_user_input(text: str) -> Tuple[Literal["command", "greeting", "unsafe", "task"], str]:
    """
    Classifies user input using calibrated percentage confidence:
    - 'command': Starts with '/'
    - 'greeting': Standalone casual greeting (Greeting Confidence > 70%)
    - 'unsafe': Violates safety rules
    - 'task': Valid coding task or technical inquiry (Task Confidence >= 30%)
    """
    trimmed = text.strip()
    if not trimmed:
        return "greeting", get_greeting_response()

    if trimmed.startswith("/"):
        return "command", trimmed

    safety_error = check_safety_guardrails(trimmed)
    if safety_error:
        return "unsafe", safety_error

    scores = calculate_intent_scores(trimmed)

    # Pure greeting with no substantive task
    if scores["greeting"] > 0.70:
        return "greeting", get_greeting_response()

    # Extract clean task by stripping conversational prefix if present
    cleaned_task = CONVERSATIONAL_PREFIX_REGEX.sub("", trimmed).strip()
    task_payload = cleaned_task if cleaned_task else trimmed

    return "task", task_payload

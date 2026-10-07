import re
from typing import Tuple, Literal, Optional, Dict, List


# Strict regex patterns for standalone greetings and pleasantries
PURE_GREETING_PATTERNS = [
    r"^(hi|hello|hey|howdy|greetings|sup|yo)(\s+(there|querynest|bot|assistant|friend|everyone))?[\s!.]*$",
    r"^(who\s+are\s+you|what\s+can\s+you\s+do|what\s+is\s+your\s+name)[\s?!.]*$",
    r"^good\s+(morning|afternoon|evening|day)[\s!.]*$",
    r"^(great|awesome|cool|nice|perfect|good|ok|okay|sounds good|thanks|thank you|thx|cheers|got it|understood|all good)[\s,!.]*(\s*(thanks|thank you|querynest|bro))?[\s!.]*$",
    r"^help[\s!.]*$",
]

ACKNOWLEDGMENT_PATTERNS = [
    r"^(great|awesome|cool|nice|perfect|good|ok|okay|sounds good|thanks|thank you|thx|cheers|got it|understood|all good)[\s,!.]*(\s*(thanks|thank you|querynest|bro))?[\s!.]*$",
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
    r"\b(sex|porn|nude|nsfw|xxx)\b",
]

# Technical indicators that strongly signal a coding task/question
TECHNICAL_KEYWORDS = {
    "cli.py", "main.py", "config.py", "nodes.py", "state.py", "edges.py", "prompts.py",
    "python", "fastapi", "pytest", "redis", "langgraph", "endpoint", "api", "function",
    "class", "method", "test", "build", "create", "fix", "debug", "run", "why", "what",
    "how", "purpose", "explain", "refactor", "import", "package", "module", "code",
    "docker", "database", "schema", "table", "crud", "query", "route", "git",
}


# Action verbs indicating a substantive coding or developer request
ACTION_VERBS = {
    "build", "create", "make", "fix", "debug", "add", "update", "modify",
    "change", "delete", "remove", "write", "test", "run", "execute", "install",
    "commit", "push", "pull", "diff", "checkout", "refactor", "explain",
    "show", "list", "check", "inspect", "find", "search", "generate",
    "format", "lint", "deploy", "setup", "start", "stop", "restart",
}

# Inquisitive question triggers
QUESTION_WORDS = {"why", "how", "what", "where", "who", "when", "which"}

# Evaluative praise and sentiment expressions
PRAISE_WORDS = {
    "great", "awesome", "impressive", "amazing", "wonderful", "fantastic",
    "super", "superb", "cool", "nice", "perfect", "good", "love", "neat",
    "slick", "clean", "works", "worked", "helpful", "thanks", "thank",
    "appreciated", "appreciate", "brilliant", "excellent", "well", "done",
    "job", "work", "fine", "cheers", "thx",
}


def is_acknowledgment_or_pleasantry(text: str) -> bool:
    """
    Semantically checks if input is an evaluative praise, conversational pleasantry, or greeting
    by analyzing action verbs, technical code targets, and sentiment intent.
    """
    clean = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = clean.split()
    if not words:
        return True

    has_praise = any(w in PRAISE_WORDS for w in words)
    has_action = any(w in ACTION_VERBS for w in words)
    has_question = any(w in QUESTION_WORDS for w in words)
    has_code_entity = bool(re.search(r"\b\w+\.(py|js|ts|tsx|jsx|json|md|yaml|yml|html|css|sh|bat|txt|sql)\b", text.lower())) or bool(re.search(r"[/\\]\w+", text))

    # If it contains praise and has no actionable code entity or imperative action
    if has_praise and not (has_action or has_question or has_code_entity):
        return True

    # If phrase is short evaluative praise without technical targets (e.g. 'great work thanks', 'worked well')
    if has_praise and len(words) <= 6 and not has_code_entity and not has_question:
        if not (has_action and any(w in {"file", "code", "repo", "bug", "test", "api", "branch", "commit"} for w in words)):
            return True

    return False


def calculate_intent_scores(text: str) -> Dict[str, float]:
    """
    JEV-style Calibrated Intent Analysis:
    Calculates weighted confidence percentages for 'greeting' vs 'task'
    using semantic action-verb and technical entity analysis.
    """
    cleaned = text.strip().lower()
    words = re.findall(r"\b\w+(?:\.\w+)?\b", cleaned)
    total_words = len(words)

    if total_words == 0:
        return {"greeting": 1.0, "task": 0.0}

    # 1. Semantic praise / pleasantry check
    if is_acknowledgment_or_pleasantry(text):
        return {"greeting": 0.99, "task": 0.01}

    for pattern in PURE_GREETING_PATTERNS:
        if re.match(pattern, cleaned):
            return {"greeting": 0.99, "task": 0.01}

    # 2. Count technical / actionable words
    tech_count = sum(1 for w in words if w in TECHNICAL_KEYWORDS or w in ACTION_VERBS)
    has_code_entity = bool(re.search(r"\b\w+\.(py|js|ts|tsx|jsx|json|md|yaml|yml|html|css|sh|bat|txt|sql)\b", cleaned)) or bool(re.search(r"[/\\]\w+", cleaned))
    if has_code_entity:
        tech_count += 3

    question_marks = text.count("?")

    # 3. Calculate calibrated ratios
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


def get_greeting_response(text: str = "") -> str:
    """Returns a concise, compact greeting or polite acknowledgment message."""
    if is_acknowledgment_or_pleasantry(text):
        return "[white]You're very welcome! Let me know if you need anything else.[/white]"
    return "[white]👋 [bold]Hi! I'm QueryNest[/bold] — your multi-agent coding assistant. Type a task or [bold cyan]/help[/bold cyan] for commands.[/white]"


def check_safety_guardrails(text: str) -> Optional[str]:
    """Scans input for destructive commands or malicious injections."""
    cleaned = text.strip().lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cleaned):
            return "I am an AI coding assistant focused on software engineering. Please provide a programming or technical task."
    return None


CLIPBOARD_IMAGE_REGISTRY: Dict[str, str] = {}

IMAGE_TAG_REGEX = re.compile(
    r"(?:@image|/vision)\s+([^\s\"']+|\"[^\"]+\"|'[^']+')",
    re.IGNORECASE,
)

HASH_IMAGE_REGEX = re.compile(
    r"(#Image\d*|#image\d*|#Image:\d+|#image:\d+)",
    re.IGNORECASE,
)


def register_clipboard_image(image_path: str, tag: Optional[str] = None) -> str:
    """Registers a clipboard image path to a clean #Image / #Image1 tag."""
    if not tag:
        count = len(CLIPBOARD_IMAGE_REGISTRY) + 1
        tag = "#Image" if count == 1 else f"#Image{count}"
    CLIPBOARD_IMAGE_REGISTRY[tag.lower()] = image_path
    CLIPBOARD_IMAGE_REGISTRY[tag] = image_path
    # Also register #Image1 as alias for #Image
    if tag == "#Image":
        CLIPBOARD_IMAGE_REGISTRY["#image1"] = image_path
        CLIPBOARD_IMAGE_REGISTRY["#Image1"] = image_path
    return tag


def extract_prompt_images(text: str) -> Tuple[str, List[str]]:
    """
    Extracts image paths marked with '#Image', '#Image1', '@image <path>', or '/vision <path>'.
    Returns (cleaned_prompt_text, list_of_image_paths).
    """
    found_paths = []

    # 1. Check explicit @image or /vision syntax
    for match in IMAGE_TAG_REGEX.finditer(text):
        path_str = match.group(1).strip("\"'")
        found_paths.append(path_str)

    # 2. Check #Image / #Image1 / #Image2 tags
    for match in HASH_IMAGE_REGEX.finditer(text):
        tag = match.group(1)
        tag_key = tag.lower()
        if tag in CLIPBOARD_IMAGE_REGISTRY:
            found_paths.append(CLIPBOARD_IMAGE_REGISTRY[tag])
        elif tag_key in CLIPBOARD_IMAGE_REGISTRY:
            found_paths.append(CLIPBOARD_IMAGE_REGISTRY[tag_key])
        elif CLIPBOARD_IMAGE_REGISTRY:
            latest_path = list(CLIPBOARD_IMAGE_REGISTRY.values())[-1]
            found_paths.append(latest_path)
        else:
            # Check latest file on disk in cache dir
            from app.core.config import settings
            cache_dir = settings.WORKSPACE_ROOT / ".querynest_cache" / "clipboard"
            if cache_dir.exists():
                pngs = sorted(cache_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                if pngs:
                    found_paths.append(str(pngs[0]))

    # Clean tags from text
    cleaned_prompt = IMAGE_TAG_REGEX.sub("", text)
    cleaned_prompt = HASH_IMAGE_REGEX.sub("", cleaned_prompt).strip()

    # If user provided only an image tag without description, default to visual analysis
    if found_paths and not cleaned_prompt:
        cleaned_prompt = "Analyze and describe the attached image in detail. Extract and explain all key visual components, text, layout structure, color scheme, and UI elements."

    return cleaned_prompt, found_paths


def triage_user_input(text: str) -> Tuple[Literal["command", "greeting", "unsafe", "task"], str]:
    """
    Classifies user input using calibrated percentage confidence:
    - 'command': Starts with '/' (except /vision which is a multimodal task)
    - 'greeting': Standalone casual greeting / acknowledgment (Greeting Confidence > 70%)
    - 'unsafe': Violates safety rules
    - 'task': Valid coding task or technical inquiry (Task Confidence >= 30%)
    """
    trimmed = text.strip()
    if not trimmed:
        return "greeting", get_greeting_response(trimmed)

    # Route /vision as a multimodal task instead of menu command
    if trimmed.startswith("/vision"):
        return "task", trimmed

    if trimmed.startswith("/"):
        return "command", trimmed

    safety_error = check_safety_guardrails(trimmed)
    if safety_error:
        return "unsafe", safety_error

    scores = calculate_intent_scores(trimmed)

    # Pure greeting / pleasantry with no substantive task
    if scores["greeting"] > 0.70:
        return "greeting", get_greeting_response(trimmed)

    # Extract clean task by stripping conversational prefix if present
    cleaned_task = CONVERSATIONAL_PREFIX_REGEX.sub("", trimmed).strip()
    task_payload = cleaned_task if cleaned_task else trimmed

    return "task", task_payload

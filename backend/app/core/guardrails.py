import re
from typing import Tuple, Literal, Optional, Dict, List, Any


# Strict regex patterns for standalone greetings and pleasantries
PURE_GREETING_PATTERNS = [
    r"^(hi|hello|hey|howdy|greetings|sup|yo)(\s+(there|querynest|bot|assistant|friend|everyone))?[\s!.]*$",
    r"^good\s+(morning|afternoon|evening|day)[\s!.]*$",
]

ACKNOWLEDGMENT_PATTERNS = [
    r"^(thanks|thank you|thx|cheers|got it|understood|all good)[\s,!.]*(\s*(thanks|thank you|querynest|bro))?[\s!.]*$",
    r"^(ok|okay|sounds good)[\s,!.]*$",
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
]

# Technical indicators that strongly signal a coding task/question
TECHNICAL_KEYWORDS = {
    "cli.py", "main.py", "config.py", "nodes.py", "state.py", "edges.py", "prompts.py",
    "python", "fastapi", "pytest", "redis", "langgraph", "endpoint", "api", "function",
    "class", "method", "test", "build", "create", "fix", "debug", "run", "why", "what",
    "how", "purpose", "explain", "refactor", "import", "package", "module", "code",
    "docker", "database", "schema", "table", "crud", "query", "route", "git",
}

ACTION_VERBS = {
    "build", "create", "make", "fix", "debug", "add", "update", "modify",
    "change", "delete", "remove", "write", "test", "run", "execute", "install",
    "commit", "push", "pull", "diff", "checkout", "refactor", "explain",
    "show", "list", "check", "inspect", "find", "search", "generate",
    "format", "lint", "deploy", "setup", "start", "stop", "restart",
}

QUESTION_WORDS = {"why", "how", "what", "where", "who", "when", "which"}


def is_acknowledgment_or_pleasantry(text: str) -> bool:
    """Checks if input is strictly a short standalone acknowledgment like 'thanks' or 'thank you'."""
    clean = text.strip().lower()
    for pattern in ACKNOWLEDGMENT_PATTERNS:
        if re.match(pattern, clean):
            return True
    return False


def is_pure_greeting(text: str) -> bool:
    """Checks if input is strictly a casual standalone greeting."""
    clean = text.strip().lower()
    for pattern in PURE_GREETING_PATTERNS:
        if re.match(pattern, clean):
            return True
    return False


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


def extract_prompt_files(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extracts @file and @folder references from prompt text and safely reads their contents.
    Resolves both exact relative paths and workspace basenames (e.g. @cli.py -> backend/app/cli.py).
    Excludes @image tags (handled by extract_prompt_images).
    """
    from app.core.config import settings
    from pathlib import Path

    IGNORE_DIRS = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        "node_modules",
        ".vscode",
        ".idea",
        ".querynest_cache",
    }

    pinned_files: List[Dict[str, Any]] = []
    root = settings.WORKSPACE_ROOT.resolve()

    # Find candidate @tags
    candidates = re.findall(r"@([^\s\"',]+)", text)
    seen_paths = set()

    for cand in candidates:
        cand_clean = cand.strip("\"'").rstrip("?.!,;:)`")
        if not cand_clean or cand_clean.lower().startswith("image"):
            continue

        target_path: Optional[Path] = None

        # 1. Direct path check
        try:
            direct = (root / cand_clean).resolve()
            if str(direct).startswith(str(root)) and direct.exists():
                target_path = direct
        except Exception:
            pass

        # 2. Workspace search by basename or relative suffix
        if not target_path:
            try:
                for p in root.rglob("*"):
                    if any(part in IGNORE_DIRS for part in p.parts):
                        continue
                    rel = p.relative_to(root)
                    rel_str = str(rel).replace("\\", "/")
                    if (
                        p.name.lower() == cand_clean.lower()
                        or p.name.lower() == f"{cand_clean}.py".lower()
                        or rel_str.lower().endswith(cand_clean.lower())
                    ):
                        target_path = p
                        break
            except Exception:
                pass

        if not target_path or not target_path.exists():
            continue

        try:
            rel_path = target_path.relative_to(root)
            rel_path_str = str(rel_path).replace("\\", "/")
            if rel_path_str in seen_paths:
                continue
            seen_paths.add(rel_path_str)

            if target_path.is_file():
                content = target_path.read_text(encoding="utf-8", errors="replace")
                # Limit very large files to first 500 lines to prevent token blowup
                lines = content.splitlines()
                if len(lines) > 500:
                    content = "\n".join(lines[:500]) + f"\n... (truncated, total {len(lines)} lines)"
                pinned_files.append({
                    "path": rel_path_str,
                    "type": "file",
                    "content": content,
                })
            elif target_path.is_dir():
                entries = [
                    f"📄 {p.relative_to(root)}"
                    for p in target_path.rglob("*")
                    if p.is_file() and not any(part in IGNORE_DIRS for part in p.parts)
                ]
                pinned_files.append({
                    "path": rel_path_str,
                    "type": "directory",
                    "content": "\n".join(entries[:60]),
                })
        except Exception:
            continue

    return text, pinned_files


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

    if is_acknowledgment_or_pleasantry(trimmed):
        return "greeting", "[white]You're very welcome! Let me know if you need anything else.[/white]"

    if is_pure_greeting(trimmed):
        return "greeting", "[white]👋 [bold]Hi! I'm QueryNest[/bold] — your multi-agent coding assistant. Type a task or [bold cyan]/help[/bold cyan] for commands.[/white]"

    # Extract clean task by stripping conversational prefix if present
    cleaned_task = CONVERSATIONAL_PREFIX_REGEX.sub("", trimmed).strip()
    task_payload = cleaned_task if cleaned_task else trimmed

    return "task", task_payload

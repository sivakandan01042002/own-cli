import os
import re
from pathlib import Path
from typing import Tuple, Literal, Optional, Dict, List, Any, Union

from app.constants.guardrails import (
    PURE_GREETING_PATTERNS,
    ACKNOWLEDGMENT_PATTERNS,
    BLOCKED_INPUT_PATTERNS,
    DESTRUCTIVE_COMMAND_PATTERNS,
    MODIFYING_COMMAND_KEYWORDS,
    TECHNICAL_KEYWORDS,
    ACTION_VERBS,
    QUESTION_WORDS,
    DEFAULT_GREETING_MSG,
    DEFAULT_ACKNOWLEDGMENT_MSG,
    DEFAULT_SAFETY_DENIAL_MSG,
)
from app.constants.workspace import DEFAULT_IGNORE_DIRS
from app.core.config import settings


class SecurityViolationError(Exception):
    """Raised when an operation violates workspace sandboxing or security policy."""
    pass


def assert_inside_workspace(path: Union[str, Path], workspace_root: Optional[Union[str, Path]] = None) -> Path:
    """
    Ensures that a path is strictly inside the workspace boundary using canonical resolution.
    Defends against:
    - Path traversal ('../../etc/passwd')
    - Prefix collision attacks ('/workspace-attacker' matching '/workspace')
    - Symlink escapes
    """
    ws_root = (Path(workspace_root) if workspace_root else settings.WORKSPACE_ROOT).resolve()
    resolved = (ws_root / Path(path)).resolve() if not Path(path).is_absolute() else Path(path).resolve()

    try:
        is_rel = resolved.is_relative_to(ws_root)
    except AttributeError:
        # Fallback for Python < 3.9
        is_rel = os.path.commonpath([str(resolved), str(ws_root)]) == str(ws_root)

    if not is_rel:
        raise SecurityViolationError(
            f"Security Sandbox Violation: Access denied for path '{resolved}' outside workspace '{ws_root}'"
        )

    return resolved


def wrap_untrusted_content(content: str, source: str = "repository") -> str:
    """
    Defense-in-depth wrapper: isolates untrusted file/web/browser content
    so LLM reasoning recognizes it as data rather than instructions.
    """
    return f'<untrusted_repository_content source="{source}">\n{content}\n</untrusted_repository_content>'


# Conversational prefix stripper (e.g. "Hi, ...", "Hey QueryNest, ...")
CONVERSATIONAL_PREFIX_REGEX = re.compile(
    r"^(hi|hello|hey|howdy|good\s+(morning|afternoon|evening))\s*[,!.:-]*\s*(querynest\s*[,!.:-]*\s*)?",
    re.IGNORECASE,
)


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
        return DEFAULT_ACKNOWLEDGMENT_MSG
    return DEFAULT_GREETING_MSG


def check_safety_guardrails(text: str) -> Optional[str]:
    """Scans input for destructive commands or malicious injections."""
    cleaned = text.strip().lower()
    for pattern in BLOCKED_INPUT_PATTERNS:
        if re.search(pattern, cleaned):
            return DEFAULT_SAFETY_DENIAL_MSG
    return None


def audit_terminal_command(command: str) -> Tuple[str, str]:
    """
    Audits a shell command against security tiers:
    - 'blocked': Dangerous destructive command (Execution denied)
    - 'modifying': Modifying/network/package operation (Requires explicit user confirmation)
    - 'safe': Read-only or safe local command (e.g. pytest, git status, ls)
    """
    clean = command.strip()
    clean_lower = clean.lower()

    # Tier 1: Check blocked destructive patterns
    for pat in DESTRUCTIVE_COMMAND_PATTERNS:
        if re.search(pat, clean_lower):
            return "blocked", f"Execution blocked by security policy: '{clean}' is potentially destructive."

    # Tier 2: Check modifying operations
    for kw in MODIFYING_COMMAND_KEYWORDS:
        if kw in clean_lower:
            return "modifying", f"Modifying operation: '{clean}' modifies packages, services, or repository state."

    # Tier 3: Safe / Read-Only
    return "safe", clean



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
                    if any(part in DEFAULT_IGNORE_DIRS for part in p.parts):
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
                    if p.is_file() and not any(part in DEFAULT_IGNORE_DIRS for part in p.parts)
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

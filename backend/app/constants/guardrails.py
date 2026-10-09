"""Guardrails, regex patterns, safety tiers, and classification keywords."""
from typing import List, Set

# Standalone Greetings & Pleasantries
PURE_GREETING_PATTERNS: List[str] = [
    r"^(hi|hello|hey|howdy|greetings|sup|yo)(\s+(there|querynest|bot|assistant|friend|everyone))?[\s!.]*$",
    r"^good\s+(morning|afternoon|evening|day)[\s!.]*$",
]

ACKNOWLEDGMENT_PATTERNS: List[str] = [
    r"^(thanks|thank you|thx|cheers|got it|understood|all good)[\s,!.]*(\s*(thanks|thank you|querynest|bro))?[\s!.]*$",
    r"^(ok|okay|sounds good)[\s,!.]*$",
]

# Prompt Injections & Malicious Input Patterns
BLOCKED_INPUT_PATTERNS: List[str] = [
    r"ignore (all )?previous instructions",
    r"disregard (all )?system (prompts|rules)",
    r"reveal (your )?system prompt",
    r"leak (your )?instructions",
    r"format\s+[a-z]:",
    r"rmdir\s+/s",
    r"del\s+/f\s+/s\s+/q",
    r"drop\s+database",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",
]

# Tier 1: Strictly Blocked Destructive System Commands
DESTRUCTIVE_COMMAND_PATTERNS: List[str] = [
    r"format(-volume)?(\s+|$)",
    r"rmdir\s+/[sS]",
    r"del\s+/[fF]\s+/[sS]",
    r"del\s+.*[/\\]windows",
    r"rm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+[/~]",
    r"drop\s+database",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",
    r"mkfs\.",
    r"dd\s+if=.*of=/dev/",
]

# Tier 2: Modifying / Package / Network Commands (Prompt Confirmation)
MODIFYING_COMMAND_KEYWORDS: List[str] = [
    "install", "uninstall", "npm i", "npm add", "npm remove",
    "pip install", "pip uninstall", "docker run", "docker stop", "docker rm",
    "git push", "git reset --hard", "git clean -f", "dropdb", "createdb",
    "kill", "taskkill", "chmod -R", "chown -R", "rm ", "del ", "rmdir "
]

# Technical Keywords signalling a Coding Task
TECHNICAL_KEYWORDS: Set[str] = {
    "cli.py", "main.py", "config.py", "nodes.py", "state.py", "edges.py", "prompts.py",
    "python", "fastapi", "pytest", "redis", "langgraph", "endpoint", "api", "function",
    "class", "method", "test", "build", "create", "fix", "debug", "run", "why", "what",
    "how", "purpose", "explain", "refactor", "import", "package", "module", "code",
    "docker", "database", "schema", "table", "crud", "query", "route", "git",
}

ACTION_VERBS: Set[str] = {
    "build", "create", "make", "fix", "debug", "add", "update", "modify",
    "change", "delete", "remove", "write", "test", "run", "execute", "install",
    "commit", "push", "pull", "diff", "checkout", "refactor", "explain",
    "show", "list", "check", "inspect", "find", "search", "generate",
    "format", "lint", "deploy", "setup", "start", "stop", "restart",
}

QUESTION_WORDS: Set[str] = {"why", "how", "what", "where", "who", "when", "which"}

# Standard Guardrail Response Messages
DEFAULT_GREETING_MSG: str = "[white]👋 [bold]Hi! I'm QueryNest[/bold] — your multi-agent coding assistant. Type a task or [cmd]/help[/cmd] for commands.[/white]"
DEFAULT_ACKNOWLEDGMENT_MSG: str = "[white]You're very welcome! Let me know if you need anything else.[/white]"
DEFAULT_SAFETY_DENIAL_MSG: str = "I am an AI coding assistant focused on software engineering. Please provide a programming or technical task."

# Multi-Agent Execution Limits & Invariants
MAX_TOOL_CALLS_PER_TURN: int = 8
MAX_DIRECT_TOOL_ITERATIONS: int = 5
MAX_INSPECTOR_TOOL_ITERATIONS: int = 5
MAX_CODER_TOOL_ITERATIONS: int = 10
MAX_REPAIR_RETRIES: int = 3

# Allowlisted Tool Subcommands & Runners
READ_ONLY_GIT_SUBCOMMANDS: Set[str] = {
    "status", "diff", "log", "branch", "show", "ls-files"
}

ALLOWLISTED_TEST_RUNNERS: Set[str] = {
    "pytest",
    "python -m pytest",
    "npm test",
    "npm run test",
    "go test",
    "cargo test",
}


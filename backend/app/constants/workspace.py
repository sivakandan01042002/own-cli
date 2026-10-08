"""Workspace and filesystem constants."""
from typing import Set

DEFAULT_IGNORE_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    ".vscode",
    ".idea",
    ".querynest_cache",
    "assets",
    ".assets",
}

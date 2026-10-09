"""Workspace and filesystem constants."""
from typing import Set

DEFAULT_IGNORE_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".vscode",
    ".idea",
    ".querynest_cache",
    "assets",
    ".assets",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".ruff_cache",
}

SOURCE_CODE_EXTENSIONS: Set[str] = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx",
    ".go", ".rs", ".java", ".cpp", ".c", ".h",
    ".cs", ".rb", ".php", ".sql", ".mjs", ".cjs"
}

BUILD_CONFIG_FILES: Set[str] = {
    "package.json", "pyproject.toml", "requirements.txt",
    "Cargo.toml", "go.mod", "Makefile", "Dockerfile",
    "tsconfig.json", "pytest.ini", "setup.py", "setup.cfg"
}

DOC_AND_MEDIA_EXTENSIONS: Set[str] = {
    ".md", ".txt", ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".svg", ".ico", ".pdf", ".csv", ".docx", ".log"
}

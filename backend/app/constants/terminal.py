"""Terminal, subprocess, and execution security constants for QueryNest."""
from typing import Set

# Standard system environment variable allowlist for subprocess isolation
ENV_ALLOWLIST: Set[str] = {
    # System identification & shell paths
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME",
    "LANG", "LC_ALL", "LC_CTYPE", "TERM", "SHELL", "TZ",
    "OS", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
    # Python & Conda virtual environment context
    "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV",
    "CONDA_PREFIX", "CONDA_PROMPT_MODIFIER", "CONDA_PYTHON_EXE", "CONDA_EXE",
}

DEFAULT_SUBPROCESS_TIMEOUT: int = 60
MAX_SUBPROCESS_TIMEOUT: int = 300
MIN_SUBPROCESS_TIMEOUT: int = 1
MAX_OUTPUT_BUFFER_CHARS: int = 50_000

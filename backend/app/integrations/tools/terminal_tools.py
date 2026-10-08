import asyncio
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, Optional, Set

from langchain_core.tools import tool
from app.constants.terminal import (
    ENV_ALLOWLIST,
    DEFAULT_SUBPROCESS_TIMEOUT,
    MAX_SUBPROCESS_TIMEOUT,
    MIN_SUBPROCESS_TIMEOUT,
    MAX_OUTPUT_BUFFER_CHARS,
)
from app.core.config import settings
from app.core.guardrails import audit_terminal_command

# Currently running child process (for SIGINT / cancellation cleanup)
_ACTIVE_SUBPROCESS: Optional[subprocess.Popen] = None
_SUBPROCESS_LOCK = threading.Lock()



def get_sanitized_environment(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Builds an allowlist-based sanitized environment dictionary for subprocess execution.
    Strictly excludes all API keys, secrets, auth tokens, and sensitive credentials.
    """
    sanitized: Dict[str, str] = {}
    current_env = os.environ

    for key, val in current_env.items():
        key_upper = key.upper()
        if key_upper in ENV_ALLOWLIST:
            sanitized[key] = val

    if extra_env:
        for k, v in extra_env.items():
            # Never permit sensitive keys even if passed in extra_env
            k_upper = k.upper()
            if not any(blocked in k_upper for blocked in ["API_KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH"]):
                sanitized[k] = v

    return sanitized


def kill_process_tree(proc: subprocess.Popen):
    """
    Terminates a subprocess and all of its child processes across Windows and POSIX.
    """
    if proc is None or proc.poll() is not None:
        return

    pid = proc.pid
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=5,
            )
        else:
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def cancel_active_subprocess():
    """Cancels any currently running terminal subprocess."""
    global _ACTIVE_SUBPROCESS
    with _SUBPROCESS_LOCK:
        if _ACTIVE_SUBPROCESS is not None:
            kill_process_tree(_ACTIVE_SUBPROCESS)
            _ACTIVE_SUBPROCESS = None


@tool
def run_terminal_command(command: str, timeout: int = 60) -> str:
    """
    Executes shell and system commands in the project workspace root.
    
    Supported use cases:
    - Package Managers: 'npm install', 'pip install <pkg>', 'yarn add <pkg>', 'pnpm i', 'uv pip install'
    - API & 3rd-Party Testing: 'curl -i https://...', 'http GET https://...', REST calls
    - Build & Containers: 'docker build ...', 'docker-compose up', 'make', 'cargo build'
    - System Scripts: PowerShell ('powershell -Command "..."'), Bash ('.sh'), Batch ('.bat')
    - Testing & Linters: 'pytest', 'flake8', 'mypy', 'black --check'
    
    Args:
        command: The shell command line string to execute.
        timeout: Maximum execution time in seconds (default is 60, can be set up to 300 for long builds/installs).
        
    Returns:
        Structured output containing exit code, stdout, and stderr.
    """
    global _ACTIVE_SUBPROCESS

    # Safety check against destructive disk/system damage
    tier, reason = audit_terminal_command(command)
    if tier == "blocked":
        return f"Error: {reason}"

    # Clamp timeout between 1s and 300s
    actual_timeout = max(1, min(timeout, 300))
    sanitized_env = get_sanitized_environment()

    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(settings.WORKSPACE_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sanitized_env,
        )

        with _SUBPROCESS_LOCK:
            _ACTIVE_SUBPROCESS = proc

        try:
            stdout, stderr = proc.communicate(timeout=actual_timeout)
        except subprocess.TimeoutExpired:
            kill_process_tree(proc)
            return f"Error: Command timed out after {actual_timeout} seconds (process tree terminated)."
        finally:
            with _SUBPROCESS_LOCK:
                _ACTIVE_SUBPROCESS = None

        # Clamp output to 50KB to avoid memory/context flooding
        max_chars = 50_000
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars] + f"\n... (truncated, total {len(stdout)} characters)"
        if len(stderr) > max_chars:
            stderr = stderr[:max_chars] + f"\n... (truncated, total {len(stderr)} characters)"

        output_parts = [f"Exit Code: {proc.returncode}"]

        if stdout.strip():
            output_parts.append(f"--- STDOUT ---\n{stdout.strip()}")

        if stderr.strip():
            output_parts.append(f"--- STDERR ---\n{stderr.strip()}")

        if not stdout.strip() and not stderr.strip():
            output_parts.append("(Command produced no output)")

        return "\n\n".join(output_parts)

    except Exception as e:
        return f"Error executing command: {str(e)}"


@tool
def run_pytest(test_path: str = "") -> str:
    """
    Runs pytest on the test suite or a specific test file/directory.
    Use this tool to verify if your code and unit tests pass.
    
    Args:
        test_path: Optional relative path to a specific test file or directory (e.g. 'tests/test_calculator.py').
        
    Returns:
        Pytest output with pass/fail summary and any tracebacks.
    """
    python_exe = sys.executable
    cmd = f'"{python_exe}" -m pytest -v {test_path}'.strip()
    return run_terminal_command.invoke({"command": cmd, "timeout": 45})


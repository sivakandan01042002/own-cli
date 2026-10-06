import subprocess
import shlex
import sys
from langchain_core.tools import tool
from app.core.config import settings

# Disallow commands that could damage the system
BLOCKED_KEYWORDS = [
    "format ",
    "rmdir /s",
    "del /f /s /q c:",
    "mkfs",
    ":(){ :|:& };:",
    "shutdown",
]


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
    # Safety check against destructive disk/system damage
    command_lower = command.lower()
    for blocked in BLOCKED_KEYWORDS:
        if blocked in command_lower:
            return f"Error: Command blocked for security reasons (contains '{blocked}')."

    # Clamp timeout between 5s and 300s
    actual_timeout = max(5, min(timeout, 300))

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(settings.WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=actual_timeout,
        )

        output_parts = [f"Exit Code: {result.returncode}"]

        if result.stdout.strip():
            output_parts.append(f"--- STDOUT ---\n{result.stdout.strip()}")

        if result.stderr.strip():
            output_parts.append(f"--- STDERR ---\n{result.stderr.strip()}")

        if not result.stdout.strip() and not result.stderr.strip():
            output_parts.append("(Command produced no output)")

        return "\n\n".join(output_parts)

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {actual_timeout} seconds."
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

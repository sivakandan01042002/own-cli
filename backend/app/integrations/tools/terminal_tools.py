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
def run_terminal_command(command: str, timeout: int = 30) -> str:
    """
    Executes a simple shell command in the project workspace root and returns its output.
    Use this tool to run tests (e.g. pytest), check python script outputs, or run linters.
    Do NOT pass multi-line python scripts or bash heredocs (e.g. <<'PY'); use read_file to inspect code.
    
    Args:
        command: The shell command line string to execute (e.g., 'pytest tests/test_main.py').
        timeout: Maximum execution time in seconds (default is 30).
        
    Returns:
        A string containing exit code, stdout, and stderr.
    """
    # Safety check
    command_lower = command.lower()
    for blocked in BLOCKED_KEYWORDS:
        if blocked in command_lower:
            return f"Error: Command blocked for security reasons (contains '{blocked}')."

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(settings.WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
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
        return f"Error: Command timed out after {timeout} seconds."
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

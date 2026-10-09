import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List

from app.constants import (
    ENV_ALLOWLIST as SUBPROCESS_ENV_ALLOWLIST,
    ALLOWLISTED_TEST_RUNNERS,
)
from app.modules.coding_agent.state import TaskExecutionStatus


def resolve_project_test_runner(workspace_root: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Determines the appropriate test runner for the workspace.
    Returns (runner_command, error_reason).
    """
    root = Path(workspace_root).resolve()

    if (root / "Cargo.toml").exists():
        if shutil.which("cargo"):
            return ("cargo test", None)
        return (None, "Rust project detected (Cargo.toml), but 'cargo' binary is not found in environment.")

    if (root / "go.mod").exists():
        if shutil.which("go"):
            return ("go test ./...", None)
        return (None, "Go project detected (go.mod), but 'go' binary is not found in environment.")

    if (root / "package.json").exists():
        if shutil.which("npm"):
            return ("npm test", None)
        return (None, "JavaScript/TypeScript project detected (package.json), but 'npm' binary is not found in environment.")

    # Python project detection
    is_python = (
        (root / "pytest.ini").exists()
        or (root / "pyproject.toml").exists()
        or (root / "requirements.txt").exists()
        or (root / "setup.py").exists()
        or any(root.glob("test_*.py"))
        or any(root.glob("tests/*.py"))
    )

    if is_python:
        if shutil.which("pytest"):
            return ("pytest", None)
        # Check current python environment
        return (f'"{sys.executable}" -m pytest', None)

    return (None, "No standard project test runner detected.")


def execute_sandboxed_test_command(
    command_str: str,
    workspace_root: str,
    timeout: int = 45,
) -> Tuple[bool, str, TaskExecutionStatus]:
    """
    Executes a test command in an allowlist-isolated subprocess with process-tree cleanup.
    Returns (passed, output_text, execution_status).
    """
    root = Path(workspace_root).resolve()
    clean_cmd = command_str.strip()

    # Build safe isolated environment
    env = {k: os.environ[k] for k in SUBPROCESS_ENV_ALLOWLIST if k in os.environ}

    # Ensure virtualenv / python bin path is in PATH
    py_dir = str(Path(sys.executable).parent)
    if "PATH" in env:
        env["PATH"] = py_dir + os.pathsep + env["PATH"]
    else:
        env["PATH"] = py_dir

    try:
        proc = subprocess.Popen(
            clean_cmd,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,
            env=env,
        )

        try:
            stdout, _ = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            # Tree-kill child process
            if os.name == "nt":
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            else:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return (False, f"❌ Test execution timed out after {timeout} seconds.", "incomplete")

        output = stdout.strip() if stdout else ""

        # Check success indicators across test runners
        passed = False
        if exit_code == 0:
            passed = True
        elif "passed" in output.lower() and "failed" not in output.lower() and "error" not in output.lower():
            passed = True

        status: TaskExecutionStatus = "completed" if passed else "failed"
        return (passed, output, status)

    except Exception as e:
        return (False, f"❌ Failed to spawn test process: {str(e)}", "failed")

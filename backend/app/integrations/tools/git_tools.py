"""Git repository integration tools for safe and autonomous version control workflows."""
import subprocess
from langchain_core.tools import tool
from app.core.config import settings

# Disallow destructive git actions that could cause data loss
BLOCKED_GIT_KEYWORDS = [
    "--force",
    "-f ",
    "reset --hard",
    "clean -f",
    "clean -fd",
    "clean -xdf",
]


@tool
def run_git_command(subcommand: str, timeout: int = 30) -> str:
    """
    Executes a safe Git version control command in the workspace repository.
    
    Supported workflows:
    - 'status': Check working directory and staged/unstaged changes.
    - 'diff': View active file differences (or 'diff --cached' for staged diffs).
    - 'log -n 5 --oneline': View recent commit history.
    - 'branch': List local branches or 'branch -a' for all branches.
    - 'checkout -b <branch_name>': Create and switch to a new branch.
    - 'checkout <branch_name>': Switch to an existing branch.
    - 'add <path>': Stage modified files (or 'add .' to stage all).
    - 'commit -m "<message>"': Commit staged changes with a descriptive message.
    - 'show <commit_hash>': Inspect a specific commit.
    
    Args:
        subcommand: The git subcommand and arguments (e.g. 'status', 'diff', 'commit -m "Add feature"').
        timeout: Maximum execution time in seconds (default is 30).
        
    Returns:
        Structured output containing the git command output and return status.
    """
    subcommand_clean = subcommand.strip()
    # Strip leading 'git ' if provided by the model
    if subcommand_clean.lower().startswith("git "):
        subcommand_clean = subcommand_clean[4:].strip()

    # Safety guardrails
    subcommand_lower = subcommand_clean.lower()
    for blocked in BLOCKED_GIT_KEYWORDS:
        if blocked in subcommand_lower:
            return f"Error: Git command blocked for safety (contains '{blocked}'). Destructive git actions are disallowed."

    full_cmd = f"git {subcommand_clean}"
    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            cwd=str(settings.WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

        output_parts = [f"[git {subcommand_clean}] (Exit Code: {result.returncode})"]

        if result.stdout.strip():
            output_parts.append(result.stdout.strip())

        if result.stderr.strip():
            output_parts.append(f"Notice / Stderr:\n{result.stderr.strip()}")

        if not result.stdout.strip() and not result.stderr.strip():
            output_parts.append("(Git command completed with no output)")

        return "\n\n".join(output_parts)

    except subprocess.TimeoutExpired:
        return f"Error: Git command timed out after {timeout} seconds."
    except Exception as e:
        return f"Error executing git command: {str(e)}"

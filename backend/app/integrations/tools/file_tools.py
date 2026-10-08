import difflib
import os
from pathlib import Path
from langchain_core.tools import tool
from rich.console import Console
from rich.syntax import Syntax
from app.core.config import settings

diff_console = Console()

# Folders to ignore so we don't waste LLM tokens scanning them
IGNORE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    ".vscode",
    ".idea",
}


def _resolve_safe_path(target_path: str) -> Path:
    """
    Security check: Resolves target_path relative to WORKSPACE_ROOT
    and verifies that it stays inside the workspace directory.
    """
    root = settings.WORKSPACE_ROOT.resolve()
    resolved = (root / target_path).resolve()

    if not str(resolved).startswith(str(root)):
        raise ValueError(f"Access denied: '{target_path}' is outside the workspace root.")

    return resolved


@tool
def list_directory(dir_path: str = ".") -> str:
    """
    Lists all files and subdirectories within a given folder path in the workspace.
    Use this tool to explore the project structure and discover file names.
    
    Args:
        dir_path: Relative path to the folder to list (defaults to "." for workspace root).
        
    Returns:
        A formatted string listing all files and directories found.
    """
    try:
        target_dir = _resolve_safe_path(dir_path)

        if not target_dir.exists():
            return f"Error: Directory '{dir_path}' does not exist."

        if not target_dir.is_dir():
            return f"Error: '{dir_path}' is a file, not a directory."

        entries = []
        for root, dirs, files in os.walk(target_dir):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            rel_root = Path(root).relative_to(settings.WORKSPACE_ROOT)
            rel_str = "" if str(rel_root) == "." else f"{rel_root}/"

            for file_name in files:
                entries.append(f"📄 {rel_str}{file_name}")

        if not entries:
            return f"Directory '{dir_path}' is empty."

        return "\n".join(entries[:100])  # limit to 100 entries to prevent context overflow

    except Exception as e:
        return f"Error listing directory '{dir_path}': {str(e)}"


@tool
def read_file(file_path: str) -> str:
    """
    Reads the content of a file from the workspace and returns it with line numbers.
    Use this tool when you need to inspect existing code, configuration files, or logs.
    
    Args:
        file_path: Relative path to the file to read (e.g., 'backend/app/main.py').
        
    Returns:
        The content of the file with line numbers, or an error message if not found.
    """
    try:
        target_file = _resolve_safe_path(file_path)

        if not target_file.exists():
            return f"Error: File '{file_path}' does not exist."

        if not target_file.is_file():
            return f"Error: '{file_path}' is a directory, not a file."

        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if not lines:
            return f"File '{file_path}' is empty."

        formatted_lines = [f"{idx + 1}: {line}" for idx, line in enumerate(lines)]
        return "".join(formatted_lines)

    except Exception as e:
        return f"Error reading file '{file_path}': {str(e)}"


@tool
def write_file(file_path: str, content: str) -> str:
    """
    Creates a new file or overwrites an existing file with the provided content.
    Automatically creates any missing parent directories.
    
    Args:
        file_path: Relative path to the file to write (e.g., 'backend/app/models/user.py').
        content: The exact string content to write into the file.
        
    Returns:
        A confirmation message indicating success and number of lines written.
    """
    try:
        target_file = _resolve_safe_path(file_path)
        is_update = target_file.exists() and target_file.is_file()

        if is_update:
            try:
                old_content = target_file.read_text(encoding="utf-8", errors="replace")
                old_lines = old_content.splitlines(keepends=True)
                new_lines = content.splitlines(keepends=True)

                diff = list(difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                    lineterm="",
                ))
                if diff:
                    diff_text = "\n".join(line.rstrip("\r\n") for line in diff)
                    diff_syntax = Syntax(diff_text, "diff", theme="ansi_dark", line_numbers=False)
                    diff_console.print()
                    diff_console.print(diff_syntax)
                    diff_console.print()
            except Exception:
                pass

        # Create parent directories if they don't exist
        target_file.parent.mkdir(parents=True, exist_ok=True)

        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)

        line_count = len(content.splitlines())
        action_verb = "updated" if is_update else "wrote"
        return f"Successfully {action_verb} {line_count} lines in '{file_path}'."

    except Exception as e:
        return f"Error writing to file '{file_path}': {str(e)}"


@tool
def delete_file(file_path: str) -> str:
    """
    Deletes a file from the workspace.
    
    Args:
        file_path: Relative path to the file to delete.
        
    Returns:
        A confirmation message indicating success or failure.
    """
    try:
        target_file = _resolve_safe_path(file_path)

        if not target_file.exists():
            return f"Error: File '{file_path}' does not exist."

        if not target_file.is_file():
            return f"Error: '{file_path}' is a directory. Use directory tools to remove directories."

        target_file.unlink()
        return f"Successfully deleted file '{file_path}'."

    except Exception as e:
        return f"Error deleting file '{file_path}': {str(e)}"


@tool
def search_code(query: str, path: str = ".", file_pattern: str = "*", max_results: int = 30) -> str:
    """
    Searches for functions, classes, variables, or text patterns across project files (Grep search).
    Use this tool to locate code symbols, find import usages, or trace function definitions quickly without reading whole files.

    Args:
        query: String or regex to search for (e.g. 'def execute_workflow' or 'REDIS_CACHE').
        path: Directory or file to search within (defaults to '.' for entire workspace).
        file_pattern: File extension filter (e.g. '*.py', '*.ts', '*.json', or '*' for all).
        max_results: Maximum matching lines to return (default 30).

    Returns:
        Formatted list of matching file paths, line numbers, and matching lines.
    """
    import fnmatch
    import re

    try:
        clean_query = query.strip()
        if not clean_query:
            return "Error: Search query cannot be empty."

        target_base = _resolve_safe_path(path)
        if not target_base.exists():
            return f"Error: Path '{path}' does not exist."

        matches = []
        try:
            pattern = re.compile(clean_query, re.IGNORECASE)
        except Exception:
            pattern = re.compile(re.escape(clean_query), re.IGNORECASE)

        files_to_scan = []
        if target_base.is_file():
            files_to_scan.append(target_base)
        else:
            for root_dir, dirs, files in os.walk(target_base):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for f in files:
                    if fnmatch.fnmatch(f, file_pattern):
                        files_to_scan.append(Path(root_dir) / f)

        for file_path in files_to_scan:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                rel_path = file_path.relative_to(settings.WORKSPACE_ROOT).as_posix()
                lines = content.splitlines()

                for idx, line in enumerate(lines, 1):
                    if pattern.search(line):
                        trimmed_line = line.strip()
                        if len(trimmed_line) > 120:
                            trimmed_line = trimmed_line[:117] + "..."
                        matches.append(f"{rel_path}:{idx}  {trimmed_line}")
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break
            except Exception:
                continue

        if not matches:
            return f"No matches found for '{query}' in '{path}' (filter: {file_pattern})."

        header = f"Found {len(matches)} match(es) for '{query}':\n"
        return header + "\n".join(matches)

    except Exception as e:
        return f"Error searching code for '{query}': {str(e)}"


@tool
def patch_file(file_path: str, target_content: str, replacement_content: str) -> str:
    """
    Surgically replaces a specific block of code inside an existing file without rewriting the whole file.
    Use this tool for precise bug fixes, refactoring specific functions, or adding imports.

    Args:
        file_path: Relative path to the file to modify.
        target_content: The exact snippet of lines to find and replace.
        replacement_content: The new snippet of lines to put in place of target_content.

    Returns:
        Confirmation message with diff verification.
    """
    try:
        target_file = _resolve_safe_path(file_path)

        if not target_file.exists() or not target_file.is_file():
            return f"Error: File '{file_path}' does not exist or is not a file."

        original_text = target_file.read_text(encoding="utf-8", errors="replace")

        # Normalize line endings
        norm_orig = original_text.replace("\r\n", "\n")
        norm_target = target_content.replace("\r\n", "\n")
        norm_replacement = replacement_content.replace("\r\n", "\n")

        count = norm_orig.count(norm_target)
        if count == 0:
            return f"Error: Target snippet was not found in '{file_path}'. Make sure whitespace and indentation match exactly."
        elif count > 1:
            return f"Error: Target snippet appears {count} times in '{file_path}'. Please include more surrounding context to make the target unique."

        new_text = norm_orig.replace(norm_target, norm_replacement, 1)

        # Print rich diff
        try:
            diff = list(difflib.unified_diff(
                norm_orig.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            ))
            if diff:
                diff_text = "\n".join(line.rstrip("\r\n") for line in diff)
                diff_syntax = Syntax(diff_text, "diff", theme="ansi_dark", line_numbers=False)
                diff_console.print()
                diff_console.print(diff_syntax)
                diff_console.print()
        except Exception:
            pass

        target_file.write_text(new_text, encoding="utf-8")
        return f"Successfully patched '{file_path}'."

    except Exception as e:
        return f"Error patching file '{file_path}': {str(e)}"




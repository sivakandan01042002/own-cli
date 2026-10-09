import os
import hashlib
import subprocess
import time
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.constants import (
    DEFAULT_IGNORE_DIRS,
    SOURCE_CODE_EXTENSIONS,
    BUILD_CONFIG_FILES,
    DOC_AND_MEDIA_EXTENSIONS,
)
from app.modules.coding_agent.state import WorkspaceManifest, VerificationResult

IGNORED_DIRS = DEFAULT_IGNORE_DIRS



def _compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file efficiently with chunked reading."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _scan_workspace_impl(
    workspace_root: str,
    max_files: int = 5000,
    max_size_bytes: int = 5 * 1024 * 1024,
) -> WorkspaceManifest:
    """Internal implementation of workspace snapshot scanner."""
    root = Path(workspace_root).resolve()
    is_git_repo = False
    git_status: List[str] = []
    tracked_files: List[str] = []
    file_hashes: Dict[str, str] = {}
    skipped_files: List[str] = []

    # 1. Check Git status if available
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if res.returncode == 0:
            is_git_repo = True
            git_status = [line.strip() for line in res.stdout.splitlines() if line.strip()]

        ls_res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if ls_res.returncode == 0:
            tracked_files = [line.strip().replace("\\", "/") for line in ls_res.stdout.splitlines() if line.strip()]
    except Exception:
        pass

    # 2. File tree traversal with safety boundaries
    scanned_count = 0
    for dirpath, dirnames, filenames in os.walk(str(root), topdown=True, followlinks=False):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]

        current_dir = Path(dirpath).resolve()
        try:
            if not current_dir.is_relative_to(root):
                continue
        except (ValueError, AttributeError):
            if not str(current_dir).startswith(str(root)):
                continue

        for fname in filenames:
            if scanned_count >= max_files:
                skipped_files.append("File limit reached (5000 files)")
                break

            fpath = current_dir / fname
            # Reject symlinks resolving outside root
            if fpath.is_symlink():
                try:
                    target = fpath.resolve()
                    if not target.is_relative_to(root):
                        skipped_files.append(f"External symlink: {fname}")
                        continue
                except Exception:
                    skipped_files.append(f"Unresolvable symlink: {fname}")
                    continue

            try:
                rel_path = str(fpath.relative_to(root)).replace("\\", "/")
                stat = fpath.stat()
                if stat.st_size > max_size_bytes:
                    skipped_files.append(f"Large file (>5MB): {rel_path}")
                    continue

                file_hashes[rel_path] = _compute_sha256(fpath)
                scanned_count += 1
            except Exception:
                skipped_files.append(f"Unreadable file: {fname}")

    manifest_status = "partial" if skipped_files else "complete"

    return {
        "is_git_repo": is_git_repo,
        "manifest_status": manifest_status,
        "initial_git_status": git_status,
        "initial_tracked_files": tracked_files,
        "initial_file_hashes": file_hashes,
        "skipped_files": skipped_files,
        "manifest_error": None,
    }


def capture_workspace_manifest(workspace_root: str, timeout_sec: float = 2.0) -> WorkspaceManifest:
    """Captures workspace baseline manifest within a strict wall-clock timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_scan_workspace_impl, workspace_root)
        try:
            return future.result(timeout=timeout_sec)
        except concurrent.futures.TimeoutError:
            return {
                "is_git_repo": False,
                "manifest_status": "partial",
                "initial_git_status": [],
                "initial_tracked_files": [],
                "initial_file_hashes": {},
                "skipped_files": ["Manifest scan timed out after 2.0s"],
                "manifest_error": "Manifest scan timed out",
            }
        except Exception as e:
            return {
                "is_git_repo": False,
                "manifest_status": "failed",
                "initial_git_status": [],
                "initial_tracked_files": [],
                "initial_file_hashes": {},
                "skipped_files": [],
                "manifest_error": str(e),
            }


def verify_code_changes(
    workspace_root: str,
    manifest: Optional[WorkspaceManifest],
    tool_modified_paths: List[str],
) -> VerificationResult:
    """
    Compares the live workspace against the baseline manifest and tool write operations.
    Returns structured VerificationResult.
    """
    if not manifest or manifest.get("manifest_status") == "failed":
        return {
            "verified": False,
            "source_changed": bool(tool_modified_paths),
            "config_changed": False,
            "changed_files": list(tool_modified_paths),
            "unverified_files": list(tool_modified_paths),
            "error": "Initial workspace manifest missing or failed; cannot verify exact diff.",
        }

    root = Path(workspace_root).resolve()
    initial_hashes = manifest.get("initial_file_hashes", {})
    changed_files: List[str] = []
    unverified_files: List[str] = list(manifest.get("skipped_files", []))

    # Check all files reported by tools or existing in current directory
    checked_paths: Set[str] = set()

    for p_str in tool_modified_paths:
        norm_p = p_str.replace("\\", "/")
        p = Path(norm_p)
        if p.is_absolute():
            try:
                rel = str(p.relative_to(root)).replace("\\", "/")
            except Exception:
                rel = norm_p
        else:
            rel = norm_p
        checked_paths.add(rel)

    # Check live filesystem for hashes of tool-reported paths & initial files
    for rel_path in checked_paths.union(initial_hashes.keys()):
        fpath = root / rel_path
        if not fpath.exists():
            if rel_path in initial_hashes:
                # File was deleted
                changed_files.append(rel_path)
            continue

        try:
            current_hash = _compute_sha256(fpath)
            init_hash = initial_hashes.get(rel_path)
            if init_hash is None or current_hash != init_hash:
                changed_files.append(rel_path)
        except Exception:
            unverified_files.append(rel_path)

    # Also check git status diff if git repo
    if manifest.get("is_git_repo"):
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0:
                current_git_status = [l.strip() for l in res.stdout.splitlines() if l.strip()]
                initial_status_set = set(manifest.get("initial_git_status", []))
                for line in current_git_status:
                    if line not in initial_status_set:
                        parts = line.split(maxsplit=1)
                        if len(parts) == 2:
                            rel_git_path = parts[1].replace("\\", "/")
                            if rel_git_path not in changed_files:
                                changed_files.append(rel_git_path)
        except Exception:
            pass

    # Classify changed files
    source_changed = any(
        any(cf.endswith(ext) for ext in SOURCE_CODE_EXTENSIONS)
        for cf in changed_files
    )

    config_changed = any(
        any(cf == bcf or cf.endswith(f"/{bcf}") for bcf in BUILD_CONFIG_FILES)
        for cf in changed_files
    )

    is_verified = (manifest.get("manifest_status") == "complete")

    return {
        "verified": is_verified,
        "source_changed": source_changed,
        "config_changed": config_changed,
        "changed_files": changed_files,
        "unverified_files": unverified_files,
        "error": manifest.get("manifest_error"),
    }

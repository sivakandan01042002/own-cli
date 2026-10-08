"""Permanent Home-Directory Storage and Workspace Scoping Engine for QueryNest (~/.querynest/)."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from app.constants.storage import (
    QUERYNEST_HOME_DIRNAME,
    AUTH_FILENAME,
    CONFIG_FILENAME,
    TRUSTED_WORKSPACES_FILENAME,
    WORKSPACES_DIRNAME,
)

# Base Home Directory (~/.querynest)
QUERYNEST_HOME = Path.home() / QUERYNEST_HOME_DIRNAME
TRUSTED_WORKSPACES_FILE = QUERYNEST_HOME / TRUSTED_WORKSPACES_FILENAME
GLOBAL_CONFIG_FILE = QUERYNEST_HOME / CONFIG_FILENAME
WORKSPACES_DIR = QUERYNEST_HOME / WORKSPACES_DIRNAME


def ensure_home_dir() -> Path:
    """Ensures ~/.querynest and its workspaces subdirectories exist."""
    QUERYNEST_HOME.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    return QUERYNEST_HOME


def get_canonical_workspace_path(workspace_root: Optional[Union[str, Path]] = None) -> str:
    """Returns normalized canonical absolute path string for a workspace root."""
    target = workspace_root or os.getcwd()
    return str(Path(target).resolve()).replace("\\", "/")


def get_workspace_hash(workspace_root: Optional[Union[str, Path]] = None) -> str:
    """Computes a deterministic 12-character SHA-256 hash for a workspace path."""
    canonical_str = get_canonical_workspace_path(workspace_root).lower()
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()[:12]


def get_workspace_storage_dir(workspace_root: Optional[Union[str, Path]] = None) -> Path:
    """Returns the dedicated permanent storage directory for a specific workspace."""
    ensure_home_dir()
    p = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
    ws_hash = get_workspace_hash(p)
    ws_dir = WORKSPACES_DIR / ws_hash
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "sessions").mkdir(parents=True, exist_ok=True)
    
    # Store workspace meta info if not present
    meta_file = ws_dir / "workspace.json"
    if not meta_file.exists():
        meta_data = {
            "workspace_path": get_canonical_workspace_path(p),
            "workspace_hash": ws_hash,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        try:
            meta_file.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
        except Exception:
            pass
            
    return ws_dir


# ==========================================
# Workspace Trust Management
# ==========================================

def get_trusted_workspaces() -> List[str]:
    """Returns the list of canonical paths for trusted workspaces."""
    ensure_home_dir()
    if not TRUSTED_WORKSPACES_FILE.exists():
        return []
    try:
        data = json.loads(TRUSTED_WORKSPACES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def is_workspace_trusted(workspace_root: Optional[Union[str, Path]] = None) -> bool:
    """Checks if a workspace folder has been explicitly trusted by the user."""
    canonical = get_canonical_workspace_path(workspace_root).lower()
    trusted = [str(Path(p).resolve()).replace("\\", "/").lower() for p in get_trusted_workspaces()]
    return canonical in trusted


def trust_workspace(workspace_root: Optional[Union[str, Path]] = None) -> None:
    """Adds a workspace folder to the trusted list."""
    ensure_home_dir()
    canonical = get_canonical_workspace_path(workspace_root)
    trusted = get_trusted_workspaces()
    if canonical not in trusted:
        trusted.append(canonical)
        try:
            TRUSTED_WORKSPACES_FILE.write_text(json.dumps(trusted, indent=2), encoding="utf-8")
        except Exception:
            pass


# ==========================================
# Permanent Zero-Loss Session Management
# ==========================================

def save_permanent_session(workspace_root: Optional[Union[str, Path]], session_id: str, thread_data: Dict[str, Any]) -> bool:
    """
    Permanently saves a session thread JSON to ~/.querynest/workspaces/<hash>/sessions/<id>.json.
    Survives PC restarts, reboots, and Redis flushes.
    """
    try:
        ws_dir = get_workspace_storage_dir(workspace_root)
        session_file = ws_dir / "sessions" / f"{session_id}.json"
        
        # Ensure timestamp and workspace are recorded
        payload = dict(thread_data)
        payload["session_id"] = session_id
        payload["workspace_path"] = get_canonical_workspace_path(workspace_root)
        payload["workspace_hash"] = get_workspace_hash(workspace_root)
        if "updated_at" not in payload:
            payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
            
        session_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def get_permanent_session(workspace_root: Optional[Union[str, Path]], session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single permanent session from disk."""
    try:
        ws_dir = get_workspace_storage_dir(workspace_root)
        session_file = ws_dir / "sessions" / f"{session_id}.json"
        if session_file.exists():
            return json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def list_permanent_sessions(workspace_root: Optional[Union[str, Path]] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Lists all permanent sessions for the specified workspace, sorted by most recent."""
    results = []
    try:
        ws_dir = get_workspace_storage_dir(workspace_root)
        sessions_dir = ws_dir / "sessions"
        if not sessions_dir.exists():
            return []
            
        files = sorted(
            sessions_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(data)
            except Exception:
                continue
    except Exception:
        pass
    return results


def delete_permanent_session(workspace_root: Optional[Union[str, Path]], session_id: str) -> bool:
    """Deletes a permanent session file from the workspace directory."""
    try:
        ws_dir = get_workspace_storage_dir(workspace_root)
        session_file = ws_dir / "sessions" / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            return True
    except Exception:
        pass
    return False


def clear_permanent_sessions(workspace_root: Optional[Union[str, Path]] = None) -> bool:
    """Clears all permanent sessions for the specified workspace."""
    try:
        ws_dir = get_workspace_storage_dir(workspace_root)
        sessions_dir = ws_dir / "sessions"
        if sessions_dir.exists():
            for f in sessions_dir.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
            return True
    except Exception:
        pass
    return False


# ==========================================
# Atomic Workspace Concurrency Locking
# ==========================================

class WorkspaceLock:
    """
    Atomic OS-level file lock for workspace concurrency control.
    Uses atomic os.open(O_CREAT | O_EXCL) to prevent multi-process race conditions.
    """
    def __init__(self, workspace_root: Optional[Union[str, Path]] = None, stale_timeout: int = 600):
        self.ws_dir = get_workspace_storage_dir(workspace_root)
        self.lock_file = self.ws_dir / ".workspace.lock"
        self.stale_timeout = stale_timeout
        self.held_session_id: Optional[str] = None

    def acquire(self, session_id: str) -> bool:
        """
        Attempts to atomically acquire the workspace lock.
        Returns True if acquired, False otherwise.
        """
        import time

        payload = {
            "session_id": session_id,
            "pid": os.getpid(),
            "timestamp": time.time(),
        }
        raw_data = json.dumps(payload).encode("utf-8")

        for attempt in range(2):
            try:
                # Atomic open: O_CREAT | O_EXCL fails if file exists
                flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
                fd = os.open(str(self.lock_file), flags)
                with os.fdopen(fd, "wb") as f:
                    f.write(raw_data)
                self.held_session_id = session_id
                return True
            except (FileExistsError, OSError):
                # Lock exists - check if it is stale or held by same session
                try:
                    content = json.loads(self.lock_file.read_text(encoding="utf-8"))
                    # If same session already holds lock
                    if content.get("session_id") == session_id:
                        self.held_session_id = session_id
                        return True

                    # Check if stale by timestamp or dead PID
                    lock_time = content.get("timestamp", 0)
                    lock_pid = content.get("pid")
                    is_stale = False

                    if time.time() - lock_time > self.stale_timeout:
                        is_stale = True
                    elif lock_pid:
                        try:
                            # Check if process exists
                            os.kill(lock_pid, 0)
                        except (OSError, ProcessLookupError, PermissionError):
                            # Process is dead or inaccessible
                            is_stale = True

                    if is_stale and attempt == 0:
                        try:
                            self.lock_file.unlink(missing_ok=True)
                            continue  # Retry atomic acquisition
                        except Exception:
                            pass
                except Exception:
                    pass

                return False

        return False

    def release(self, session_id: Optional[str] = None):
        """Releases the lock if held by current session."""
        target_session = session_id or self.held_session_id
        try:
            if self.lock_file.exists():
                if target_session:
                    try:
                        content = json.loads(self.lock_file.read_text(encoding="utf-8"))
                        if content.get("session_id") != target_session:
                            return  # Held by another session
                    except Exception:
                        pass
                self.lock_file.unlink(missing_ok=True)
                self.held_session_id = None
        except Exception:
            pass


# ==========================================
# Structured Audit Logging (audit.jsonl)
# ==========================================

def log_audit_event(event: Dict[str, Any], workspace_root: Optional[Union[str, Path]] = None) -> bool:
    """
    Appends a structured audit event to ~/.querynest/workspaces/<hash>/logs/audit.jsonl.
    """
    try:
        ws_dir = get_workspace_storage_dir(workspace_root)
        logs_dir = ws_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        audit_file = logs_dir / "audit.jsonl"

        record = dict(event)
        if "timestamp" not in record:
            record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        if "pid" not in record:
            record["pid"] = os.getpid()

        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return True
    except Exception:
        return False


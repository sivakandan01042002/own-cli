"""Centralized Redis connection, caching, and session manager for QueryNest."""

from typing import Optional, Dict, Any, List
import json
import logging
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger("querynest.redis")

_redis_client = None
_in_memory_sessions: List[Dict[str, Any]] = []
_in_memory_cache: Dict[str, str] = []


def _normalize_redis_url(raw_url: str) -> str:
    """Normalizes raw Redis URLs (handling Upstash CLI strings and TLS rediss:// protocol)."""
    if not raw_url:
        return "redis://localhost:6379/0"
    
    clean = raw_url.replace("redis-cli", "").replace("--tls", "").replace("-u", "").strip()
    if clean.startswith("redis://") and "upstash.io" in clean:
        clean = clean.replace("redis://", "rediss://", 1)
    return clean


def get_redis_client():
    """
    Returns a connected Redis client instance.
    Gracefully returns None if Redis or redis-py is unavailable, allowing zero-crash fallbacks.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    if not getattr(settings, "REDIS_CACHE_ENABLED", True):
        return None

    try:
        import redis
        clean_url = _normalize_redis_url(settings.REDIS_URL)
        client = redis.from_url(
            clean_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as e:
        logger.debug(f"Redis not reachable at {settings.REDIS_URL}: {e}")
        return None


# ---------------------------------------------------------
# Response & Tool Caching Helpers
# ---------------------------------------------------------
def get_cached_response(cache_key: str) -> Optional[str]:
    """Retrieves cached text from Redis if available, with in-memory fallback."""
    client = get_redis_client()
    if client is not None:
        try:
            return client.get(f"querynest:cache:{cache_key}")
        except Exception:
            pass
    return _in_memory_cache.get(cache_key) if isinstance(_in_memory_cache, dict) else None


def set_cached_response(cache_key: str, value: str, ttl: Optional[int] = None) -> bool:
    """Caches text in Redis with a TTL, with in-memory fallback."""
    global _in_memory_cache
    if not isinstance(_in_memory_cache, dict):
        _in_memory_cache = {}

    client = get_redis_client()
    if client is not None:
        try:
            expire_seconds = ttl or getattr(settings, "REDIS_CACHE_TTL_SECONDS", 3600)
            client.setex(f"querynest:cache:{cache_key}", expire_seconds, value)
            return True
        except Exception:
            pass
    
    _in_memory_cache[cache_key] = value
    return True


# ---------------------------------------------------------
# Threaded Multi-Turn Session Management
# ---------------------------------------------------------
SESSIONS_CACHE_DIR = settings.WORKSPACE_ROOT / ".querynest_cache" / "sessions"
_in_memory_threads: Dict[str, Dict[str, Any]] = {}
_in_memory_thread_order: List[str] = []


def serialize_message(msg: Any) -> Dict[str, Any]:
    """Converts LangChain message object to serializable JSON dict."""
    if isinstance(msg, dict):
        return msg
    msg_type = getattr(msg, "type", "human")
    content = getattr(msg, "content", "")
    data: Dict[str, Any] = {
        "type": msg_type,
        "content": content,
    }
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        data["tool_calls"] = msg.tool_calls
    if hasattr(msg, "name") and msg.name:
        data["name"] = msg.name
    if hasattr(msg, "tool_call_id") and msg.tool_call_id:
        data["tool_call_id"] = msg.tool_call_id
    return data


def deserialize_message(data: Dict[str, Any]) -> Any:
    """Converts serialized JSON dict back into LangChain message object."""
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
    msg_type = data.get("type", "human")
    content = data.get("content", "")
    if msg_type == "human":
        return HumanMessage(content=content)
    elif msg_type == "ai":
        return AIMessage(content=content, tool_calls=data.get("tool_calls", []))
    elif msg_type == "system":
        return SystemMessage(content=content)
    elif msg_type == "tool":
        return ToolMessage(
            content=content,
            name=data.get("name", "tool"),
            tool_call_id=data.get("tool_call_id", ""),
        )
    return HumanMessage(content=content)


def save_session_thread(
    session_id: str,
    title: str,
    messages: List[Any],
    meta: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Saves or updates a complete multi-turn session thread in Redis and local cache.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    serialized_messages = [serialize_message(m) for m in messages]
    
    # Calculate turn count (number of human messages)
    turn_count = sum(1 for m in serialized_messages if m.get("type") == "human")

    thread_data: Dict[str, Any] = {
        "session_id": session_id,
        "title": title or "Untitled Session",
        "turn_count": turn_count,
        "updated_at": now_str,
        "messages": serialized_messages,
    }
    if meta:
        thread_data.update(meta)

    # 1. Local disk cache fallback
    try:
        SESSIONS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        file_path = SESSIONS_CACHE_DIR / f"{session_id}.json"
        file_path.write_text(json.dumps(thread_data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"Failed to save session thread to disk: {e}")

    # 2. In-memory fallback
    _in_memory_threads[session_id] = thread_data
    if session_id in _in_memory_thread_order:
        _in_memory_thread_order.remove(session_id)
    _in_memory_thread_order.insert(0, session_id)

    # 3. Redis persistence
    client = get_redis_client()
    if client is not None:
        try:
            client.set(f"querynest:thread:{session_id}", json.dumps(thread_data))
            client.lrem("querynest:thread_index", 0, session_id)
            client.lpush("querynest:thread_index", session_id)
            client.ltrim("querynest:thread_index", 0, 49)
            return True
        except Exception as e:
            logger.debug(f"Failed to save session thread to Redis: {e}")

    return True


def get_session_thread(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves full session thread by session_id from Redis or local cache.
    """
    client = get_redis_client()
    if client is not None:
        try:
            raw = client.get(f"querynest:thread:{session_id}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.debug(f"Failed to get session thread from Redis: {e}")

    # Fallback to local cache
    file_path = SESSIONS_CACHE_DIR / f"{session_id}.json"
    if file_path.exists():
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return _in_memory_threads.get(session_id)


def list_session_threads(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Lists distinct session threads ordered from most recent to oldest.
    """
    results: List[Dict[str, Any]] = []
    seen_ids = set()

    client = get_redis_client()
    if client is not None:
        try:
            thread_ids = client.lrange("querynest:thread_index", 0, limit - 1)
            for tid in thread_ids:
                if tid and tid not in seen_ids:
                    t_data = get_session_thread(tid)
                    if t_data:
                        results.append(t_data)
                        seen_ids.add(tid)
        except Exception as e:
            logger.debug(f"Failed to list session threads from Redis: {e}")

    # Fallback: scan local cache directory
    if len(results) < limit and SESSIONS_CACHE_DIR.exists():
        try:
            local_files = sorted(
                SESSIONS_CACHE_DIR.glob("*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for lf in local_files:
                tid = lf.stem
                if tid not in seen_ids:
                    try:
                        t_data = json.loads(lf.read_text(encoding="utf-8"))
                        results.append(t_data)
                        seen_ids.add(tid)
                    except Exception:
                        pass
                if len(results) >= limit:
                    break
        except Exception:
            pass

    # Memory fallback
    if not results:
        for tid in _in_memory_thread_order[:limit]:
            if tid in _in_memory_threads:
                results.append(_in_memory_threads[tid])

    return results[:limit]


def delete_session_thread(session_id: str) -> bool:
    """Deletes a session thread from Redis and local cache."""
    client = get_redis_client()
    if client is not None:
        try:
            client.delete(f"querynest:thread:{session_id}")
            client.lrem("querynest:thread_index", 0, session_id)
        except Exception:
            pass

    file_path = SESSIONS_CACHE_DIR / f"{session_id}.json"
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            pass

    _in_memory_threads.pop(session_id, None)
    if session_id in _in_memory_thread_order:
        _in_memory_thread_order.remove(session_id)
    return True


def clear_session_records() -> bool:
    """Clears all session records and threads from Redis, local disk, and memory."""
    global _in_memory_sessions, _in_memory_threads, _in_memory_thread_order
    _in_memory_sessions = []
    _in_memory_threads = {}
    _in_memory_thread_order = []

    client = get_redis_client()
    if client is not None:
        try:
            client.delete("querynest:sessions")
            client.delete("querynest:thread_index")
            keys = client.keys("querynest:thread:*")
            if keys:
                client.delete(*keys)
        except Exception:
            pass

    if SESSIONS_CACHE_DIR.exists():
        try:
            for f in SESSIONS_CACHE_DIR.glob("*.json"):
                f.unlink()
        except Exception:
            pass

    return True


# Backward compatibility aliases
save_session_record = save_session_thread
get_session_records = list_session_threads

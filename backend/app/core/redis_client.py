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
# Session History Storage & Retrieval
# ---------------------------------------------------------
def save_session_record(record: Dict[str, Any]) -> bool:
    """
    Appends a completed task session record into Redis list 'querynest:sessions'.
    Falls back to in-memory list if Redis is offline.
    """
    if "created_at" not in record:
        record["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    client = get_redis_client()
    if client is not None:
        try:
            client.lpush("querynest:sessions", json.dumps(record))
            # Keep the latest 50 sessions
            client.ltrim("querynest:sessions", 0, 49)
            return True
        except Exception as e:
            logger.debug(f"Failed to push session to Redis: {e}")

    _in_memory_sessions.insert(0, record)
    if len(_in_memory_sessions) > 50:
        _in_memory_sessions.pop()
    return True


def get_session_records(limit: int = 15) -> List[Dict[str, Any]]:
    """
    Retrieves recent task session records from Redis.
    """
    client = get_redis_client()
    if client is not None:
        try:
            raw_items = client.lrange("querynest:sessions", 0, limit - 1)
            return [json.loads(item) for item in raw_items if item]
        except Exception as e:
            logger.debug(f"Failed to fetch sessions from Redis: {e}")

    return _in_memory_sessions[:limit]


def clear_session_records() -> bool:
    """Clears all session records from Redis and memory."""
    global _in_memory_sessions
    _in_memory_sessions = []
    client = get_redis_client()
    if client is not None:
        try:
            client.delete("querynest:sessions")
            return True
        except Exception:
            pass
    return True

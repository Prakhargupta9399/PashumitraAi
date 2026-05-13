# app/services/cache.py
# NEW Phase 2: Redis-backed cache for AI responses, rate limits, session state.
# Falls back gracefully to in-memory dict if Redis is not configured.

import json, logging, time
from typing import Any, Optional
from app.config import settings

logger = logging.getLogger("pashumitra.cache")


class PashuCache:
    """
    Two-tier cache:
      - Tier 1: In-memory dict (always available, process-local)
      - Tier 2: Redis (optional, shared across workers)
    TTL is seconds. Default 3600 = 1 hour.
    """

    def __init__(self):
        self._mem: dict = {}          # {key: (value, expires_at)}
        self._redis = None
        self._redis_ok = False

    def connect(self):
        """Lazy-connect to Redis. Call once at startup."""
        if not settings.REDIS_URL:
            logger.info("REDIS_URL not set — using in-memory cache only")
            return
        try:
            import redis  # type: ignore
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True,
                                         socket_timeout=2)
            self._redis.ping()
            self._redis_ok = True
            logger.info("Redis cache connected: %s", settings.REDIS_URL[:30])
        except Exception as e:
            logger.warning("Redis unavailable (%s) — using in-memory fallback", e)
            self._redis_ok = False

    # ── CORE OPS ──────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        # 1. Memory
        if key in self._mem:
            val, exp = self._mem[key]
            if time.time() < exp:
                return val
            del self._mem[key]
        # 2. Redis

        if self._redis_ok and self._redis is not None:
            try:
                raw = self._redis.get(key)
                if raw:
                    val = json.loads(raw)
                    self._mem[key] = (val, time.time() + 60)  # warm local cache
                    return val
            except Exception as e:
                logger.warning("Redis GET error: %s", e)
        return None

    def set(self, key: str, value: Any, ttl: int = 3600):
        self._mem[key] = (value, time.time() + ttl)
        if self._redis_ok and self._redis is not None:
            try:
                self._redis.setex(key, ttl, json.dumps(value, default=str))
            except Exception as e:
                logger.warning("Redis SET error: %s", e)

    def delete(self, key: str):
        self._mem.pop(key, None)
        if self._redis_ok and self._redis is not None:
            try:
                self._redis.delete(key)
            except Exception:
                pass

    def flush_prefix(self, prefix: str):
        """Delete all keys starting with prefix."""
        keys_to_del = [k for k in self._mem if k.startswith(prefix)]
        for k in keys_to_del:
            del self._mem[k]
        if self._redis_ok and self._redis is not None:
            try:
                for key in self._redis.scan_iter(f"{prefix}*"):
                    self._redis.delete(key)
            except Exception:
                pass

    # ── HELPER KEYS ───────────────────────────────────────────────────────────

    @staticmethod
    def ai_key(text: str) -> str:
        """Cache key for AI diagnosis results."""
        import hashlib
        return "ai:" + hashlib.md5(text.lower().strip().encode()).hexdigest()

    @staticmethod
    def session_key(phone: str) -> str:
        """Cache key for farmer conversation session."""
        return f"session:{phone}"

    @staticmethod
    def milk_key(cattle_id: str, month: str) -> str:
        """Cache key for monthly milk summary."""
        return f"milk:{cattle_id}:{month}"


cache = PashuCache()

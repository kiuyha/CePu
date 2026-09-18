"""Client Redis async, dependency FastAPI (mudah di-override saat testing)."""
import redis.asyncio as redis

from .config import get_settings

_settings = get_settings()
_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(_settings.redis_url, decode_responses=True)
    return _redis_client

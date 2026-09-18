"""Rate limiter berbasis Redis (fixed window counter)."""
from fastapi import Depends, Request
import redis.asyncio as redis

from .config import get_settings
from .errors import RateLimitExceededError
from .redis_client import get_redis_client

_settings = get_settings()


class RedisRateLimiter:
    def __init__(self, scope: str, max_requests: int, window_seconds: int):
        self.scope = scope
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def check(self, redis_client: redis.Redis, identity: str) -> None:
        key = f"ratelimit:{self.scope}:{identity}"

        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, self.window_seconds)

        if current > self.max_requests:
            raise RateLimitExceededError(
                f"Terlalu banyak permintaan. Batas: {self.max_requests} "
                f"per {self.window_seconds} detik."
            )


def client_ip_key(request: Request) -> str:
    if request.client:
        return request.client.host
    return "unknown"


detect_limiter = RedisRateLimiter(
    scope="detect",
    max_requests=_settings.rate_limit_detect_per_minute,
    window_seconds=60,
)

report_limiter = RedisRateLimiter(
    scope="report",
    max_requests=_settings.rate_limit_report_per_hour,
    window_seconds=3600,
)


async def enforce_detect_rate_limit(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis_client),
) -> None:
    await detect_limiter.check(redis_client, client_ip_key(request))


async def enforce_report_rate_limit(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis_client),
) -> None:
    await report_limiter.check(redis_client, client_ip_key(request))

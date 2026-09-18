"""Cache verifikasi multi-sumber berbasis Redis (kind:value_hash, TTL 14 hari)."""
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

import redis.asyncio as redis

Kind = Literal["phone", "email", "company"]

TTL_SECONDS = 14 * 24 * 3600


@dataclass
class VerificationResult:
    value_masked: str
    verdict_score: float
    verdict_binary: Optional[bool]
    source: str
    fetched_at: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "VerificationResult":
        return cls(**json.loads(raw))


def hash_value(value: str) -> str:
    normalized = value.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def build_cache_key(kind: Kind, value: str, source: Optional[str] = None) -> str:
    """`source` opsional untuk membedakan beberapa sumber independen dengan `kind` sama."""
    base = f"{kind}:{hash_value(value)}"
    return f"{base}:{source}" if source else base


def mask_value(kind: Kind, value: str) -> str:
    value = value.strip()
    bullet = "\u2022"
    if kind == "phone":
        if len(value) <= 7:
            return value
        return f"{value[:4]}{bullet * 4}{value[-3:]}"
    if kind == "email":
        if "@" not in value:
            return value
        local, _, domain = value.partition("@")
        if len(local) <= 2:
            return f"{local[0]}{bullet}@{domain}"
        return f"{local[0]}{bullet * (len(local) - 2)}{local[-1]}@{domain}"
    return value


class VerificationCache:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def get(self, kind: Kind, value: str, source: Optional[str] = None) -> Optional[VerificationResult]:
        raw = await self.redis.get(build_cache_key(kind, value, source))
        if raw is None:
            return None
        return VerificationResult.from_json(raw)

    async def set(
        self,
        kind: Kind,
        value: str,
        *,
        verdict_score: float,
        verdict_binary: Optional[bool],
        source: str,
        cache_source_key: Optional[str] = None,
    ) -> VerificationResult:
        result = VerificationResult(
            value_masked=mask_value(kind, value),
            verdict_score=verdict_score,
            verdict_binary=verdict_binary,
            source=source,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        key = build_cache_key(kind, value, cache_source_key)
        await self.redis.set(key, result.to_json(), ex=TTL_SECONDS)
        return result

    async def get_or_neutral(
        self, kind: Kind, value: str, source: Optional[str] = None
    ) -> tuple[VerificationResult, bool]:
        cached = await self.get(kind, value, source)
        if cached is not None:
            return cached, False

        neutral = VerificationResult(
            value_masked=mask_value(kind, value),
            verdict_score=0.5,
            verdict_binary=None,
            source="neutral_fallback",
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        return neutral, True

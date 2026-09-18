"""
Test untuk VerificationCache (fase Redis Caching Layer).
"""
from api.core.cache import (
    VerificationCache,
    build_cache_key,
    hash_value,
    mask_value,
)


# ---------- hash_value & build_cache_key ----------

def test_hash_value_is_deterministic():
    assert hash_value("081234567890") == hash_value("081234567890")


def test_hash_value_differs_for_different_input():
    assert hash_value("081234567890") != hash_value("081234567891")


def test_hash_value_is_case_and_whitespace_insensitive():
    """Nomor/email yang sama walau beda spasi/kapitalisasi harus dianggap sama."""
    assert hash_value("  Test@Email.com  ") == hash_value("test@email.com")


def test_build_cache_key_format():
    key = build_cache_key("phone", "081234567890")
    assert key.startswith("phone:")
    assert key == f"phone:{hash_value('081234567890')}"


# ---------- mask_value ----------

def test_mask_value_phone_keeps_prefix_and_suffix():
    masked = mask_value("phone", "081234567890")
    assert masked.startswith("0812")
    assert masked.endswith("890")
    assert "\u2022" in masked
    # Nomor asli tidak boleh muncul utuh di hasil masking
    assert "081234567890" not in masked


def test_mask_value_phone_too_short_returned_as_is():
    assert mask_value("phone", "123") == "123"


def test_mask_value_email_masks_local_part():
    masked = mask_value("email", "halilatunnisa@example.com")
    assert masked.endswith("@example.com")
    assert "halilatunnisa" not in masked


def test_mask_value_company_not_masked():
    """Nama perusahaan itu sendiri data publik, tidak perlu dimasking."""
    assert mask_value("company", "PT Contoh Sejahtera") == "PT Contoh Sejahtera"


# ---------- VerificationCache: get/set ----------

async def test_cache_set_then_get_returns_same_data(fake_redis):
    cache = VerificationCache(fake_redis)
    await cache.set(
        "phone",
        "081234567890",
        verdict_score=0.9,
        verdict_binary=True,
        source="aduannomor.id",
    )

    result = await cache.get("phone", "081234567890")

    assert result is not None
    assert result.verdict_score == 0.9
    assert result.verdict_binary is True
    assert result.source == "aduannomor.id"
    assert "081234567890" not in result.value_masked


async def test_cache_get_miss_returns_none(fake_redis):
    cache = VerificationCache(fake_redis)
    result = await cache.get("email", "belumpernahdicek@example.com")
    assert result is None


async def test_cache_ttl_is_set_to_14_days(fake_redis):
    cache = VerificationCache(fake_redis)
    await cache.set(
        "company",
        "PT Contoh Sejahtera",
        verdict_score=0.1,
        verdict_binary=False,
        source="ahu_online",
    )

    key = build_cache_key("company", "PT Contoh Sejahtera")
    ttl = await fake_redis.ttl(key)

    # TTL harus ada (bukan -1 = tanpa expiry) dan mendekati 14 hari
    fourteen_days = 14 * 24 * 3600
    assert 0 < ttl <= fourteen_days


# ---------- get_or_neutral (dipakai fase Validator nanti) ----------

async def test_get_or_neutral_returns_cached_value_when_hit(fake_redis):
    cache = VerificationCache(fake_redis)
    await cache.set(
        "phone", "081200000000", verdict_score=0.8, verdict_binary=True, source="kredibel.com"
    )

    result, is_degraded = await cache.get_or_neutral("phone", "081200000000")

    assert is_degraded is False
    assert result.verdict_score == 0.8
    assert result.source == "kredibel.com"


async def test_get_or_neutral_returns_neutral_when_miss(fake_redis):
    cache = VerificationCache(fake_redis)

    result, is_degraded = await cache.get_or_neutral("email", "belumadadi@cache.com")

    assert is_degraded is True
    assert result.verdict_score == 0.5
    assert result.verdict_binary is None
    assert result.source == "neutral_fallback"

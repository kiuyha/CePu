"""Wrapper timeout+retry generik untuk semua validator sumber eksternal."""
import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

# Timeout default untuk validator eksternal yang menggunakan HTTP scraper.
# Nilai 1.0 detik terlalu kecil; scraper companyhouse (~5s), aduannomor (~5s),
# dan kredibel (~6s) membutuhkan waktu lebih lama. Kita set 12s sebagai batas
# aman yang melingkupi semua konfigurasi timeout scraper + overhead jaringan.
DEFAULT_TIMEOUT_SECONDS = 12.0
RETRY_DELAY_SECONDS = 0.5


class ValidatorUnavailable(Exception):
    def __init__(self, source: str, original_error: Exception | None = None):
        self.source = source
        self.original_error = original_error
        super().__init__(f"Validator '{source}' gagal setelah retry: {original_error}")


async def call_with_retry(
    coro_fn: Callable[[], Awaitable[T]],
    *,
    source: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retry_delay: float = RETRY_DELAY_SECONDS,
) -> T:
    for attempt in range(2):
        try:
            return await asyncio.wait_for(coro_fn(), timeout=timeout)
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            if attempt == 1:
                raise ValidatorUnavailable(source, exc) from exc
            await asyncio.sleep(retry_delay)

    raise ValidatorUnavailable(source)

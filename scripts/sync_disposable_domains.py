"""
Script untuk melakukan sinkronisasi daftar disposable email domains dari repositori GitHub:
https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf
ke tabel database `disposable_domains`.

Jalankan secara manual atau via cron job (misal mingguan):
    python scripts/sync_disposable_domains.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db.base import async_session_factory, init_models  # noqa: E402
from api.services.disposable_sync import sync_disposable_domains_from_github  # noqa: E402


async def main():
    print("Memulai sinkronisasi disposable email domains dari GitHub...")
    await init_models()
    async with async_session_factory() as session:
        added = await sync_disposable_domains_from_github(session)
        print(f"Sinkronisasi selesai. Berhasil menambahkan/memperbarui {added} domain baru ke tabel disposable_domains.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Seed tabel company_registry dari REAL_Job_Offer_Clean.xlsx.

Cara pakai (dari folder cepu):
    python scripts/seed_company_registry.py path/ke/REAL_Job_Offer_Clean.xlsx

Aman dijalankan berkali-kali (upsert). HANYA pakai data REAL, bukan FAKE
-- nama perusahaan di dataset FAKE adalah korban pencatutan nama, bukan
pelaku, jadi tidak boleh dijadikan daftar is_flagged_scam.
"""
import asyncio
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.db.base import async_session_factory, init_models  # noqa: E402
from api.db.repository import CompanyRegistryRepository  # noqa: E402


async def seed_from_excel(xlsx_path: str) -> None:
    df = pd.read_excel(xlsx_path)

    if "nama_perusahaan_terdeteksi" not in df.columns:
        raise ValueError(
            f"Kolom 'nama_perusahaan_terdeteksi' tidak ditemukan. "
            f"Kolom yang ada: {list(df.columns)}"
        )

    company_names = (
        df["nama_perusahaan_terdeteksi"]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[lambda s: s.str.len() > 2]
        .unique()
    )

    print(f"Ditemukan {len(company_names)} nama perusahaan unik di {xlsx_path}")

    await init_models()

    inserted = 0
    async with async_session_factory() as session:
        repo = CompanyRegistryRepository(session)
        for name in company_names:
            await repo.upsert(
                legal_name=name,
                registered=True,
                is_flagged_scam=False,
                source="scraped_real_postings",
            )
            inserted += 1
            if inserted % 200 == 0:
                print(f"  ... {inserted}/{len(company_names)} diproses")

    print(f"Selesai. {inserted} entri di-upsert ke company_registry.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Pakai: python scripts/seed_company_registry.py <path_ke_REAL_Job_Offer_Clean.xlsx>")
        sys.exit(1)

    asyncio.run(seed_from_excel(sys.argv[1]))

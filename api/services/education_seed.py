"""Modul seeding otomatis untuk data artikel edukasi penipuan lowongan kerja."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.repository import EducationArticleRepository

logger = logging.getLogger(__name__)

INITIAL_EDUCATION_ARTICLES = [
    {
        "slug": "pengenalan-penipuan-lowongan-kerja",
        "title": "Apa Itu Penipuan Lowongan Kerja?",
        "tags": ["pengenalan", "definisi", "dasar"],
        "published": True,
        "body_md": """## Apa Itu Penipuan Lowongan Kerja?

**Penipuan lowongan kerja** adalah modus kejahatan di mana pelaku membuat iklan lowongan pekerjaan palsu dengan mengatasnamakan perusahaan ternama atau perusahaan fiktif untuk memperdaya para pencari kerja.

### Modus Operandi Umum:
- **Pungutan Biaya**: Meminta uang pendaftaran, biaya tiket akomodasi/travel fiktif dengan janji akan diganti (reimburse), atau biaya seragam dan tes kesehatan.
- **Pencurian Data Pribadi (Identity Theft)**: Meminta foto KTP, KK, buku tabungan, atau nomor rekening bank di tahap awal tanpa alasan seleksi yang jelas.
- **Eksploitasi Tugas (Task Scam / Like & Subscribe)**: Meminta korban menyelesaikan tugas sederhana dengan iming-iming komisi harian, lalu menuntut deposit uang untuk membuka komisi lebih besar.
- **Panggilan Seleksi Massal Tanpa Melamar**: Mengirimkan surat undangan seleksi wawancara di kota lain melalui WhatsApp/Email padahal Anda tidak pernah melamar di perusahaan tersebut.""",
    },
    {
        "slug": "ciri-ciri-lowongan-pekerjaan-palsu",
        "title": "Ciri-Ciri Lowongan Pekerjaan Palsu",
        "tags": ["ciri-ciri", "tanda-bahaya", "red-flags"],
        "published": True,
        "body_md": """## Ciri-Ciri Lowongan Pekerjaan Palsu

Waspadai tanda-tanda bahaya (*red flags*) berikut saat membaca lowongan atau menerima panggilan kerja:

### 1. Gaji Sangat Tinggi & Tidak Masuk Akal
Menawarkan gaji puluhan juta rupiah untuk pekerjaan entri dasar tanpa syarat keahlian atau pengalaman khusus.

### 2. Meminta Transfer Uang di Awal
Perusahaan resmi **tidak pernah** memungut biaya sepeser pun dalam proses rekrutmen. Waspadai permintaan transfer travel agen tertentu (misalnya travel fiktif di Bali/Surabaya/Jakarta) dengan iming-iming tiket akan di-*reimburse* panitia.

### 3. Identitas Perusahaan Fiktif / Tidak Jelas
- Menggunakan alamat kantor palsu atau alamat virtual office yang mencurigakan.
- Tidak memiliki website resmi, profil LinkedIn korporat, atau rekam jejak legalitas di database AHU Kemenkumham / CompanyHouse.

### 4. Menggunakan Domain Email Gratisan
Perusahaan profesional menggunakan email dengan domain sendiri (contoh: `recruitment@astra.co.id`), bukan `@gmail.com`, `@yahoo.com`, atau domain generator sekali pakai (`@yopmail.com`).

### 5. Janji Pasti Diterima (Garansi Kelulusan)
Menjanjikan 100% langsung diterima tanpa proses wawancara teknis atau uji kompetensi yang terstruktur.""",
    },
    {
        "slug": "tips-pencegahan-dan-verifikasi-mandiri",
        "title": "Tips Pencegahan & Perlindungan Diri",
        "tags": ["pencegahan", "tips", "keamanan", "panduan"],
        "published": True,
        "body_md": """## Langkah Sederhana Melindungi Diri

Gunakan langkah-langkah praktis berikut sebelum merespons panggilan kerja atau mengirimkan berkas lamaran:

### 1. Riset Mendalam Sebelum Melamar
- Cari nama perusahaan di mesin pencari dan cek website resmi.
- Verifikasi legalitas perusahaan melalui alat deteksi **CePu** atau cek nomor SK AHU Kemenkumham.
- Cek ulasan mantan karyawan di portal karir tepercaya (seperti Jobstreet, Glassdoor, LinkedIn).

### 2. Jangan Pernah Membayar Biaya Apapun
Ingat prinsip dasar rekrutmen: **Perusahaan yang mencari karyawan, bukan mencari uang dari pelamar**. Jika ada permintaan biaya tiket, hotel, materai, atau pelatihan kerja, segera batalkan.

### 3. Waspadai Permintaan Dokumen Sensitif
Jangan mengirimkan foto KTP, Kartu Keluarga, swafoto memegang KTP, atau informasi buku rekening bank jika baru dalam tahap seleksi administrasi awal.

### 4. Verifikasi Kontak Rekruter
- Hubungi nomor resmi kantor atau customer support yang tertera di website resmi perusahaan untuk mengonfirmasi keaslian jadwal wawancara.
- Gunakan fitur deteksi **CePu** untuk memeriksa reputasi nomor WhatsApp dan keabsahan domain email pengirim.""",
    },
]


async def seed_initial_education_articles(db: AsyncSession) -> int:
    """Mengisi database dengan artikel awal dari EducationPage jika tabel masih kosong."""
    repo = EducationArticleRepository(db)
    existing = await repo.list_all()
    if existing:
        return 0

    inserted = 0
    for art in INITIAL_EDUCATION_ARTICLES:
        await repo.upsert_by_slug(
            slug=art["slug"],
            title=art["title"],
            body_md=art["body_md"],
            tags=art["tags"],
            published=art["published"],
        )
        inserted += 1

    logger.info("Berhasil men-seed %d artikel edukasi awal.", inserted)
    return inserted

# CePu Backend API

Sistem deteksi dan edukasi dini risiko penipuan lowongan kerja berbasis analisis pola iklan.

## Cara Menjalankan

```bash
cd cepu
pip install -r api/requirements.txt
cp deploy/.env.example api/.env   # isi sesuai environment kamu
uvicorn api.main:app --reload --port 8000
```

Server berjalan di `http://127.0.0.1:8000`. Dokumentasi interaktif (Swagger) ada di `/docs`.

Pertama kali dijalankan, server akan mendownload model IndoBERT (~500MB) dari HuggingFace Hub — butuh koneksi internet dan bisa memakan waktu beberapa menit. Run berikutnya jauh lebih cepat karena model sudah ter-cache.

## Menjalankan Test

```bash
python -m pytest -v
```

140 test, semuanya berjalan tanpa perlu koneksi internet, Redis, atau database asli (pakai SQLite + fakeredis untuk isolasi test).

## Endpoint Utama

### `POST /v1/detect`
Deteksi risiko penipuan dari teks lowongan, nomor telepon, email, atau nama perusahaan.

**Request** (form-data, semua field opsional kecuali minimal satu harus diisi):
| Field | Tipe | Keterangan |
|---|---|---|
| `text` | string | Teks lowongan/pesan |
| `company` | string | Nama perusahaan |
| `email` | string | Email pengirim |
| `phone` | string | Nomor telepon |
| `image` | file | Screenshot (maks 2MB) |

**Response 200:**
```json
{
  "request_id": "uuid",
  "risk_score": 0.74,
  "category": "tinggi",
  "reasons": ["Teks lowongan menunjukkan pola bahasa yang mirip modus penipuan"],
  "alternatives": [],
  "degraded_sources": [],
  "processing_ms": 1240,
  "model_version": "indobert-v1"
}
```

`category`: `"rendah"` | `"sedang"` | `"tinggi"`

### `POST /v1/reports`
Laporkan lowongan mencurigakan.

**Request** (form-data): `suspect_phone`, `suspect_email`, `suspect_company`, `message_raw`, `screenshot` — minimal satu diisi.

**Response 200:** `{"id": "uuid", "status": "pending"}`

### `GET /healthz`
Status layanan dan model. `{"status": "ok", "model_loaded": true, "model_version": "indobert-v1"}`

### `POST /internal/wa/inbound`
Endpoint internal untuk gateway WhatsApp (butuh header `X-Internal-Token`). Tidak dipakai frontend web.

## Kode Error

| Kode | Penyebab |
|---|---|
| 400 | Payload kosong |
| 413 | File di atas 2MB |
| 415 | Tipe file tidak didukung |
| 429 | Rate limit terlampaui (10 deteksi/menit, 5 laporan/jam per IP) |
| 503 | Model belum siap dimuat |

## Environment Variables

Lihat `deploy/.env.example` untuk daftar lengkap. Yang wajib diisi: `DB_URL` (Postgres/Supabase), `REDIS_URL`, `INTERNAL_TOKEN`.

## Struktur Proyek

```
cepu/
├── api/
│   ├── core/          # config, error handling, rate limit, cache
│   ├── db/            # model & repository database
│   ├── routers/       # endpoint HTTP
│   ├── services/       # anonimisasi, ekstraksi entitas, validator, BERT, risk scorer, bot WA
│   └── tests/
├── scripts/           # seed_company_registry.py
└── deploy/.env.example
```

## Catatan Implementasi

- **OCR**: Menggunakan **RapidOCR (ONNX Runtime)** untuk ekstraksi teks gambar secara cepat dan efisien pada CPU/VPS.
- **Validator Legalitas Perusahaan**: Terintegrasi dengan scraper modular **companyhouse.id** berbasis session HTTP, secara otomatis memverifikasi dan menyimpan profil badan hukum ke database `company_registry`.
- **Email Verifier Multi-Tahap**:
  1. **MX & DNS Active Records**: Memeriksa apakah domain email memiliki mail exchanger aktif via `dnspython`. Jika MX tidak ditemukan, domain diberi skor penalti (0.80).
  2. **Disposable & Temporary Webmail Detection (Database & GitHub Sync)**:
     - Menggunakan tabel database `disposable_domains` yang disinkronisasi secara berkala dari repositori open-source GitHub (`disposable-email-domains/disposable-email-domains`).
     - Sinkronisasi manual/cron job mingguan dapat dijalankan melalui script `python scripts/sync_disposable_domains.py`.
     - Terdapat fallback ke environment variable `DISPOSABLE_EMAIL_DOMAINS` jika tabel DB belum di-seed.
     - Jika terdeteksi sebagai disposable domain, sistem mengenakan penalti berat (0.95).
  3. **Domain Mismatch & Similarity (Lookalike/Typosquatting)**: Menghitung jarak Levenshtein antara domain email dengan nama perusahaan resmi. Jika terdeteksi modus typosquatting atau penambahan prefiks/sufiks (contoh: perusahaan `tokopedia` namun menggunakan email `hrd@tokopedia-recruitment.com`), domain langsung ditandai sebagai indikasi impersonasi/spoofing (0.85).
  4. **Corporate vs Free Webmail Flag**: Jika pengirim mengklaim sebagai entitas korporasi formal (`PT`, `CV`, dsb.) tetapi menggunakan domain webmail publik gratis (`@gmail.com`, `@yahoo.com`, dsb. dari `FREE_EMAIL_DOMAINS`), sistem menerapkan penalti (0.70) dan memberikan alasan edukasi terkait penggunaan email resmi perusahaan.




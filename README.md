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

## Keterbatasan Saat Ini

- OCR untuk input gambar belum diimplementasikan
- Validator AHU/LinkedIn masih placeholder (data legitimasi perusahaan pakai `company_registry` internal, hasil seed dari data lowongan yang berhasil dikumpulkan)
- Tabel `disposable_domains` dan `model_artifacts` (sesuai skema arsitektur) belum dibuat
- Job cleanup retensi data (hapus data lama otomatis) belum ada

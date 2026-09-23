# CePu - Sistem Deteksi & Edukasi Dini Penipuan Lowongan Kerja

CePu adalah platform terpadu untuk mengenali, mendeteksi, dan melaporkan indikasi penipuan lowongan kerja secara dini. Menggabungkan klasifikasi NLP berbasis IndoBERT, validasi multi-sumber legalitas korporasi, verifikasi rekam reputasi nomor kontak, dan analisis keaslian domain email pengirim.

---

## 🚀 Panduan Menjalankan Sistem

Aplikasi ini menggunakan **satu file konfigurasi `.env` terpusat** di root direktori proyek, yang secara otomatis dibaca oleh Backend (FastAPI) maupun Frontend (Vite/React).

### 1. Konfigurasi Lingkungan (Satu File `.env`)

Cukup buat satu file `.env` di root direktori proyek:
```bash
cp deploy/.env.example .env
```
*(Backend dan Frontend akan otomatis membaca konfigurasi dari root `.env` ini tanpa perlu membuat banyak file terpisah).*

### 2. Menjalankan Backend (FastAPI)
```bash
# Aktifkan virtual environment
source .venv/bin/activate

# Install dependensi (jika belum)
pip install -r api/requirements.txt

# Jalankan server API
uvicorn api.main:app --reload --port 5687
```
- Server Backend berjalan di `http://127.0.0.1:5687`.
- Dokumentasi interaktif (Swagger UI) tersedia di: `http://127.0.0.1:5687/docs`.

### 3. Menjalankan Frontend Web (React + TypeScript + Vite)
```bash
cd web

# Install dependensi frontend
npm install   # atau: bun install

# Jalankan development server
npm run dev   # atau: bun run dev
```
- Website berjalan di `http://127.0.0.1:3000`.
- Vite dev server secara otomatis mem-proxy request `/v1` dan `/healthz` ke backend target yang ditentukan di `VITE_API_URL` (default: `http://127.0.0.1:5687`).

### 4. Menjalankan Bot WhatsApp (Personal Number via QR Code)
CePu menyediakan bot WhatsApp yang dapat langsung menggunakan **nomor WhatsApp pribadi** tanpa memerlukan akun resmi WhatsApp Business API:
```bash
cd gateway-wa

# Install dependensi gateway (jika belum)
npm install   # atau: bun install

# Jalankan gateway
npm start     # atau: bun start
```
- **Cara Menghubungkan**: Kode QR akan muncul langsung di terminal. Buka aplikasi WhatsApp di HP Anda (`Pengaturan / Titik 3` -> `Perangkat Tertaut` -> `Tautkan Perangkat`), lalu arahkan kamera ke kode QR di terminal.
- **Sesi Otomatis**: Kredensial sesi akan disimpan di folder `gateway-wa/session/` (dapat diatur lewat `WA_SESSION_PATH`). Setelah scan pertama kali, bot akan otomatis tersambung tanpa perlu scan ulang.
- **Fitur Chat Bot**:
  - `1` / `Edukasi`: Tips & artikel mengenali modus penipuan lowongan kerja.
  - `2` / `Lapor`: Mengirimkan laporan penipuan lowongan untuk disimpan ke database.
  - `3` / `Deteksi`: Panduan input data loker lengkap (nomor, email, perusahaan, pesan, screenshot).
  - Teks langsung: Mengirim langsung pesan loker untuk dicek skor risiko & rekomendasi alternatif pekerjaan aman.
  - Ketik `bantuan` untuk panduan atau `reset` untuk memulai ulang sesi.

---

## 🐳 Deployment Menggunakan Docker Container

Seluruh sistem CePu (Backend API, Frontend Web Nginx, WhatsApp Gateway, PostgreSQL, dan Redis) telah dikemas dalam container Docker:

### 1. Build & Jalankan Semua Container
```bash
# Jalankan seluruh stack
docker compose up -d --build
```

### 2. Memindai QR Code WhatsApp di Docker
Untuk melihat kode QR WhatsApp gateway dan menghubungkan nomor pribadi Anda:
```bash
docker logs -f cepu-gateway-wa
```
Pindai kode QR yang muncul di terminal menggunakan aplikasi WhatsApp (`Perangkat Tertaut`). Sesi login akan otomatis tersimpan di volume Docker `wa_session`.

### 3. Menghentikan Container
```bash
docker compose down
```

---

## ⚙️ Variabel Konfigurasi (`.env`)

| Variabel | Default | Keterangan |
|---|---|---|
| `DB_URL` | `sqlite:///./cepu_dev.db` | URL database PostgreSQL atau SQLite lokal. |
| `REDIS_URL` | `redis://localhost:6379/0` | URL Redis cache. |
| `INTERNAL_TOKEN` | `change-me` | Token autentikasi internal gateway WhatsApp. |
| `HF_MODEL_ID` | `Kiuyha/indobert-job-fraud-detection` | Hugging Face model IndoBERT deteksi scam. |
| `NER_MODEL_ID` | `fahmisyaifudin/indobert_ner_p1` | Model IndoBERT token-classification untuk NER. |
| `BERT_MAX_LENGTH` | `512` | Panjang token sequence klasifikasi IndoBERT. |
| `NER_MAX_LENGTH` | `512` | Panjang token sequence Named Entity Recognition. |
| `OCR_LANG` | `ind+eng` | Bahasa OCR (RapidOCR ONNX). |
| `COMPANYHOUSE_BASE_URL` | `https://companyhouse.id` | Endpoint target scraping legalitas perusahaan. |
| `COMPANYHOUSE_SESSION_COOKIE` | *(base64 string)* | Cookie awal sesi scraping `companyhouse.id`. |
| `ADUANNOMOR_BASE_URL` | `https://aduannomor.id` | API pengecekan aduan penipuan nomor Kominfo. |
| `KREDIBEL_BASE_URL` | `https://www.kredibel.com` | Target pengecekan reputasi nomor via HTTP/2. |
| `KREDIBEL_SESSION_COOKIE` | *(base64 string)* | Cookie awal sesi scraping `kredibel.com`. |
| `DISPOSABLE_DOMAINS_SYNC_URL` | *(raw github url)* | URL upstream sinkronisasi blocklist domain email sekali pakai. |
| `FREE_EMAIL_DOMAINS` | `gmail.com,yahoo.com,...` | Daftar domain webmail publik gratis. |
| `VITE_API_URL` | `http://127.0.0.1:5687` | Target URL backend untuk frontend (client & dev proxy). |

---

## 🧪 Menjalankan Test Suite

```bash
pytest -v
```
Seluruh 162 pengujian berjalan tanpa ketergantungan jaringan eksternal (terisolasi menggunakan mock, SQLite in-memory, dan fakeredis).

---

## 📡 Endpoint Utama Backend

### `POST /v1/detect` & `POST /v1/detect/stream` (SSE Streaming)
Menganalisis indikasi penipuan dari teks lowongan, nomor telepon, email pengirim, nama perusahaan, atau gambar tangkapan layar.

- **`POST /v1/detect`**: Mengembalikan response JSON lengkap setelah seluruh tahapan selesai.
- **`POST /v1/detect/stream`**: Mengalirkan progres real-time (`text/event-stream` / Server-Sent Events) ke antarmuka pengguna web dan bot, mengabarkan tahapan analisis (OCR -> IndoBERT NER -> IndoBERT Classifier -> Multi-Source Validators -> Risk Scorer -> Result).

**Request Form-Data** (minimal 1 field terisi):
- `text`: Teks iklan lowongan kerja.
- `company`: Nama perusahaan perekrut.
- `email`: Alamat email perekrut.
- `phone`: Nomor telepon / WhatsApp perekrut.
- `image`: File screenshot lowongan (JPG/PNG/WebP, maks 2MB).

**Response JSON (`/v1/detect`) / Result Event (`/v1/detect/stream`):**
```json
{
  "request_id": "9439a619-66a2-4f51-b879-65dfaaac3346",
  "risk_score": 0.70,
  "category": "tinggi",
  "reasons": [
    "Teks lowongan menunjukkan pola bahasa yang sangat mirip modus penipuan",
    "Terdapat kata kunci mencurigakan: transfer, biaya pendaftaran"
  ],
  "alternatives": [],
  "degraded_sources": [],
  "processing_ms": 1240,
  "model_version": "indobert-v1"
}
```

### `POST /v1/reports`
Melaporkan lowongan penipuan terkonfirmasi ke basis data blacklist intelijen.
- **Request**: `suspect_phone`, `suspect_email`, `suspect_company`, `message_raw`, `screenshot`.
- **Response**: `{"id": "uuid", "status": "pending"}`.

### `GET /healthz`
Pemeriksaan kesehatan sistem dan status pemuatan model AI.

---

## 🏗️ Fitur & Arsitektur Utama

### 1. Klasifikasi AI IndoBERT & Preprocessing Ekstraksi Fitur
- Menggunakan arsitektur model fine-tuned **`Kiuyha/indobert-job-fraud-detection`** dan NER **`fahmisyaifudin/indobert_ner_p1`**.
- Ekstraksi entitas mencakup penyaringan teks artefak sumber (EMSCAD, nomor telepon, masking URL, dan normalisasi).

### 2. Ekstraksi Teks Gambar (RapidOCR ONNX)
- Menggunakan engine **RapidOCR** berbasis ONNX Runtime untuk ekstraksi teks dari gambar screenshot yang diunggah pengguna tanpa beban GPU tinggi.

### 3. Verifikasi Legalitas Perusahaan (CompanyHouse.id)
- Scraper modular berbasis session HTTP yang mengekstrak 8 atribut badan hukum resmi (nama perusahaan, bentuk badan hukum, nomor registrasi, nomor SK, kota, negara, telepon, dan alamat terdaftar) dan menyimpannya ke database lokal `company_registry`.
- **Auto-Update Session Cookies**: Secara dinamis memperbarui dan mempertahankan token sesi dari header `Set-Cookie` respon server, mencegah scraper mengalami kegagalan saat token berotasi.

### 4. Pengecekan Reputasi Nomor Telepon Multi-Sumber
- **aduannomor.id (Kominfo)**: Memeriksa database aduan resmi penipuan seluler via form POST dengan header `Referer` bypass. Nomor dengan `reported_count > 0` langsung diberi penalti skor penipuan tinggi (`0.95`).
- **Fallback Kredibel.com (HTTP/2)**: Jika aduannomor.id bersih / 0 laporan, sistem memeriksa halaman ulasan Kredibel menggunakan protokol HTTP/2. Nomor dengan ulasan negatif/buruk diberi skor `0.85`, sedangkan nomor tanpa ulasan / bersih diberi skor aman (`0.20`).
- **Auto-Update Cookies**: Melacak dan menyimpan token `kredibel_session` dan `XSRF-TOKEN` secara otomatis.

### 5. Verifikasi Keaslian Domain Email Pengirim
- **MX & Active DNS Resolver**: Menjamin domain email memiliki mail server aktif.
- **Deteksi Email Sementara (Disposable Domains)**: Sinkronisasi database berkala dari repositori open-source GitHub (`disposable-email-domains/disposable-email-domains`) via skrip `python -m scripts.sync_disposable_domains`.
- **Typosquatting & Lookalike Check**: Membandingkan kemiripan string (jarak Levenshtein) antara domain email dan nama perusahaan resmi guna mendeteksi modus impersonasi (contoh: `hrd@tokopedia-recruitment.com`).
- **Penalti Email Publik Gratis**: Klaim entitas formal korporasi (`PT`, `CV`) yang menggunakan penyedia email gratis (`@gmail.com`, `@yahoo.com`) dikenakan penalti edukatif (`0.70`).

### 6. Antarmuka Web Modern (Vite + React + TypeScript)
- Tata letak responsif penuh untuk desktop dan mobile yang disesuaikan dengan referensi UI (`example/web/`).
- **Deteksi Tema Otomatis**: Mendeteksi preferensi tema sistem operasi (`prefers-color-scheme`) untuk mode gelap/terang secara otomatis disertai tombol toggle manual.
- Badge skor numerik presisi beserta persentase risiko pada modal hasil deteksi.

"""
Fixture bersama untuk semua test.

Dua hal penting yang di-setup di sini:

1. Redis di-override dengan `fakeredis` (Redis palsu yang jalan di
   memori Python, tanpa perlu instalasi server Redis beneran). Supaya
   siapapun bisa jalankan `pytest` di komputernya tanpa install Redis
   dulu. Production tetap pakai Redis asli lewat REDIS_URL di .env.

2. File database dev (`cepu_dev.db`, SQLite) dihapus di awal sesi test
   supaya tiap kali `pytest` dijalankan mulai dari kondisi bersih, tidak
   menumpuk data dari run sebelumnya.
"""
import os

# PENTING: paksa test selalu pakai SQLite terpisah, TIDAK PEDULI apa isi
# file .env (yang production-nya bisa saja berisi connection string
# Postgres/Supabase asli). Ini harus di-set SEBELUM baris import apapun
# dari `api`, karena Settings/engine dibuat sekali saat modul pertama
# kali di-import.
#
# Tanpa ini: begitu .env berisi Postgres asli, `pytest` ikut mencoba
# konek ke situ juga -- padahal test seharusnya cepat, lokal, dan tidak
# bergantung sama sekali pada koneksi internet/kredensial production.
os.environ["DB_URL"] = "sqlite:///./cepu_test.db"

# Hapus DB test lama SEBELUM import apapun dari api/, supaya database
# selalu mulai bersih tiap kali test dijalankan.
_TEST_DB_FILE = "cepu_test.db"
if os.path.exists(_TEST_DB_FILE):
    os.remove(_TEST_DB_FILE)

import pytest
from fakeredis import aioredis as fakeredis_aioredis
from fastapi.testclient import TestClient

from api.main import app
from api.core.redis_client import get_redis_client
from api.services import bert_infer


@pytest.fixture(autouse=True)
def mock_bert_load(monkeypatch):
    """
    Ganti load_model() dengan versi palsu yang instan, supaya `pytest`
    TIDAK mendownload model 498MB dari HuggingFace di setiap test run --
    sama semangatnya dengan fakeredis untuk Redis dan SQLite untuk
    Postgres.

    Sekaligus, default-kan predict_fraud_probability supaya SELALU
    mengembalikan nilai netral (0.5) tanpa benar-benar butuh `torch`
    terinstall -- test yang secara spesifik ingin menguji hasil prediksi
    BERT tertentu (misal risk_score untuk P_BERT tinggi) tinggal panggil
    `monkeypatch.setattr("api.routers.detect.predict_fraud_probability", ...)`
    sendiri di dalam test tersebut, itu akan menimpa default ini (fixture
    dan test memakai instance `monkeypatch` yang sama, jadi override-nya
    aman dan otomatis dibersihkan setelah test selesai).
    """

    async def _fake_load_model():
        bert_infer._mark_loaded_for_tests()

    async def _fake_predict(text: str) -> float:
        return 0.5

    monkeypatch.setattr("api.main.load_model", _fake_load_model)
    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake_predict)


@pytest.fixture()
def client(mock_bert_load):
    # PENTING: harus pakai "with" supaya event "startup" (yang membuat
    # tabel-tabel DB lewat init_models()) benar-benar dijalankan. Tanpa
    # "with", startup event di-skip dan query pertama ke DB akan gagal
    # dengan error "no such table".
    #
    # `mock_bert_load` sengaja jadi parameter (bukan cuma autouse) supaya
    # PASTI sudah aktif sebelum TestClient() memicu lifespan startup yang
    # memanggil load_model().
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
async def fake_redis():
    """
    Ganti Redis asli dengan fakeredis untuk setiap test, dan flush
    datanya sebelum & sesudah supaya counter rate limit antar-test
    tidak saling mempengaruhi (persis seperti reset in-memory di fase
    sebelumnya, cuma sekarang lewat fakeredis).
    """
    fake = fakeredis_aioredis.FakeRedis(decode_responses=True)
    await fake.flushall()

    app.dependency_overrides[get_redis_client] = lambda: fake

    yield fake

    await fake.flushall()
    app.dependency_overrides.pop(get_redis_client, None)

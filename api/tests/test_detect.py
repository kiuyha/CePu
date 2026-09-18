import io

import pytest

from api.core.config import get_settings

SETTINGS = get_settings()


def _fallback_jpeg() -> bytes:
    # JPEG minimal valid (1x1 putih), cukup untuk lolos cek content-type + size.
    import base64

    b64 = (
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkI"
        "CQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQ"
        "EBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAABAAEDASIA"
        "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEB"
        "AQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX"
        "/9k="
    )
    return base64.b64decode(b64)


# ---------- Payload valid ----------

def test_detect_with_text_only_returns_200_and_contract_shape(client):
    response = client.post("/v1/detect", data={"text": "lowongan transfer dulu 500rb"})
    assert response.status_code == 200

    body = response.json()
    for key in (
        "request_id",
        "risk_score",
        "category",
        "reasons",
        "alternatives",
        "degraded_sources",
        "processing_ms",
        "model_version",
    ):
        assert key in body, f"Field '{key}' hilang dari response, padahal ada di kontrak API"


def test_detect_with_company_phone_email_only_returns_200(client):
    """Bukan cuma 'text' yang harus diterima -- field lain sendiri-sendiri juga valid."""
    response = client.post(
        "/v1/detect",
        data={"company": "PT Contoh Sejahtera", "phone": "081234567890", "email": "a@b.com"},
    )
    assert response.status_code == 200


def test_detect_with_valid_image_returns_200(client):
    files = {"image": ("foto.jpg", _fallback_jpeg(), "image/jpeg")}
    response = client.post("/v1/detect", files=files)
    assert response.status_code == 200


def test_detect_with_unicode_company_name_does_not_crash(client):
    """Field dengan emoji/karakter unicode tidak boleh bikin server error."""
    response = client.post("/v1/detect", data={"company": "PT Kerja Cepat 🚀💰"})
    assert response.status_code == 200


# ---------- Payload tidak valid ----------

def test_detect_with_empty_payload_returns_400(client):
    response = client.post("/v1/detect")
    assert response.status_code == 400
    assert response.json()["error"] == "empty_payload"


def test_detect_with_only_whitespace_text_returns_400(client):
    """String isinya cuma spasi harus dianggap kosong, bukan valid."""
    response = client.post("/v1/detect", data={"text": "   "})
    assert response.status_code == 400


def test_detect_with_wrong_file_type_returns_415(client):
    files = {"image": ("dokumen.txt", b"bukan gambar", "text/plain")}
    response = client.post("/v1/detect", data={"text": "cek ini"}, files=files)
    assert response.status_code == 415
    assert response.json()["error"] == "unsupported_media_type"


def test_detect_with_oversized_file_returns_413(client):
    big_content = b"0" * (SETTINGS.max_upload_size_bytes + 1)
    files = {"image": ("besar.jpg", big_content, "image/jpeg")}
    response = client.post("/v1/detect", files=files)
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_detect_with_empty_string_image_field_is_treated_as_no_image(client):
    """
    Reproduksi bug nyata: Swagger UI mengirim field 'image' sebagai string
    kosong (bukan file) kalau user tidak pilih file apapun -- persis seperti
    curl -F 'image=' (bukan cuma field 'image' yang hilang total dari
    request). Endpoint harus tetap 200, bukan 422.
    """
    response = client.post(
        "/v1/detect",
        data={
            "text": "deteksi penipuan",
            "company": "",
            "email": "",
            "phone": "",
            "image": "",  # persis seperti yang dikirim Swagger UI
        },
    )
    assert response.status_code == 200
    """Boundary check: ukuran PAS di batas 2MB harus tetap lolos (bukan '>=')."""
    exact_content = b"0" * SETTINGS.max_upload_size_bytes
    files = {"image": ("pas.jpg", exact_content, "image/jpeg")}
    response = client.post("/v1/detect", files=files)
    assert response.status_code == 200


# ---------- Rate limit ----------

def test_detect_rate_limit_triggers_429_after_max_requests(client):
    limit = SETTINGS.rate_limit_detect_per_minute

    for i in range(limit):
        response = client.post("/v1/detect", data={"text": f"percobaan {i}"})
        assert response.status_code == 200, f"Request ke-{i+1} harusnya masih di bawah limit"

    # Request berikutnya (melebihi limit) harus kena 429
    response = client.post("/v1/detect", data={"text": "harusnya kena limit"})
    assert response.status_code == 429
    assert response.json()["error"] == "rate_limit_exceeded"

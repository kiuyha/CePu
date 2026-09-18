from api.core.config import get_settings

SETTINGS = get_settings()


def test_report_with_message_returns_pending_status(client):
    response = client.post("/v1/reports", data={"message_raw": "lowongan mencurigakan minta transfer"})
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "pending"
    assert "id" in body and body["id"]  # id tidak boleh kosong


def test_report_with_only_suspect_phone_is_valid(client):
    """Laporan tanpa message_raw tapi ada suspect_phone tetap harus diterima."""
    response = client.post("/v1/reports", data={"suspect_phone": "081234567890"})
    assert response.status_code == 200


def test_report_with_empty_payload_returns_400(client):
    response = client.post("/v1/reports")
    assert response.status_code == 400
    assert response.json()["error"] == "empty_payload"


def test_report_with_oversized_screenshot_returns_413(client):
    big_content = b"0" * (SETTINGS.max_upload_size_bytes + 1)
    files = {"screenshot": ("besar.jpg", big_content, "image/jpeg")}
    response = client.post("/v1/reports", files=files)
    assert response.status_code == 413


def test_report_with_wrong_screenshot_type_returns_415(client):
    files = {"screenshot": ("dokumen.pdf", b"%PDF-1.4 fake", "application/pdf")}
    response = client.post(
        "/v1/reports", data={"message_raw": "cek ini"}, files=files
    )
    assert response.status_code == 415


def test_report_rate_limit_triggers_429_after_max_requests(client):
    limit = SETTINGS.rate_limit_report_per_hour

    for i in range(limit):
        response = client.post("/v1/reports", data={"message_raw": f"laporan {i}"})
        assert response.status_code == 200, f"Laporan ke-{i+1} harusnya masih di bawah limit"

    response = client.post("/v1/reports", data={"message_raw": "harusnya kena limit"})
    assert response.status_code == 429
    assert response.json()["error"] == "rate_limit_exceeded"

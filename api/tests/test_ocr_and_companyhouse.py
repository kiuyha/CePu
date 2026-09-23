"""
Test untuk CompanyHouse.id scraper dan RapidOCR ONNX service.
"""
import io
import pytest
from PIL import Image, ImageDraw

from api.services.ocr import extract_text_from_image_bytes
from api.services.validators.companyhouse_scraper import (
    CompanyHouseScraper,
    generate_company_slug,
)
from api.services.validators.ahu import check_company_ahu
from api.db.base import async_session_factory
from api.db.repository import CompanyRegistryRepository, DetectionRepository


def test_generate_company_slug():
    assert generate_company_slug("PT. Makna Jaya Pratama") == "makna-jaya-pratama"
    assert generate_company_slug("CV Maju Lancar") == "maju-lancar"
    assert generate_company_slug("Yayasan Harapan Bangsa (YHB)") == "harapan-bangsa-yhb"


def test_companyhouse_parser_extracts_all_required_schema():
    html_sample = """
    <html>
      <head><title>PT. Makna Jaya Pratama</title></head>
      <body>
        <h1>PT. Makna Jaya Pratama</h1>
        <div class="info-list">
          <div>Legal Entity Type: Limited Liability Company (PT)</div>
          <div>Business Number: 1175425</div>
          <div>SK Number: AHU-0012345.AH.01.01.TAHUN 2020</div>
          <div>City: KOTA SEMARANG</div>
          <div>Country: Indonesia</div>
          <div>Phone: 082117200589</div>
          <div class="address">Jl. Dr. Sutomo No. 11A Lantai 3, KOTA SEMARANG, Indonesia</div>
        </div>
      </body>
    </html>
    """
    scraper = CompanyHouseScraper()
    data = scraper.parse_company_page(html_sample)

    assert data["company_name"] == "PT. Makna Jaya Pratama"
    assert data["legal_entity_type"] == "Limited Liability Company (PT)"
    assert data["business_number"] == "1175425"
    assert data["sk_number"] == "AHU-0012345.AH.01.01.TAHUN 2020"
    assert data["city"] == "KOTA SEMARANG"
    assert data["country"] == "Indonesia"
    assert data["phone"] == "082117200589"
    assert "Jl. Dr. Sutomo" in data["registered_address"]


async def test_check_company_ahu_persists_to_db(client, monkeypatch):
    """
    Verifikasi jika scraper berhasil menemukan data perusahaan,
    data tersebut disimpan ke company_registry dan skor v_company menjadi 0.2.
    """
    fake_data = {
        "company_name": "PT Makna Jaya Pratama",
        "legal_entity_type": "Limited Liability Company (PT)",
        "business_number": "1175425",
        "sk_number": "AHU-112233",
        "city": "KOTA SEMARANG",
        "country": "Indonesia",
        "phone": "082117200589",
        "registered_address": "Jl. Dr. Sutomo",
    }

    monkeypatch.setattr(
        "api.services.validators.companyhouse_scraper.CompanyHouseScraper.fetch_company_detail",
        lambda self, name: fake_data,
    )

    async with async_session_factory() as session:
        result = await check_company_ahu("PT Makna Jaya Pratama", db=session)
        assert result.verdict_score == 0.2
        assert result.verdict_binary is False
        assert result.source == "companyhouse.id"

        repo = CompanyRegistryRepository(session)
        entry = await repo.get_by_name("PT Makna Jaya Pratama")
        assert entry is not None
        assert entry.registered is True
        assert entry.source == "companyhouse.id"


def test_rapidocr_extracts_text_from_synthesized_image():
    """Membuat gambar sederhana dengan teks menggunakan PIL, lalu ekstrak dengan RapidOCR."""
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 35), "LOWONGAN KERJA", fill=(0, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    text, score = extract_text_from_image_bytes(image_bytes)
    assert "LOWONGAN" in text.upper() or "KERJA" in text.upper()
    assert score > 0.0


async def test_detect_with_image_triggers_ocr_and_saves_ocr_text(client, monkeypatch):
    """Menguji bahwa upload gambar diproses OCR dan tersimpan di field ocr_text di DB."""
    img = Image.new("RGB", (320, 120), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((10, 30), "PT Maju Lancar gaji 10jt", fill=(0, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    async def _fake_predict(text: str) -> float:
        return 0.4

    monkeypatch.setattr("api.services.detection_pipeline.predict_fraud_probability", _fake_predict)

    files = {"image": ("poster.jpg", image_bytes, "image/jpeg")}
    response = client.post("/v1/detect", files=files)
    assert response.status_code == 200

    body = response.json()
    req_id = body["request_id"]

    async with async_session_factory() as session:
        repo = DetectionRepository(session)
        rec = await repo.get_by_id(req_id)
        assert rec is not None
        assert rec.ocr_text is not None
        assert len(rec.ocr_text.strip()) > 0

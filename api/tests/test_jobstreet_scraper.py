"""Test pure-function JobStreet: payload builder, parser, dan intent WA.

Tidak menyentuh jaringan — search_jobs() asli tidak dipanggil di sini.
"""
from api.services.jobstreet_scraper import JobStreetScraper, build_payload, parse_jobs
from api.services.wa_bot import _parse_job_search_intent


def test_build_payload_memakai_session_dari_env():
    payload = build_payload(
        role="driver",
        location_text="Jakarta",
        page=1,
        page_size=5,
        session_id="sess-123",
        sol_visitor_id="sol-456",
    )
    assert payload["operationName"] == "JobSearchV7"
    intent = payload["variables"]["params"]["searchIntent"]
    assert intent["text"] == "driver"
    assert intent["where"] == "Jakarta"
    assert payload["variables"]["params"]["sessionId"] == "sess-123"
    assert payload["variables"]["params"]["searchContext"]["solVisitorId"] == "sol-456"
    assert "query" in payload and "JobSearchV7" in payload["query"]


def test_build_payload_tanpa_lokasi_tidak_ada_where():
    payload = build_payload(role="kasir")
    intent = payload["variables"]["params"]["searchIntent"]
    assert "where" not in intent


def test_headers_tanpa_cookie_browser_cukup_session_id():
    scraper = JobStreetScraper.__new__(JobStreetScraper)
    from api.core.config import get_settings

    scraper.settings = get_settings()
    scraper.session_id = "sess-abc"
    scraper.visitor_id = "sess-abc"
    scraper.sol_visitor_id = "sess-abc"
    headers = scraper._headers()
    assert "cf_clearance" not in headers.get("cookie", "")
    assert "JobseekerSessionId=sess-abc" in headers["cookie"]
    assert headers["x-seek-ec-sessionid"] == "sess-abc"
    # Backend menolak query tanpa header browser ini (UNSTABLE_QUERY_ERROR).
    assert headers["x-custom-features"] == "application/features.seek.all+json"
    assert headers["sec-fetch-site"] == "same-origin"


def _fake_response():
    return {
        "data": {
            "jobSearchV7": {
                "results": {
                    "jobs": [
                        {
                            "id": "111",
                            "title": "Driver Operasional",
                            "organisation": {"name": "PT Maju Jaya"},
                            "advertiser": {"name": "PT Maju Jaya"},
                            "location": {"displayName": {"text": "Jakarta"}},
                            "salary": {"min": 5000000, "max": 7000000, "currency": "IDR"},
                            "cjs": {
                                "salary": {"displayValue": "Rp 5–7 jt"},
                                "workTypes": [{"name": "Full time"}],
                            },
                            "listedAt": {"dateTimeUtc": "2026-01-01T00:00:00Z", "label": "1h ago"},
                            "url": "https://id.jobstreet.com/job/111",
                        },
                        {
                            "id": "222",
                            "title": "Driver Pribadi",
                            "organisation": {},
                            "advertiser": {"name": "Budi"},
                            "location": {},
                            "salary": {},
                            "cjs": {},
                            "listedAt": {},
                            "url": None,
                        },
                    ]
                }
            }
        }
    }


def test_parse_jobs_mengembalikan_link_dan_field_penting():
    jobs = parse_jobs(_fake_response())
    assert len(jobs) == 2
    first = jobs[0]
    assert first["title"] == "Driver Operasional"
    assert first["company"] == "PT Maju Jaya"
    assert first["location"] == "Jakarta"
    assert first["salary_min"] == 5000000
    assert first["url"] == "https://id.jobstreet.com/job/111"
    # url kosong -> fallback dari id
    assert jobs[1]["url"] == "https://id.jobstreet.com/job/222"


def test_parse_jobs_response_rusak_jadi_list_kosong():
    assert parse_jobs({}) == []
    assert parse_jobs({"data": None}) == []
    assert parse_jobs({"data": {"jobSearchV7": None}}) == []


def test_parse_job_search_intent():
    assert _parse_job_search_intent("cari kerja driver di Jakarta") == ("driver", "Jakarta")
    assert _parse_job_search_intent("Cari Loker Kasir") == ("Kasir", None)
    assert _parse_job_search_intent("lowongan mirip: admin") == ("admin", None)
    assert _parse_job_search_intent("/job driver di Jakarta") == ("driver", "Jakarta")
    assert _parse_job_search_intent("/job kasir") == ("kasir", None)
    assert _parse_job_search_intent("/job") is None
    assert _parse_job_search_intent("cari kerja") is None
    # pemicu tanpa posisi -> None supaya bot meminta klarifikasi, bukan scrape ngawur
    assert _parse_job_search_intent("cari pekerjaan yang mirip") is None
    assert _parse_job_search_intent("lowongan mirip") is None
    # bukan intent -> None (tetap masuk alur deteksi/menu normal)
    assert _parse_job_search_intent("PT ABC menipu saya, gaji tidak dibayar") is None
    assert _parse_job_search_intent("3") is None

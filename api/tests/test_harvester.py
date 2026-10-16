"""
Test untuk scripts/refresh_browser_sessions.py — tanpa browser asli.

Yang diuji (murni fungsi config + file, tanpa Playwright):
1. Cookie lintas domain tidak bocor antar situs (bug nyata: kredibel_session
   + junk GA pernah tertempel ke COMPANYHOUSE_SESSION_COOKIE karena satu
   profil dipakai lintas situs).
2. Kredibel ikut memanen cf_clearance.
3. write_env_values: update in-place, tambah key baru, komentar utuh, backup.
"""
import importlib.util
from pathlib import Path


def _load_harvester():
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "scripts"
        / "refresh_browser_sessions.py"
    )
    spec = importlib.util.spec_from_file_location("refresh_browser_sessions", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_filter_drops_cross_domain_cookies():
    mod = _load_harvester()
    raw = [
        {"name": "company_house_indonesia_session", "value": "sess-ch", "domain": ".companyhouse.id"},
        {"name": "XSRF-TOKEN", "value": "xsrf", "domain": ".companyhouse.id"},
        {"name": "cf_clearance", "value": "clr", "domain": ".companyhouse.id"},
        # Bocoran dari profil lintas situs: harus dibuang semua.
        {"name": "kredibel_session", "value": "sess-kr", "domain": ".kredibel.com"},
        {"name": "_ga", "value": "GA1.1.x", "domain": ".companyhouse.id"},
        {"name": "_gcl_au", "value": "1.1.x", "domain": ".companyhouse.id"},
    ]
    picked = mod._filter_site_cookies(raw, mod.SITES["companyhouse"])
    assert picked == {
        "company_house_indonesia_session": "sess-ch",
        "XSRF-TOKEN": "xsrf",
        "cf_clearance": "clr",
    }


def test_kredibel_site_config_keeps_session_and_clearance():
    mod = _load_harvester()
    names = mod.SITES["kredibel"]["cookie_names"]
    assert "kredibel_session" in names
    assert "cf_clearance" in names
    assert mod.SITES["kredibel"]["domains"] == ("kredibel.com",)


def test_companyhouse_site_config_has_no_empty_allow_all():
    mod = _load_harvester()
    names = mod.SITES["companyhouse"]["cookie_names"]
    assert names  # tidak boleh () lagi — itu penyebab kebocoran
    assert "company_house_indonesia_session" in names


def test_write_env_updates_in_place_and_backs_up(tmp_path):
    mod = _load_harvester()
    env = tmp_path / ".env"
    env.write_text(
        "# komentar\n"
        "DB_URL=sqlite:///./x.db\n"
        "KREDIBEL_SESSION_COOKIE=lama\n"
    )
    backup = mod.write_env_values(
        env,
        {"KREDIBEL_SESSION_COOKIE": "baru", "COMPANYHOUSE_SESSION_COOKIE": "ch-baru"},
    )

    assert backup is not None
    assert "KREDIBEL_SESSION_COOKIE=lama" in backup.read_text()

    content = env.read_text()
    assert "# komentar" in content
    assert "DB_URL=sqlite:///./x.db" in content
    assert "KREDIBEL_SESSION_COOKIE=baru" in content
    assert "COMPANYHOUSE_SESSION_COOKIE=ch-baru" in content
    assert "lama" not in content


def test_write_env_creates_new_file_without_backup(tmp_path):
    mod = _load_harvester()
    env = tmp_path / ".env"
    backup = mod.write_env_values(env, {"KREDIBEL_SESSION_COOKIE": "v"})
    assert backup is None
    assert env.read_text().strip() == "KREDIBEL_SESSION_COOKIE=v"


def test_write_env_leaves_commented_keys_alone(tmp_path):
    mod = _load_harvester()
    env = tmp_path / ".env"
    env.write_text("#KREDIBEL_SESSION_COOKIE=contoh\n")
    mod.write_env_values(env, {"KREDIBEL_SESSION_COOKIE": "asli"})
    content = env.read_text()
    assert "#KREDIBEL_SESSION_COOKIE=contoh" in content
    assert "\nKREDIBEL_SESSION_COOKIE=asli" in content

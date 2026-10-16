"""Pemanen sesi browser untuk scraper (JALANKAN MANUAL, bukan di request path).

Membuka Chromium asli via Playwright ke situs target, menunggu Cloudflare/
cookie terbentuk, lalu mencetak baris .env siap tempel — atau langsung
menulisnya ke .env dengan --write-env.

Butuh:  pip install playwright && playwright install chromium

Contoh:
    .venv/bin/python scripts/refresh_browser_sessions.py --site kredibel --write-env
    .venv/bin/python scripts/refresh_browser_sessions.py --site all --headed --write-env
    .venv/bin/python scripts/refresh_browser_sessions.py --site all \
        --headed --profile-dir ./sessions/chrome --write-env
Opsi --headed membuka browser terlihat (berguna kalau ada CAPTCHA yang
harus diselesaikan manual — selesaikan di jendela browser, lalu tekan
Enter di terminal). Opsi --profile-dir memakai profil persisten sehingga
kepercayaan situs menumpuk antar panen (disarankan untuk sesi awet).
Opsi --write-env menulis hasil langsung ke .env (backup lama ke .env.bak);
restart backend sesudahnya agar Settings baru terbaca.
"""
import argparse
import sys
from pathlib import Path
from typing import Optional

# Root repo = folder di atas scripts/ (tempat .env tinggal).
ROOT_DIR = Path(__file__).resolve().parent.parent

SITES = {
    "kredibel": {
        "url": "https://www.kredibel.com/",
        "env_key": "KREDIBEL_SESSION_COOKIE",
        "domains": ("kredibel.com",),
        # cf_clearance/__cf_bm = pass challenge Cloudflare. Tanpa ini,
        # cookie sesi hasil panen dibuang sia-sia saat server kena challenge.
        # Keduanya terikat IP egress + kedaluwarsa dalam hitungan jam.
        "cookie_names": ("kredibel_session", "cf_clearance", "__cf_bm"),
        "wait_ms": 6000,
        # Kredibel memberi kuota kecil untuk pencarian anonim per IP;
        # login menaikkan kuota tapi mengikat risiko flag ke akun tersebut.
        "login_hint": (
            "Kredibel membatasi kuota pencarian anonim per IP — login dengan "
            "akunmu bila butuh kuota lebih (risiko flag ditanggung akun itu; "
            "untuk demo PKM + cache, anonim biasanya cukup)"
        ),
    },
    "companyhouse": {
        "url": "https://companyhouse.id/",
        "env_key": "COMPANYHOUSE_SESSION_COOKIE",
        "domains": ("companyhouse.id",),
        # Daftar eksplisit: sesi Laravel + pass Cloudflare. cookie_names
        # kosong dulu = "ambil semua", yang terbukti membocorkan cookie
        # situs lain + junk analitik karena profil dipakai lintas situs.
        "cookie_names": (
            "company_house_indonesia_session",
            "XSRF-TOKEN",
            "cf_clearance",
            "__cf_bm",
        ),
        "wait_ms": 6000,
    },
    "jobstreet": {
        "url": "https://id.jobstreet.com/",
        "env_key": "JOBSTREET_SESSION_ID",
        "domains": ("jobstreet.com",),
        "cookie_names": ("JobseekerSessionId", "JobseekerVisitorId", "sol_id"),
        "wait_ms": 6000,
    },
}

DEFAULT_LOGIN_HINT = (
    "JANGAN login pakai akun pribadi — sesi anonim sudah cukup; "
    "login mengikat kuota & risiko flag ke akunmu"
)


def _filter_site_cookies(all_cookies: list, cfg: dict) -> dict:
    """Saring cookie browser ke milik situs ini saja.

    context.cookies() mengembalikan cookie SEMUA domain dalam profil
    (profil dipakai lintas situs) — tanpa saringan domain, cookie kredibel
    + junk analitik ikut tertempel ke COMPANYHOUSE_SESSION_COOKIE.
    """
    domains = cfg.get("domains", ())
    names = cfg.get("cookie_names", ())
    out = {}
    for c in all_cookies:
        dom = c.get("domain") or ""
        if domains and not any(d in dom for d in domains):
            continue
        if names and c.get("name") not in names:
            continue
        out[c["name"]] = c.get("value", "")
    return out


def write_env_values(env_path: Path, values: dict) -> Optional[Path]:
    """Tulis/update KEY=VALUE ke file .env tanpa merusak baris lain.

    Baris komentar dan key lain dipertahankan apa adanya; key yang belum
    ada ditambahkan di akhir. File lama dibackup ke .env.bak dulu.
    Mengembalikan path backup, atau None bila .env belum ada sebelumnya.
    """
    lines = []
    backup = None
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        backup = env_path.with_name(env_path.name + ".bak")
        backup.write_text("\n".join(lines) + ("\n" if lines else ""))
    found = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in values:
                out.append(f"{key}={values[key]}")
                found.add(key)
                continue
        out.append(line)
    for key, val in values.items():
        if key not in found:
            out.append(f"{key}={val}")
    env_path.write_text("\n".join(out) + "\n")
    return backup


def harvest(
    site_key: str, cfg: dict, headed: bool, profile_dir: Optional[str], channel: Optional[str]
) -> tuple:
    """Panen satu situs. Mengembalikan (exit_code, {ENV_KEY: value}).

    Tuple kedua kosong bila panen gagal — main() hanya menulis yang sukses.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright belum terinstal. Jalankan:\n"
            "  pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 2, {}

    print(f"[*] Membuka {cfg['url']} (headed={headed}) ...")
    with sync_playwright() as p:
        launch_kwargs: dict = {
            "headless": not headed,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        }
        # channel="chrome" memakai Google Chrome asli (bukan Chromium headless
        # shell) — jauh lebih dipercaya Cloudflare. Butuh Chrome terinstal.
        if channel:
            print(f"[*] Memakai browser channel: {channel}")
            launch_kwargs["channel"] = channel
        if profile_dir:
            # Profil persisten: cookie/riwayat menumpuk -> sesi lebih dipercaya
            # dan tidak mulai dari nol setiap panen.
            print(f"[*] Memakai profil persisten: {profile_dir}")
            context = p.chromium.launch_persistent_context(
                profile_dir,
                headless=not headed,
                channel=channel,
                args=launch_kwargs["args"],
                viewport={"width": 1366, "height": 768},
                locale="id-ID",
                timezone_id="Asia/Jakarta",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
                ),
            )
            browser = context.browser
            close = context.close
        else:
            browser = p.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                locale="id-ID",
                timezone_id="Asia/Jakarta",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
                ),
            )
            close = browser.close
        page = context.new_page()
        try:
            page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            print(f"[!] Navigasi gagal: {exc}", file=sys.stderr)
        page.wait_for_timeout(cfg["wait_ms"])

        if headed:
            hint = cfg.get("login_hint") or DEFAULT_LOGIN_HINT
            input(f"[*] Selesaikan CAPTCHA di jendela browser ({hint}), lalu tekan Enter ... ")
            page.wait_for_timeout(2000)

        raw_cookies = list(context.cookies())
        title = page.title()
        close()

    print(f"[*] Judul halaman: {title!r}")
    picked = _filter_site_cookies(raw_cookies, cfg)
    if not picked:
        print(
            f"[!] Cookie {cfg['cookie_names'] or '(apapun)'} tidak ditemukan. "
            "Situs mungkin masih menampilkan challenge — coba --headed.",
            file=sys.stderr,
        )
        print(f"[*] Cookie yang terlihat: {sorted(c.get('name', '?') for c in raw_cookies) or '(tidak ada)'}")
        return 1, {}

    print("\n--- tempel ke .env ---")
    collected = {}
    if site_key == "jobstreet":
        for k in ("JobseekerSessionId", "JobseekerVisitorId", "sol_id"):
            if k in picked:
                env_name = {
                    "JobseekerSessionId": "JOBSTREET_SESSION_ID",
                    "JobseekerVisitorId": "JOBSTREET_VISITOR_ID",
                    "sol_id": "JOBSTREET_SOL_VISITOR_ID",
                }[k]
                print(f"{env_name}={picked[k]}")
                collected[env_name] = picked[k]
    else:
        joined = "; ".join(f"{k}={v}" for k, v in picked.items())
        print(f"{cfg['env_key']}={joined}")
        collected[cfg["env_key"]] = joined
    print("---------------------\n")
    if any(k in picked for k in ("cf_clearance", "__cf_bm")):
        print(
            "[*] Catatan: cf_clearance kedaluwarsa dalam hitungan jam dan "
            "terikat IP egress. Panen dari mesin yang sama dengan server "
            "(atau via proxy yang sama), lalu restart backend. Ulangi panen "
            "saat log scraper mulai menunjukkan challenge/redirect login."
        )
    return 0, collected


def main() -> int:
    parser = argparse.ArgumentParser(description="Panen cookie sesi via Chromium asli.")
    parser.add_argument(
        "--site",
        choices=[*SITES, "all"],
        default="all",
        help="Situs target (default: all)",
    )
    parser.add_argument("--headed", action="store_true", help="Tampilkan jendela browser")
    parser.add_argument(
        "--channel",
        default=None,
        help='Channel browser, mis. "chrome" untuk Google Chrome asli '
        "(disarankan melawan Cloudflare; butuh Chrome terinstal).",
    )
    parser.add_argument(
        "--profile-dir",
        default=None,
        help="Direktori profil persisten (mis. ./sessions/chrome). "
        "Cookie/riwayat menumpuk antar panen sehingga sesi lebih dipercaya.",
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Tulis hasil langsung ke .env (backup lama ke .env.bak). "
        "Tanpa ini hanya dicetak untuk ditempel manual.",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Lokasi .env (default: .env di root repo).",
    )
    args = parser.parse_args()

    targets = list(SITES) if args.site == "all" else [args.site]
    code = 0
    collected = {}
    for key in targets:
        rc, values = harvest(key, SITES[key], args.headed, args.profile_dir, args.channel)
        code = max(code, rc)
        collected.update(values)

    if collected and args.write_env:
        env_path = Path(args.env_file) if args.env_file else (ROOT_DIR / ".env")
        backup = write_env_values(env_path, collected)
        print(f"[*] Ditulis ke {env_path}: {', '.join(sorted(collected))}")
        if backup:
            print(f"[*] Backup .env lama: {backup}")
        print("[*] Restart backend agar Settings baru terbaca (mis. `docker compose restart backend`).")
    elif collected:
        print("[*] Tip: tambah --write-env agar langsung ditulis ke .env tanpa tempel manual.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

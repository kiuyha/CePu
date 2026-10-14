"""Pemanen sesi browser untuk scraper (JALANKAN MANUAL, bukan di request path).

Membuka Chromium asli via Playwright ke situs target, menunggu Cloudflare/
cookie terbentuk, lalu mencetak baris .env siap tempel.

Butuh:  pip install playwright && playwright install chromium

Contoh:
    .venv/bin/python scripts/refresh_browser_sessions.py --site kredibel
    .venv/bin/python scripts/refresh_browser_sessions.py --site all --headed
    .venv/bin/python scripts/refresh_browser_sessions.py --site all \
        --headed --profile-dir ./sessions/chrome
Opsi --headed membuka browser terlihat (berguna kalau ada CAPTCHA yang
harus diselesaikan manual — selesaikan di jendela browser, lalu tekan
Enter di terminal). Opsi --profile-dir memakai profil persisten sehingga
kepercayaan situs menumpuk antar panen (disarankan untuk sesi awet).
"""
import argparse
import sys
from typing import Optional

SITES = {
    "kredibel": {
        "url": "https://www.kredibel.com/",
        "env_key": "KREDIBEL_SESSION_COOKIE",
        "cookie_names": ("kredibel_session",),
        "wait_ms": 6000,
    },
    "companyhouse": {
        "url": "https://companyhouse.id/",
        "env_key": "COMPANYHOUSE_SESSION_COOKIE",
        "cookie_names": (),
        "wait_ms": 6000,
    },
    "jobstreet": {
        "url": "https://id.jobstreet.com/",
        "env_key": "JOBSTREET_SESSION_ID",
        "cookie_names": ("JobseekerSessionId", "JobseekerVisitorId", "sol_id"),
        "wait_ms": 6000,
    },
}


def harvest(
    site_key: str, cfg: dict, headed: bool, profile_dir: Optional[str], channel: Optional[str]
) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright belum terinstal. Jalankan:\n"
            "  pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 2

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
            input(
                "[*] Selesaikan CAPTCHA di jendela browser (JANGAN login pakai akun "
                "pribadi — sesi anonim sudah cukup; login mengikat kuota & risiko "
                "flag ke akunmu), lalu tekan Enter ... "
            )
            page.wait_for_timeout(2000)

        cookies = {c["name"]: c["value"] for c in context.cookies()}
        title = page.title()
        close()

    print(f"[*] Judul halaman: {title!r}")
    names = cfg["cookie_names"]
    picked = {k: v for k, v in cookies.items() if not names or k in names}
    if not picked:
        print(
            f"[!] Cookie {names or '(apapun)'} tidak ditemukan. "
            "Situs mungkin masih menampilkan challenge — coba --headed.",
            file=sys.stderr,
        )
        print(f"[*] Cookie yang terlihat: {sorted(cookies) or '(tidak ada)'}")
        return 1

    print("\n--- tempel ke .env ---")
    if site_key == "jobstreet":
        for k in ("JobseekerSessionId", "JobseekerVisitorId", "sol_id"):
            if k in picked:
                env_name = {
                    "JobseekerSessionId": "JOBSTREET_SESSION_ID",
                    "JobseekerVisitorId": "JOBSTREET_VISITOR_ID",
                    "sol_id": "JOBSTREET_SOL_VISITOR_ID",
                }[k]
                print(f"{env_name}={picked[k]}")
    else:
        joined = "; ".join(f"{k}={v}" for k, v in picked.items())
        print(f"{cfg['env_key']}={joined}")
    print("---------------------\n")
    return 0


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
    args = parser.parse_args()

    targets = list(SITES) if args.site == "all" else [args.site]
    code = 0
    for key in targets:
        code = max(code, harvest(key, SITES[key], args.headed, args.profile_dir, args.channel))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

"""
Scraper modular untuk JobStreet (id.jobstreet.com) via GraphQL JobSearchV7.

Hanya dijalankan on-demand (tidak otomatis di pipeline deteksi):
- endpoint GET /v1/jobs/search (web), atau
- perintah "cari kerja <posisi>" di bot WhatsApp.

Session (session id, visitor id) dibaca dari Settings / .env,
mengikuti pola KredibelScraper: curl --http2 dulu, fallback httpx.
Tidak butuh cookie browser: cookie `JobseekerSessionId`/`JobseekerVisitorId`
dibangun otomatis dari session id di atas.
"""
import json
import logging
import shutil
import subprocess
import uuid
from typing import Any, Optional

from ..core.config import Settings, get_settings

from .anti_ban import throttle

logger = logging.getLogger(__name__)

GRAPHQL_PATH = "/graphql"

JOB_SEARCH_QUERY = """query JobSearchV7($params: JobSearchV7QueryInput!, $locale: Locale!, $zone: Zone!, $country: JobSearchV7Country!, $timezone: Timezone!, $tagsSubType: [JobSearchV7TagsSubType!]) {
  jobSearchV7(params: $params) {
    results {
      jobs {
        id
        title
        abstract
        adDisplay
        advertiser {
          id
          name
          __typename
        }
        organisation {
          id
          name
          companyProfileId
          companyProfileUrl
          companyProfileRelativeUrlToBeUsedWithZone
          __typename
        }
        categories {
          id
          label(locale: $locale)
          __typename
        }
        location {
          id
          countryCode
          displayName {
            text
            __typename
          }
          seoHierarchy {
            contextualName {
              text
              __typename
            }
            __typename
          }
          __typename
        }
        cjs {
          workTypes {
            sourceId
            name(locale: $locale)
            __typename
          }
          source {
            isAutoIncluded
            __typename
          }
          salary {
            hideSalary
            minimum
            maximum
            currency
            period
            displayValue
            __typename
          }
          roleTitles {
            shortId
            isDistinct
            __typename
          }
          product {
            branding {
              companyLogoURL
              __typename
            }
            bullets
            adType {
              sourceId
              __typename
            }
            __typename
          }
          externalReferences {
            id
            sourceSystem
            type
            metadata {
              name
              assets {
                profilePhotoUrl
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        listedAt {
          dateTimeUtc
          label(context: JOB_POSTED, length: SHORT, timezone: $timezone, locale: $locale)
          __typename
        }
        salary {
          period
          min
          max
          currency
          __typename
        }
        sol
        tags(subType: $tagsSubType) {
          type
          label(locale: $locale)
          __typename
        }
        url
        workArrangements {
          id
          label {
            lang
            text
            __typename
          }
          __typename
        }
        activity {
          visitedApplicationSite {
            count
            mostRecent {
              dateTimeUtc
              __typename
            }
            __typename
          }
          applicationEnds {
            count
            mostRecent {
              dateTimeUtc
              __typename
            }
            __typename
          }
          applicationStarts {
            count
            mostRecent {
              dateTimeUtc
              __typename
            }
            __typename
          }
          impressions {
            count
            mostRecent {
              dateTimeUtc
              __typename
            }
            __typename
          }
          jobDetails {
            count
            mostRecent {
              dateTimeUtc
              __typename
            }
            __typename
          }
          __typename
        }
        __typename
      }
      pagination {
        page
        pageSize
        resultCount
        __typename
      }
      __typename
    }
    enrichment {
      facets {
        categoryV1 {
          id
          label {
            lang
            text
            __typename
          }
          count
          __typename
        }
        distinctTitleV1 {
          id
          label
          count
          __typename
        }
        __typename
      }
      suggestions {
        queryParamLabelsV1 {
          text
          where {
            id
            kind
            label {
              lang
              text
              __typename
            }
            contextualName {
              lang
              text
              __typename
            }
            contextualNameLocalisations(siteKey: $country) {
              lang
              text
              __typename
            }
            isGranular
            defaultDistanceKms
            __typename
          }
          locationsHierarchy {
            id
            kind
            label {
              lang
              text
              __typename
            }
            contextualName {
              lang
              text
              __typename
            }
            isGranular
            defaultDistanceKms
            __typename
          }
          __typename
        }
        relatedSearchesV1 {
          totalJobs
          text
          __typename
        }
        organisationV1 {
          organisationId
          organisationName
          totalJobs
          __typename
        }
        locationV1 {
          local {
            sequence
            completions {
              id
              label(locale: $locale, zone: $zone, context: CONTEXTUAL_NAME, labelType: SHORT)
              __typename
            }
            __typename
          }
          international {
            sequence
            completions {
              id
              label(locale: $locale, zone: $zone, context: CONTEXTUAL_NAME, labelType: SHORT)
              __typename
            }
            __typename
          }
          __typename
        }
        sabFilterV1 {
          showSABFilter
          __typename
        }
        canonicalV1 {
          text
          where {
            id
            name
            __typename
          }
          __typename
        }
        spellingCorrectionV1 {
          type
          count
          searchToken
          label {
            lang
            defaultText
            __typename
          }
          intent {
            country
            locale
            text
            where
            whereId
            sort
            distanceKms
            filter {
              advertiserId
              categoryId
              listedAt
              organisationId
              organisationName
              salaryMin
              salaryMax
              tags
              workTypeId
              workArrangementId
              __typename
            }
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    context {
      searchToken
      filterNewSince
      representations {
        uiV1 {
          country
          locale
          text
          where
          whereId
          sort
          distanceKms
          filter {
            advertiserId
            categoryId
            categoryName
            listedAt
            organisationId
            organisationName
            salaryMin
            salaryMax
            tags
            workTypeId
            workArrangementId
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    metadata {
      flight
      request {
        correlationId
        __typename
      }
      sol
      __typename
    }
    __typename
  }
}"""


def build_payload(
    role: str,
    location_text: Optional[str] = None,
    distance_kms: int = 50,
    page: int = 1,
    page_size: int = 10,
    session_id: str = "",
    sol_visitor_id: str = "",
    country: str = "ID",
    locale: str = "en-ID",
    sort: str = "score",
) -> dict:
    """Susun body GraphQL untuk operasi JobSearchV7."""
    search_intent: dict[str, Any] = {
        "country": country,
        "locale": locale,
        "text": role,
        "distanceKms": distance_kms,
        "sort": sort,
    }
    if location_text:
        search_intent["where"] = location_text

    variables = {
        "params": {
            "searchIntent": search_intent,
            "searchContext": {
                "brand": "jobstreet",
                "channel": "web",
                "solVisitorId": sol_visitor_id,
                "intent": "SEARCH",
                "source": "FE_SERP",
            },
            "responseConfig": {
                "results": ["jobs"],
                "representations": ["uiV1"],
                "page": page,
                "pageSize": page_size,
                "enrichment": {
                    "suggestions": [
                        "locationV1",
                        "queryParamLabelsV1",
                        "sabFilterV1",
                        "organisationV1",
                        "spellingCorrectionV1",
                        "relatedSearchesV1",
                    ],
                    "relatedSearchesCount": 12,
                },
            },
            "sessionId": session_id,
        },
        "locale": locale,
        "zone": "asia-4",
        "timezone": "Asia/Jakarta",
        "country": country,
        "tagsSubType": ["VSAB"],
    }

    return {
        "operationName": "JobSearchV7",
        "variables": variables,
        "extensions": {
            "clientLibrary": {"name": "@apollo/client", "version": "4.2.9"},
        },
        "query": JOB_SEARCH_QUERY,
    }


def parse_jobs(response_json: dict) -> list[dict[str, Any]]:
    """Ubah response GraphQL menjadi list lowongan yang ringkas (siap tampil + link)."""
    try:
        jobs_raw = response_json["data"]["jobSearchV7"]["results"]["jobs"]
    except (KeyError, TypeError):
        logger.warning("JobStreet response tidak berisi daftar jobs.")
        return []
    if not isinstance(jobs_raw, list):
        return []

    jobs: list[dict[str, Any]] = []
    for job in jobs_raw:
        if not isinstance(job, dict):
            continue
        cjs = job.get("cjs") or {}
        salary_block = job.get("salary") or {}
        org = job.get("organisation") or {}
        advertiser = job.get("advertiser") or {}
        location = job.get("location") or {}
        display_name = (location.get("displayName") or {}).get("text")

        job_url = job.get("url")
        if not job_url and job.get("id"):
            job_url = f"https://id.jobstreet.com/job/{job['id']}"

        jobs.append(
            {
                "id": job.get("id"),
                "title": job.get("title"),
                "company": org.get("name") or advertiser.get("name"),
                "location": display_name,
                "salary_min": salary_block.get("min"),
                "salary_max": salary_block.get("max"),
                "salary_currency": salary_block.get("currency"),
                "salary_display": (cjs.get("salary") or {}).get("displayValue"),
                "work_type": ", ".join(
                    wt.get("name", "") for wt in (cjs.get("workTypes") or []) if isinstance(wt, dict)
                ),
                "listed_at": (job.get("listedAt") or {}).get("dateTimeUtc"),
                "listed_label": (job.get("listedAt") or {}).get("label"),
                "url": job_url,
            }
        )
    return jobs


class JobStreetScraper:
    """Client pencarian kerja JobStreet. Semua session diambil dari Settings/.env."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        # Kalau .env kosong, bangkitkan sekali per instance agar konsisten antar request.
        self.session_id = self.settings.jobstreet_session_id.strip() or str(uuid.uuid4())
        self.visitor_id = self.settings.jobstreet_visitor_id.strip() or self.session_id
        self.sol_visitor_id = self.settings.jobstreet_sol_visitor_id.strip() or self.session_id
        from .anti_ban import get_breaker

        self._breaker = get_breaker(
            "jobstreet",
            self.settings.scrape_circuit_threshold,
            self.settings.scrape_circuit_cooldown_seconds,
        )

    def _headers(self) -> dict[str, str]:
        user_agent = self.settings.jobstreet_user_agent.strip() or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
        )
        # WAJIB meniru header browser asli: tanpa sec-fetch-*/x-custom-features,
        # backend menjawab UNSTABLE_QUERY_ERROR walau query-nya valid.
        # Tidak ada secret di sini — semuanya statis, session tetap dari settings.
        return {
            "accept": "application/graphql-response+json,application/json;q=0.9",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://id.jobstreet.com",
            "referer": "https://id.jobstreet.com/",
            "sec-ch-ua": '"Brave";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "seek-request-brand": "jobstreet",
            "seek-request-country": "ID",
            "user-agent": user_agent,
            "x-custom-features": "application/features.seek.all+json",
            "x-seek-ec-sessionid": self.session_id,
            "x-seek-ec-visitorid": self.visitor_id,
            "x-seek-site": "chalice",
            # Cukup session id ini saja — tanpa cookie browser / cf_clearance.
            "cookie": f"JobseekerSessionId={self.session_id}; JobseekerVisitorId={self.visitor_id}",
        }

    def _endpoint(self) -> str:
        return f"{self.settings.jobstreet_base_url.rstrip('/')}{GRAPHQL_PATH}"

    def search_jobs(
        self,
        role: str,
        location_text: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> list[dict[str, Any]]:
        """Cari lowongan (blocking). Panggil via asyncio.to_thread dari kode async."""
        if not self._breaker.allow():
            logger.info("JobStreet di-skip (circuit terbuka).")
            return []
        throttle(
            "jobstreet",
            self.settings.scrape_min_interval_seconds,
            self.settings.scrape_jitter_seconds,
        )
        payload = build_payload(
            role=role,
            location_text=location_text,
            page=page,
            page_size=page_size,
            session_id=self.session_id,
            sol_visitor_id=self.sol_visitor_id,
        )
        logger.info("Mencari lowongan JobStreet: role=%r location=%r", role, location_text)

        curl_path = shutil.which("curl")
        if curl_path:
            raw = self._post_via_curl(payload, curl_path)
        else:
            raw = self._post_via_httpx(payload)
        if raw is None:
            return []
        return parse_jobs(raw)

    def _post_via_curl(self, payload: dict, curl_path: str) -> Optional[dict]:
        cmd = [curl_path, "-s", "--http2", "-X", "POST", self._endpoint()]
        proxy = (self.settings.jobstreet_proxy or "").strip()
        if proxy:
            cmd.extend(["-x", proxy])
        for key, value in self._headers().items():
            cmd.extend(["-H", f"{key}: {value}"])
        cmd.extend([
            "-d", json.dumps(payload),
            "--max-time", str(self.settings.jobstreet_timeout_seconds),
        ])
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.settings.jobstreet_timeout_seconds + 5,
            )
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning("JobStreet curl gagal: %s", exc)
            return None
        if res.returncode != 0:
            self._breaker.record_failure()
            logger.warning("JobStreet curl error: %s", res.stderr.strip()[:300])
            return None
        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError:
            self._breaker.record_failure()
            logger.warning("JobStreet response bukan JSON (kemungkinan diblokir).")
            return None
        if isinstance(data, dict) and data.get("errors"):
            from .anti_ban import classify_ban

            kind = classify_ban(graphql_errors=data["errors"])
            if kind in ("challenge", "blocked", "rate_limited", "server_error"):
                self._breaker.record_failure()
            else:
                self._breaker.record_success()
            logger.warning(
                "JobStreet GraphQL errors [%s]: %s", kind, str(data["errors"])[:300]
            )
        else:
            self._breaker.record_success()
        return data

    def _post_via_httpx(self, payload: dict) -> Optional[dict]:
        import httpx

        proxy = (self.settings.jobstreet_proxy or "").strip() or None
        try:
            with httpx.Client(
                http2=True, timeout=self.settings.jobstreet_timeout_seconds, proxy=proxy
            ) as client:
                resp = client.post(self._endpoint(), headers=self._headers(), json=payload)
                if resp.status_code != 200:
                    from .anti_ban import classify_ban

                    kind = classify_ban(status_code=resp.status_code)
                    if kind in ("challenge", "blocked", "rate_limited", "server_error"):
                        self._breaker.record_failure()
                    logger.warning("JobStreet HTTP %d [%s].", resp.status_code, kind)
                    return None
                self._breaker.record_success()
                return resp.json()
        except Exception as exc:
            self._breaker.record_failure()
            logger.warning("JobStreet httpx gagal: %s", exc)
            return None

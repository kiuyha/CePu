"""
Ekstraksi entitas dan preprocessing teks persis sesuai Modelling_PKM_AMLI.ipynb.
Mendukung regex standar & EMSCAD, pembersihan artefak/hoaks/emoji,
ekstraksi perusahaan via NER + heuristik, dan masking [PERUSAHAAN], [URL], [EMAIL], [NOMOR_HP].
"""
import html
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Standard & EMSCAD Regex Patterns (sesuai Cell 2 notebook)
URL_PAT = r'https?://\S+|www\.\S+'
EMAIL_PAT = r'[\w\.-]+@[\w\.-]+\.\w+'
PHONE_PAT = r'(?:\+?62|0)8[1-9](?:[\s-]?\d){7,11}\b'

EMSCAD_EMAIL_HASH = r'#EMAIL_[a-f0-9]+#'
EMSCAD_PHONE_HASH = r'#PHONE_[a-f0-9]+#'
EMSCAD_URL_HASH   = r'#URL_[a-f0-9]+#'

STANDARD_URL_PAT   = r'https?://\S+|www\.\S+'
STANDARD_EMAIL_PAT = r'[\w\.-]+@[\w\.-]+\.\w+'
STANDARD_PHONE_PAT = r'(?:\+?\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}\b|(?:\+?62|0)8[1-9](?:[\s-]?\d){7,11}\b'

# Heuristic company regex matching notebook Cell 8:
# r'\b(?:PT|CV|Perum|UD|Firma|Yayasan)\b\.?\s+[A-Z][a-zA-Z0-9\.\s]+'
# We bound the title casing tokens so it doesn't greedily eat entire lowercased sentence clauses like "untuk posisi admin"
COMPANY_HEURISTIC_BOUNDED = r'\b(?:PT|CV|Perum|UD|Firma|Yayasan)\b\.?\s+([A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*){0,4})'
COMPANY_HEURISTIC = r'\b(?:PT|CV|Perum|UD|Firma|Yayasan)\b\.?\s+[A-Z][a-zA-Z0-9\.\s]+'

HOAX_NARRATIVE_PATTERNS = [
    r'cek fakta', r'periksa fakta', r'turnbackhoax', r'mafindo',
    r'hoaks', r'hoax', r'disinformasi', r'misinformasi',
    r'diduga', r'postingan(?: foto| video)?', r'unggahan', r'tangkapan layar',
    r'akun (?:facebook|instagram|tiktok|media sosial)', r'beredar(?: sebuah| di media sosial)?',
    r'klaim(?:nya)?', r'narasi(?:nya)?', r'menurut penelusuran', r'faktanya',
    r'#\w+'
]
HOAX_NARRATIVE_RE = re.compile('|'.join(HOAX_NARRATIVE_PATTERNS), re.IGNORECASE)
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]+",
    flags=re.UNICODE
)


def strip_source_artifacts(text: str) -> str:
    """Removes hashtags, emoji, and fact-checking/hoax-narrative boilerplate that leak
    which site the text was collected from rather than describing the job offer itself."""
    text = EMOJI_RE.sub(' ', text)
    text = HOAX_NARRATIVE_RE.sub(' ', text)
    return text


def mask_and_extract_companies(
    text: str,
    ner_entities: Optional[list[dict]] = None
) -> tuple[str, list[str]]:
    """
    Ekstraksi entitas organisasi/perusahaan dan masking ke [PERUSAHAAN].
    Memakai hasil NER jika tersedia, dikombinasikan dengan regex heuristik formal.
    """
    if not isinstance(text, str) or not text.strip():
        return "", []

    target_tags = {'ORGANIZATION', 'POLITICAL_ORGANIZATION', 'ORG'}
    extracted_orgs = []

    if ner_entities:
        org_entities = [e for e in ner_entities if e.get('entity_group') in target_tags]
        for e in org_entities:
            org_str = text[e['start']:e['end']].strip()
            if org_str:
                extracted_orgs.append(org_str)

        org_entities.sort(key=lambda x: x['start'], reverse=True)
        masked_text = text
        for entity in org_entities:
            start = entity['start']
            end = entity['end']
            masked_text = masked_text[:start] + ' [PERUSAHAAN] ' + masked_text[end:]
    else:
        masked_text = text

    # Heuristic company mentions (PT, CV, Perum, UD, etc.) bounded
    heuristic_companies = []
    for m in re.finditer(COMPANY_HEURISTIC_BOUNDED, text):
        full = m.group(0).strip()
        if full:
            heuristic_companies.append(full)

    unique_orgs = list(dict.fromkeys(heuristic_companies + extracted_orgs))

    # Mask heuristic companies in text
    masked_text = re.sub(COMPANY_HEURISTIC_BOUNDED, ' [PERUSAHAAN] ', masked_text)

    return masked_text, unique_orgs


def process_job_text(
    text: str,
    ner_entities: Optional[list[dict]] = None
) -> dict:
    """
    Pipeline pembersihan & ekstraksi entitas lengkap persis seperti process_scraped_text
    dan process_emscad_text di notebook.
    """
    if not isinstance(text, str) or not text.strip():
        return {
            "text_clean_no_contact": "",
            "text_clean_with_contact": "",
            "extracted_emails": [],
            "extracted_phones": [],
            "extracted_urls": [],
            "extracted_companies": []
        }

    clean = html.unescape(text)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = strip_source_artifacts(clean)

    # Standard + EMSCAD URLs
    emscad_urls = re.findall(EMSCAD_URL_HASH, clean, re.IGNORECASE)
    std_urls = re.findall(STANDARD_URL_PAT, clean)
    urls = list(dict.fromkeys(emscad_urls + std_urls))

    # Standard + EMSCAD Emails (deduped case-insensitively)
    emscad_emails = re.findall(EMSCAD_EMAIL_HASH, clean, re.IGNORECASE)
    std_emails = re.findall(STANDARD_EMAIL_PAT, clean)
    seen_emails = set()
    emails = []
    for em in (emscad_emails + std_emails):
        lowered = em.lower()
        if lowered not in seen_emails:
            seen_emails.add(lowered)
            emails.append(em)

    # Standard + EMSCAD Phones (clean spacing/dashes while keeping leading + if present)
    emscad_phones = re.findall(EMSCAD_PHONE_HASH, clean, re.IGNORECASE)
    raw_phones = re.findall(STANDARD_PHONE_PAT, clean)
    std_phones = []
    for p in raw_phones:
        has_plus = p.strip().startswith("+")
        cleaned_digits = re.sub(r'[\s-]', '', p)
        if has_plus and not cleaned_digits.startswith("+"):
            cleaned_digits = "+" + cleaned_digits
        std_phones.append(cleaned_digits)

    phones = list(dict.fromkeys(emscad_phones + std_phones))

    # Masking
    masked = clean
    masked = re.sub(EMSCAD_URL_HASH, ' [URL] ', masked, flags=re.IGNORECASE)
    masked = re.sub(STANDARD_URL_PAT, ' [URL] ', masked)
    masked = re.sub(EMSCAD_EMAIL_HASH, ' [EMAIL] ', masked, flags=re.IGNORECASE)
    masked = re.sub(STANDARD_EMAIL_PAT, ' [EMAIL] ', masked)
    masked = re.sub(EMSCAD_PHONE_HASH, ' [NOMOR_HP] ', masked, flags=re.IGNORECASE)
    masked = re.sub(STANDARD_PHONE_PAT, ' [NOMOR_HP] ', masked)

    masked, companies = mask_and_extract_companies(masked, ner_entities=ner_entities)

    no_contact = re.sub(r'\s+', ' ', masked).strip()
    with_contact = re.sub(r'\s+', ' ', clean).strip()

    return {
        "text_clean_no_contact": no_contact,
        "text_clean_with_contact": with_contact,
        "extracted_emails": emails,
        "extracted_phones": phones,
        "extracted_urls": urls,
        "extracted_companies": companies
    }


def extract_entities_and_features(
    text_no_contact: str,
    emails: Optional[list] = None,
    phones: Optional[list] = None,
    urls: Optional[list] = None,
    companies: Optional[list] = None
) -> dict:
    """
    Fitur tambahan dan penyusunan alasan linguistik sesuai Cell 8 notebook.
    """
    cleaned = text_no_contact if isinstance(text_no_contact, str) else ""

    emails = [e.strip() for e in (emails or []) if e and e.strip()]
    phones = [p.strip() for p in (phones or []) if p and p.strip()]
    urls = [u.strip() for u in (urls or []) if u and u.strip()]

    heuristic_companies = []
    for m in re.finditer(COMPANY_HEURISTIC_BOUNDED, cleaned):
        full = m.group(0).strip()
        if full:
            heuristic_companies.append(full)

    ner_companies = [c.strip() for c in (companies or []) if c and c.strip()]
    companies_all = list(dict.fromkeys(heuristic_companies + ner_companies))

    suspicious_keywords = ["transfer", "administrasi", "gaji tinggi tanpa syarat", "biaya pendaftaran", "hubungi wa"]
    lower_text = cleaned.lower()
    keyword_counts = {kw: lower_text.count(kw) for kw in suspicious_keywords}
    suspicious_keyword_total = sum(keyword_counts.values())

    digit_count = sum(c.isdigit() for c in cleaned)
    special_char_ratio = sum(not c.isalnum() and not c.isspace() for c in cleaned) / (len(cleaned) + 1e-5)
    text_length = len(cleaned)

    reasons = []
    if suspicious_keyword_total > 0:
        found_kws = [k for k, v in keyword_counts.items() if v > 0]
        reasons.append(f"Terdapat kata kunci mencurigakan: {', '.join(found_kws)}")
    if digit_count > 15:
        reasons.append("Frekuensi karakter angka tinggi (potensi nomor rekening/kontak tak resmi)")
    if special_char_ratio > 0.08:
        reasons.append("Rasio karakter khusus melebihi batas wajar")

    return {
        "extracted_phones": phones,
        "extracted_emails": emails,
        "extracted_urls": urls,
        "extracted_companies": companies_all,
        "text_length": text_length,
        "digit_count": digit_count,
        "special_char_ratio": special_char_ratio,
        "suspicious_keyword_count": suspicious_keyword_total,
        "num_emails": len(emails),
        "num_phones": len(phones),
        "num_urls": len(urls),
        "has_contact_info": int(bool(emails or phones or urls)),
        "reasons": reasons
    }


@dataclass
class ExtractedEntities:
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    company_source: str = "ner_and_heuristic"


def extract_phones(text: str) -> list[str]:
    processed = process_job_text(text)
    return processed["extracted_phones"]


def extract_emails(text: str) -> list[str]:
    processed = process_job_text(text)
    return processed["extracted_emails"]


def extract_companies(text: str) -> list[str]:
    processed = process_job_text(text)
    return processed["extracted_companies"]


def extract_entities(text: str, ner_entities: Optional[list[dict]] = None) -> ExtractedEntities:
    if not text:
        return ExtractedEntities()

    processed = process_job_text(text, ner_entities=ner_entities)
    return ExtractedEntities(
        phones=processed["extracted_phones"],
        emails=processed["extracted_emails"],
        companies=processed["extracted_companies"],
        company_source="ner_and_heuristic" if ner_entities else "heuristic_prefix",
    )



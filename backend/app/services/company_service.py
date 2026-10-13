"""
Global Commercial Registry & Company Screening Service
======================================================
Collects a person's worldwide company affiliations and board memberships from
several official/public sources in parallel.

Source hierarchy (most trustworthy first):
  1. OpenCorporates API  — 140+ countries, 200M+ company records (widest open data)
  2. SEC EDGAR (US)      — US public company officers and shareholders
  3. Companies House (UK)— UK company director search API
  4. KAP.org.tr (TR)     — Turkish public companies (regulated by the CMB)
  5. Ticaret Sicili (TR) — Turkish official gazette archive
  6. Web Search          — Yahoo + multilingual query variants for global coverage

NOTE: sources such as MERSIS, TOBB, Europages and D&B sit behind JS-dependent
      interfaces, so for now they are only reached indirectly through web search.
      A Playwright integration could cover them later.
"""

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from app.utils.logger import logger

# ─── Data Model ───────────────────────────────────────────────────────────────


@dataclass
class CompanyRecord:
    """
    A single company record, kept together with the person's relation to it,
    its source, a confidence score and a risk profile.
    """

    company_name: str
    company_type: str = "Unknown"
    role: str = "Unknown"
    role_category: str = "unknown"  # founder | executive | board_member | shareholder | unknown
    status: str = "unknown"  # active | passive | liquidated | unknown
    source_url: str = ""
    source_name: str = ""
    country: str | None = None  # Country the company is registered in
    confidence: float = 0.5  # 0.0-1.0; from source authority + context richness
    registry_id: str | None = None  # OpenCorporates id, MERSIS, Company No, CIK, etc.
    city: str | None = None
    sector: str | None = None
    risk_flags: list = field(default_factory=list)
    snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "company_name": self.company_name,
            "company_type": self.company_type,
            "role": self.role,
            "role_category": self.role_category,
            "status": self.status,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "country": self.country,
            "confidence": round(self.confidence, 2),
            "registry_id": self.registry_id,
            "city": self.city,
            "sector": self.sector,
            "risk_flags": self.risk_flags,
            "snippet": self.snippet[:300] if self.snippet else "",
        }


# ─── Constants ────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Global company suffix patterns ──────────────────────────────────────────
# The most common legal forms: English, German, French, Spanish,
# Italian, Dutch, Portuguese and Turkish.
COMPANY_SUFFIX_RE = re.compile(
    r"\b((?:[A-ZÇÖŞİĞÜÀ-Ÿ][A-Za-zÀ-ÿÇçÖöŞşİiĞğÜü0-9&\-\.]{1,30}\s*){1,6})"
    r"(?:"
    # Anglosakson
    r"Inc\.|Inc\b|Corp\.|Corp\b|LLC\b|L\.L\.C\.|Ltd\.|Ltd\b|"
    r"PLC\b|P\.L\.C\.|LLP\b|LP\b|L\.P\.|PLLC\b|"
    # German / Swiss / Austrian
    r"GmbH\b|AG\b|KG\b|OHG\b|UG\b|SE\b|"
    # French / Belgian / Swiss
    r"S\.A\.\b|SA\b|S\.A\.R\.L\.\b|SARL\b|SAS\b|S\.A\.S\.\b|"
    r"EURL\b|SCI\b|SNC\b|"
    # Spanish / Portuguese
    r"S\.L\.\b|SL\b|S\.R\.L\.\b|SRL\b|S\.A\. de C\.V\.\b|"
    # Italian
    r"S\.p\.A\.\b|SpA\b|S\.r\.l\.\b|Srl\b|"
    # Dutch / Belgian
    r"B\.V\.\b|BV\b|N\.V\.\b|NV\b|"
    # Scandinavian
    r"AB\b|A/S\b|ApS\b|Oy\b|"
    # Turkish
    r"A\.Ş\.\b|AŞ\b|Ltd\. Şti\.\b|LTD\.ŞTİ\.\b|Holding\b|HOLDİNG\b|"
    r"Grubu\b|GRUP\b|Şirketi\b"
    r")",
    re.UNICODE,
)

# Legal-form lookup table (ordered by precedence - longer suffixes first)
COMPANY_TYPE_MAP = [
    ("Ltd. Şti.", "Limited Şirket (TR)"),
    ("LTD.ŞTİ.", "Limited Şirket (TR)"),
    ("A.Ş.", "Anonim Şirket (TR)"),
    ("Holding", "Holding"),
    ("HOLDİNG", "Holding"),
    ("S.A. de C.V.", "Sociedad Anónima (MX)"),
    ("S.p.A.", "Società per Azioni (IT)"),
    ("S.r.l.", "Società a responsabilità limitata (IT)"),
    ("S.A.R.L.", "Société à responsabilité limitée (FR)"),
    ("S.A.", "Société Anonyme / S.A."),
    ("GmbH", "Gesellschaft mit beschränkter Haftung (DE)"),
    ("B.V.", "Besloten Vennootschap (NL)"),
    ("N.V.", "Naamloze Vennootschap (NL)"),
    ("P.L.C.", "Public Limited Company (UK)"),
    ("PLC", "Public Limited Company (UK)"),
    ("L.L.C.", "Limited Liability Company (US)"),
    ("LLC", "Limited Liability Company (US)"),
    ("Inc.", "Incorporated (US/CA)"),
    ("Inc", "Incorporated (US/CA)"),
    ("Corp.", "Corporation (US/CA)"),
    ("Corp", "Corporation (US/CA)"),
    ("Ltd.", "Limited Company"),
    ("Ltd", "Limited Company"),
    ("LLP", "Limited Liability Partnership"),
    ("AG", "Aktiengesellschaft (DE/CH/AT)"),
    ("AB", "Aktiebolag (SE)"),
    ("A/S", "Aktieselskab (DK/NO)"),
    ("ApS", "Anpartsselskab (DK)"),
    ("Oy", "Osakeyhtiö (FI)"),
    ("SE", "Societas Europaea (EU)"),
    ("KG", "Kommanditgesellschaft (DE)"),
    ("SAS", "Société par Actions Simplifiée (FR)"),
    ("SRL", "Sociedad de Responsabilidad Limitada"),
    ("Grubu", "Grup / Group (TR)"),
    ("GRUP", "Grup / Group (TR)"),
    ("Şirketi", "Şirket (TR)"),
]

# ── Role patterns (multilingual) ────────────────────────────────────────────
ROLE_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "founder": [
        (r"\b(co[- ]?founder|founder|founding\s*partner)\b", "Co-Founder / Founder"),
        (r"\b(kurucu\s*ortak|kurucu)\b", "Kurucu / Ortak (TR)"),
        (r"\b(gründer|mitgründer)\b", "Gründer (DE)"),
        (r"\b(fondateur|co-fondateur)\b", "Fondateur (FR)"),
        (r"\b(fundador|cofundador)\b", "Fundador (ES)"),
        (r"\bmüteşebbis\b", "Müteşebbis (TR)"),
    ],
    "executive": [
        (r"\bchief\s*executive\s*officer\b|\bceo\b", "CEO"),
        (r"\bchief\s*financial\s*officer\b|\bcfo\b", "CFO"),
        (r"\bchief\s*operating\s*officer\b|\bcoo\b", "COO"),
        (r"\bchief\s*technology\s*officer\b|\bcto\b", "CTO"),
        (r"\bmanaging\s*director\b|\bmd\b", "Managing Director"),
        (r"\bgeneral\s*manager\b", "General Manager"),
        (r"\bpresident\b", "President"),
        (r"\bchairman\b|\bchairperson\b", "Chairman"),
        (r"\bgeschäftsführer\b", "Geschäftsführer (DE)"),
        (r"\bgerant\b|\bprésident[-\s]directeur\b|\bpdg\b", "Gérant / PDG (FR)"),
        (r"\bgenel\s*müdür\b", "Genel Müdür (TR)"),
        (r"\byönetim\s*kurulu\s*başkan[ıi]\b", "YK Başkanı (TR)"),
        (r"\bmurahhas\s*aza\b", "Murahhas Aza (TR)"),
        (r"\byönetici\b|\bdirektör\b", "Yönetici / Direktör (TR)"),
        (r"\badministrateur\s*délégué\b", "Administrateur Délégué (FR/BE)"),
        (r"\badministrador\s*único\b", "Administrador Único (ES)"),
    ],
    "board_member": [
        (r"\bboard\s*(of\s*directors?\s*)?member\b|\bdirector\b", "Director / Board Member"),
        (r"\bnon[- ]?executive\s*director\b", "Non-Executive Director"),
        (r"\bindependent\s*director\b", "Independent Director"),
        (r"\bsupervisory\s*board\b|\baufsichtsrat\b", "Supervisory Board (DE)"),
        (r"\byönetim\s*kurulu\s*üye\b|\byk\s*üye\b", "YK Üyesi (TR)"),
        (r"\bdenetim\s*kurulu\b", "Denetim Kurulu Üyesi (TR)"),
        (r"\badministrateur\b", "Administrateur (FR)"),
        (r"\bconsejero\b", "Consejero (ES)"),
        (r"\bamministratore\b", "Amministratore (IT)"),
        (r"\bcommissario\b", "Commissario (IT)"),
    ],
    "shareholder": [
        (r"\bshareholder\b|\bstockholder\b", "Shareholder"),
        (r"\bbeneficial\s*owner\b", "Beneficial Owner"),
        (r"\bmajority\s*owner\b|\bminority\s*owner\b", "Owner"),
        (r"\bprincipal\s*shareholder\b", "Principal Shareholder"),
        (r"\bhissedar\b|\bpay\s*sahibi\b|\bsermayedar\b", "Hissedar / Pay Sahibi (TR)"),
        (r"\bortak\b", "Ortak (TR)"),
        (r"\bactionnaire\b", "Actionnaire (FR)"),
        (r"\bgesellschafter\b", "Gesellschafter (DE)"),
        (r"\baccionista\b", "Accionista (ES)"),
        (r"\bazionista\b", "Azionista (IT)"),
    ],
}

STATUS_PATTERNS = {
    "liquidated": [
        r"\b(liquidat|dissolv|wound\s*up|struck\s*off|winding\s*up)\b",
        r"\b(tasfiye|iflas|konkordato|kapatıl|feshedil|kapandı)\b",
        r"\b(aufgelöst|insolvent|liquidation)\b",
        r"\b(en\s*liquidation|radié|dissous)\b",
        r"\b(liquidazione|fallimento|cancellata)\b",
    ],
    "passive": [
        r"\b(dormant|inactive|dissolved|non[- ]?trading)\b",
        r"\b(pasif|faaliyetsiz|faal\s*değil)\b",
        r"\b(ruhend|inaktiv)\b",
    ],
    "active": [
        r"\b(active|trading|operating|incorporated)\b",
        r"\b(aktif|faal[^i]|faaliyet\s*göster)\b",
        r"\b(aktiv|in\s*betrieb)\b",
        r"\b(en\s*activité|actif)\b",
    ],
}

# Risk signals - they warn the researcher, they do not convict the company
RISK_PATTERNS = {
    "offshore": [
        r"\b(bvi|british\s*virgin\s*islands|cayman|bermuda|jersey|guernsey|"
        r"isle\s*of\s*man|malta|cyprus|kıbrıs|bahamas|panama|seychelles|"
        r"mauritius|samoa|vanuatu|liechtenstein|andorra|monaco|offshore|"
        r"tax\s*haven|vergi\s*cenneti)\b",
    ],
    "shell_company": [
        r"\b(shell\s*company|paravan\s*şirket|nominee|front\s*company|"
        r"mailbox\s*company|letterbox\s*company|sanal\s*ofis)\b",
    ],
    "liquidated": [r"\b(liquidat|iflas|tasfiye|konkordato|insolvent)\b"],
    "pep_related": [
        r"\b(politician|siyasetçi|minister|bakan|senator|"
        r"congress|parliament|meclis|deputy|milletvekili)\b"
    ],
    "sanction": [r"\b(sanctioned|sanction|embargo|ofac|eu\s*list|yaptırım)\b"],
    "high_risk_sector": [
        r"\b(gambling|casino|cryptocurrency\s*exchange|"
        r"arms|weapons|narco|kumar|silah)\b"
    ],
}

# ── Industry detection (global) ─────────────────────────────────────────────
SECTOR_PATTERNS = {
    "Technology": r"\b(technology|tech|software|it\b|digital|cyber|cloud|ai\b|"
    r"saas|fintech|yazılım|bilişim|teknoloji)\b",
    "Real Estate": r"\b(real\s*estate|property|gayrimenkul|emlak|reit|immobili)\b",
    "Construction": r"\b(construction|building|infrastructure|inşaat|yapı|müteahhit)\b",
    "Energy": r"\b(energy|oil|gas|solar|wind|renewable|enerji|petrol|doğalgaz)\b",
    "Finance": r"\b(finance|financial|investment|banking|insurance|fund|hedge|"
    r"private\s*equity|finans|yatırım|sigorta|banka|portföy)\b",
    "Healthcare": r"\b(health|medical|pharma|hospital|clinic|biotech|"
    r"sağlık|hastane|ilaç|medikal)\b",
    "Mining": r"\b(mining|mineral|gold|copper|coal|maden|madencilik)\b",
    "Media": r"\b(media|publishing|broadcasting|press|news|"
    r"medya|yayın|gazete|basın)\b",
    "Tourism": r"\b(tourism|hotel|hospitality|travel|resort|"
    r"turizm|otel|seyahat)\b",
    "Logistics": r"\b(logistics|shipping|freight|transport|supply\s*chain|"
    r"lojistik|nakliye|kargo)\b",
    "Retail": r"\b(retail|e[- ]?commerce|marketplace|consumer|"
    r"perakende|e[- ]ticaret|market)\b",
    "Food & Beverage": r"\b(food|beverage|restaurant|agriculture|gıda|tarım|restoran)\b",
    "Education": r"\b(education|university|academy|training|eğitim|üniversite|kurs)\b",
    "Legal": r"\b(law\s*firm|legal|attorney|barrister|solicitor|hukuk|avukat)\b",
    "Defense": r"\b(defense|defence|aerospace|military|savunma|havacılık)\b",
}


# ─── Service ──────────────────────────────────────────────────────────────────


class CompanyScraperService:
    """
    Global company screening service.

    Collects the companies tied to a person from 6 sources concurrently:
    OpenCorporates, SEC EDGAR, Companies House, KAP, Ticaret Sicili and web search.

    Design decisions:
      - ThreadPoolExecutor: IO-bound scraping; consistent with the other services.
      - Multilingual role/suffix detection: TR, EN, DE, FR, ES, IT, NL, PT, Nordic.
      - Dynamic confidence: source authority + context quality feed the score.
      - Risk flags: in line with OSINT ethics - a warning, never an accusation.
      - Deduplication: the same company seen from N sources is merged, its
        confidence raised, and no information is dropped.
    """

    OPENCORPORATES_SEARCH = "https://api.opencorporates.com/v0.4/officers/search"
    SEC_EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
    COMPANIES_HOUSE_SEARCH = "https://find-and-update.company-information.service.gov.uk/search/officers"
    KAP_SEARCH = "https://www.kap.org.tr/tr/arama"
    TICARET_SICIL_SEARCH = "https://www.ticaretsiciilgazetesi.gtb.gov.tr/arama"

    def __init__(self, timeout: int = 12):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout

    # ── Public API ────────────────────────────────────────────────────────────

    def search_companies(self, name: str) -> list[dict]:
        """
        Collect the person's global company affiliations from every source.

        Args:
            name: Full name to search for (e.g. "Elon Musk", "Ahmet Yilmaz")

        Returns:
            A list of dicts sorted by confidence score, descending.
        """
        logger.log_action("CompanyService: global company screening started", target=name)
        records: list[CompanyRecord] = []

        tasks = {
            "OpenCorporates": lambda: self._search_opencorporates(name),
            "SEC EDGAR (US)": lambda: self._search_sec_edgar(name),
            "Companies House (UK)": lambda: self._search_companies_house(name),
            "Wikidata": lambda: self._search_wikidata(name),
            "KAP (TR)": lambda: self._search_kap(name),
            "Ticaret Sicili (TR)": lambda: self._search_ticaret_sicil(name),
            "Web Search": lambda: self._search_via_web(name),
        }

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fn): label for label, fn in tasks.items()}
            for future in as_completed(futures):
                label = futures[future]
                try:
                    results = future.result(timeout=self.timeout + 8)
                    records.extend(results)
                    logger.log_action(f"CompanyService {label}: {len(results)} record(s)")
                except Exception as exc:
                    logger.log_warning(f"[CompanyService] {label} failed (non-critical): {exc}")

        merged = self._deduplicate(records)
        merged.sort(key=lambda r: r.confidence, reverse=True)

        if len(merged) >= 5:
            logger.log_thought(f"[CompanyService] {len(merged)} companies - this may be a complex network")

        logger.log_success(f"[CompanyService] {len(merged)} unique companies in total")
        return [r.to_dict() for r in merged]

    # ── OpenCorporates ────────────────────────────────────────────────────────

    def _search_opencorporates(self, name: str) -> list[CompanyRecord]:
        """
        OpenCorporates officer/director search API.
        140+ countries, 200M+ records - the widest open company database.

        Limitation: the free API caps pagination, so only the first 20 results
        are pulled (enough when the name is distinctive).
        """
        records: list[CompanyRecord] = []
        try:
            from app.config import get_settings

            params = {"q": name, "per_page": 20}
            token = get_settings().opencorporates_api_token
            if token:
                params["api_token"] = token

            resp = self.session.get(
                self.OPENCORPORATES_SEARCH,
                params=params,
                timeout=self.timeout,
            )
            # 401/403 → no API token configured; skip silently (other sources cover this)
            if resp.status_code in (401, 403):
                logger.log_thought(
                    "[CompanyService/OpenCorporates] API token required (401/403) - "
                    "falling back to the other sources (SEC/Companies House/web)."
                )
                return records
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("results", {}).get("officers", []):
                officer = item.get("officer", {})
                company = officer.get("company", {}) or {}

                company_name = company.get("name") or officer.get("company_name", "")
                if not company_name:
                    continue

                role_raw = officer.get("position", "")
                role_label, role_cat = self._classify_role_from_text(role_raw)
                if role_label == "Unknown" and role_raw:
                    role_label = role_raw.title()

                status_raw = company.get("current_status", "unknown")
                status = self._map_oc_status(status_raw)

                jurisdiction = company.get("jurisdiction_code", "")
                country = self._jurisdiction_to_country(jurisdiction)

                company_url = (
                    f"https://opencorporates.com{company.get('opencorporates_url', '')}"
                    if company.get("opencorporates_url")
                    else ""
                )

                records.append(
                    CompanyRecord(
                        company_name=company_name,
                        company_type=self._extract_company_type(company_name),
                        role=role_label,
                        role_category=role_cat,
                        status=status,
                        source_url=company_url,
                        source_name="OpenCorporates",
                        country=country,
                        confidence=0.88,  # Structured API data = high confidence
                        registry_id=company.get("company_number"),
                        risk_flags=self._detect_risks(company_name + " " + (country or "")),
                        snippet=(
                            f"{role_label} at {company_name} ({country or jurisdiction})"
                            if country or jurisdiction
                            else f"{role_label} at {company_name}"
                        ),
                    )
                )

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/OpenCorporates] failed: {exc}")

        return records

    def _map_oc_status(self, status: str) -> str:
        s = (status or "").lower()
        if any(k in s for k in ("active", "registered", "incorporated")):
            return "active"
        if any(k in s for k in ("dissolved", "liquidat", "struck", "wound")):
            return "liquidated"
        if any(k in s for k in ("dormant", "inactive")):
            return "passive"
        return "unknown"

    def _jurisdiction_to_country(self, code: str) -> str | None:
        """Translate an OpenCorporates jurisdiction code into a readable country name."""
        mapping = {
            "us": "USA",
            "gb": "United Kingdom",
            "de": "Germany",
            "fr": "France",
            "nl": "Netherlands",
            "ch": "Switzerland",
            "au": "Australia",
            "ca": "Canada",
            "jp": "Japan",
            "cn": "China",
            "sg": "Singapore",
            "ie": "Ireland",
            "lu": "Luxembourg",
            "cy": "Cyprus",
            "mt": "Malta",
            "ky": "Cayman Islands",
            "bvi": "British Virgin Islands",
            "tr": "Turkey",
            "ae": "UAE",
            "ru": "Russia",
            "se": "Sweden",
            "dk": "Denmark",
            "fi": "Finland",
            "no": "Norway",
            "it": "Italy",
            "es": "Spain",
            "pt": "Portugal",
            "be": "Belgium",
            "at": "Austria",
            "br": "Brazil",
            "mx": "Mexico",
            "in": "India",
            "hk": "Hong Kong",
            "za": "South Africa",
        }
        base = code.split("_")[0].lower() if code else ""
        return mapping.get(base)

    # ── Wikidata (global, keyless) ────────────────────────────────────────────

    def _search_wikidata(self, name: str) -> list[CompanyRecord]:
        """
        Wikidata public knowledge graph — links notable people to organizations
        via employer (P108) and member-of (P463). Fully public, keyless.
        """
        records: list[CompanyRecord] = []
        api = "https://www.wikidata.org/w/api.php"
        try:
            # 1) Resolve the person to a QID
            sr = self.session.get(
                api,
                params={
                    "action": "wbsearchentities",
                    "search": name,
                    "language": "en",
                    "format": "json",
                    "type": "item",
                    "limit": 1,
                },
                timeout=self.timeout,
            )
            sr.raise_for_status()
            hits = sr.json().get("search", [])
            if not hits:
                return records
            qid = hits[0].get("id")
            if not qid:
                return records

            # 2) Fetch the person's claims
            cr = self.session.get(
                api,
                params={
                    "action": "wbgetentities",
                    "ids": qid,
                    "props": "claims",
                    "format": "json",
                },
                timeout=self.timeout,
            )
            cr.raise_for_status()
            claims = cr.json().get("entities", {}).get(qid, {}).get("claims", {})

            org_qids: list[str] = []
            for prop in ("P108", "P463"):  # employer, member of
                for snak in claims.get(prop, []):
                    try:
                        oid = snak["mainsnak"]["datavalue"]["value"]["id"]
                        if oid not in org_qids:
                            org_qids.append(oid)
                    except (KeyError, TypeError):
                        continue
            org_qids = org_qids[:8]
            if not org_qids:
                return records

            # 3) Batch-resolve organization labels
            lr = self.session.get(
                api,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(org_qids),
                    "props": "labels",
                    "languages": "en",
                    "format": "json",
                },
                timeout=self.timeout,
            )
            lr.raise_for_status()
            entities = lr.json().get("entities", {})

            person_url = f"https://www.wikidata.org/wiki/{qid}"
            for oid in org_qids:
                label = entities.get(oid, {}).get("labels", {}).get("en", {}).get("value")
                if not label:
                    continue
                records.append(
                    CompanyRecord(
                        company_name=label,
                        company_type=self._extract_company_type(label),
                        role="Affiliation (employer / member)",
                        role_category="unknown",
                        status="unknown",
                        source_url=person_url,
                        source_name="Wikidata",
                        confidence=0.68,
                        registry_id=oid,
                        risk_flags=self._detect_risks(label),
                        snippet=f"{name} linked to {label} via Wikidata ({qid}).",
                    )
                )
        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/Wikidata] failed: {exc}")
        return records

    # ── SEC EDGAR (USA) ───────────────────────────────────────────────────────

    def _search_sec_edgar(self, name: str) -> list[CompanyRecord]:
        """
        Full-text search over the SEC EDGAR filings archive.
        Covers the officer lists in DEF 14A (proxy statements) and 10-K (annual
        reports); those forms must disclose board members and major shareholders.
        """
        records: list[CompanyRecord] = []
        try:
            resp = self.session.get(
                self.SEC_EDGAR_SEARCH,
                params={
                    "q": f'"{name}"',
                    "forms": "DEF 14A,10-K,SC 13D,SC 13G",
                    "hits.hits._source": "period_of_report,display_names,file_date",
                    "hits.hits.total": 10,
                },
                headers={"User-Agent": "JARVIS/1.0 (research@jarvis.local)"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            hits = data.get("hits", {}).get("hits", [])
            for hit in hits[:10]:
                src = hit.get("_source", {})
                companies_raw = src.get("display_names", [])
                form_type = src.get("form_type", "")
                file_date = src.get("file_date", "")

                # display_names: [{"name": "Tesla Inc", "id": "CIK..."}]
                for entry in companies_raw if isinstance(companies_raw, list) else []:
                    company_name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
                    cik = entry.get("id", "") if isinstance(entry, dict) else ""
                    if not company_name:
                        continue

                    role_label, role_cat = self._infer_role_from_form(form_type)

                    records.append(
                        CompanyRecord(
                            company_name=company_name,
                            company_type=self._extract_company_type(company_name),
                            role=role_label,
                            role_category=role_cat,
                            status="active",
                            source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                            source_name="SEC EDGAR (US)",
                            country="USA",
                            confidence=0.82,
                            registry_id=cik,
                            risk_flags=self._detect_risks(company_name),
                            snippet=(
                                f"{form_type} filing ({file_date}) — {name} mentioned in relation to {company_name}"
                            ),
                        )
                    )

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/SEC] failed: {exc}")

        return records

    def _infer_role_from_form(self, form_type: str) -> tuple[str, str]:
        form = (form_type or "").upper()
        if form in ("DEF 14A", "PRE 14A"):
            return "Director / Board Member", "board_member"
        if form in ("SC 13D", "SC 13G"):
            return "Major Shareholder (>5%)", "shareholder"
        if form == "10-K":
            return "Executive / Director", "executive"
        return "Named in Filing", "unknown"

    # ── Companies House (UK) ──────────────────────────────────────────────────

    def _search_companies_house(self, name: str) -> list[CompanyRecord]:
        """
        The UK Companies House public search system.
        Covers registered director and company-secretary lookups.
        Official UK government data - high reliability.
        """
        records: list[CompanyRecord] = []
        try:
            resp = self.session.get(
                self.COMPANIES_HOUSE_SEARCH,
                params={"q": name},
                timeout=self.timeout,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Companies House search results: officer cards
            for card in soup.select(".officer-result, .search-result"):
                card.select_one(".officer-name, h3, .result-name")
                company_el = card.select_one(".company-name, .result-company")
                role_el = card.select_one(".officer-role, .role")
                link_el = card.select_one("a")

                if not company_el:
                    continue

                company_name = company_el.get_text(strip=True)
                role_raw = role_el.get_text(strip=True) if role_el else ""
                role_label, role_cat = self._classify_role_from_text(role_raw)
                href = link_el.get("href", "") if link_el else ""

                records.append(
                    CompanyRecord(
                        company_name=company_name,
                        company_type=self._extract_company_type(company_name),
                        role=role_label if role_label != "Unknown" else (role_raw or "Director"),
                        role_category=role_cat if role_cat != "unknown" else "board_member",
                        status="active",
                        source_url=f"https://find-and-update.company-information.service.gov.uk{href}",
                        source_name="Companies House (UK)",
                        country="United Kingdom",
                        confidence=0.87,
                        risk_flags=self._detect_risks(company_name),
                        snippet=f"Officer record: {name} at {company_name} ({role_raw})",
                    )
                )

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/CompaniesHouse] failed: {exc}")

        return records

    # ── KAP.org.tr (Turkey, Public Companies) ────────────────────────────────

    def _search_kap(self, name: str) -> list[CompanyRecord]:
        """
        KAP (Public Disclosure Platform) - Turkish listed companies supervised by
        the CMB. KAP is the official channel where companies traded on Borsa
        Istanbul publish board changes and insider disclosures.
        """
        records: list[CompanyRecord] = []
        first_name = name.split()[0] if name.split() else name

        try:
            resp = self.session.get(
                self.KAP_SEARCH,
                params={"q": name},
                timeout=self.timeout,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            if first_name.lower() in page_text.lower():
                extracted = self._extract_companies_from_text(
                    page_text,
                    name,
                    base_confidence=0.85,
                    source_url=f"{self.KAP_SEARCH}?q={requests.utils.quote(name)}",
                    source_name="KAP (Kamuyu Aydınlatma Platformu)",
                    country="Turkey",
                )
                for rec in extracted:
                    if rec.role_category in ("board_member", "executive"):
                        rec.confidence = min(1.0, rec.confidence + 0.10)
                records.extend(extracted)

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/KAP] failed: {exc}")

        return records

    # ── Ticaret Sicili Gazetesi (Turkey) ─────────────────────────────────────

    def _search_ticaret_sicil(self, name: str) -> list[CompanyRecord]:
        """
        The Turkish Trade Registry Gazette - the most authoritative Turkish source.
        Covers incorporation, capital increase, management change and liquidation
        announcements.
        """
        records: list[CompanyRecord] = []
        first_name = name.split()[0] if name.split() else name

        try:
            resp = self.session.get(
                self.TICARET_SICIL_SEARCH,
                params={"q": name},
                timeout=self.timeout + 5,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            if first_name.lower() in page_text.lower():
                extracted = self._extract_companies_from_text(
                    page_text,
                    name,
                    base_confidence=0.90,
                    source_url=f"{self.TICARET_SICIL_SEARCH}?q={requests.utils.quote(name)}",
                    source_name="Ticaret Sicili Gazetesi (TR)",
                    country="Turkey",
                )
                records.extend(extracted)

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/TicaretSicil] site unreachable (non-critical): {exc}")

        return records

    # ── Web Search (Global, Multi-Language) ──────────────────────────────────

    def _search_via_web(self, name: str) -> list[CompanyRecord]:
        """
        Run multilingual company queries through the Yahoo search engine.
        Each query targets a different role type or geography:
          - English: global companies and SEC/Companies House records
          - Turkish: Turkey-specific research
          - Crunchbase/LinkedIn: startups and tech companies
          - Bloomberg/Reuters: listed-company news

        The results are fed into the regex-based text extraction engine.
        """
        queries = [
            # Global English
            (f'"{name}" CEO founder director company', 0.65),
            (f'"{name}" board of directors chairman shareholder', 0.68),
            (f'"{name}" executive officer company Inc Corp Ltd', 0.63),
            (f'"{name}" site:opencorporates.com', 0.82),
            (f'"{name}" site:bloomberg.com CEO director', 0.75),
            (f'"{name}" site:reuters.com company executive', 0.72),
            (f'"{name}" site:crunchbase.com founder', 0.78),
            (f'"{name}" site:linkedin.com company director', 0.60),
            # Turkish
            (f'"{name}" yönetim kurulu üyesi şirket', 0.70),
            (f'"{name}" kurucu ortak A.Ş. Ltd CEO', 0.75),
            (f'"{name}" MERSİS tescil ticaret sicil', 0.80),
            (f'"{name}" site:kap.org.tr', 0.85),
            # Europe
            (f'"{name}" Geschäftsführer Aufsichtsrat GmbH AG', 0.65),
            (f'"{name}" directeur gérant conseil administration SA', 0.65),
            (f'"{name}" amministratore consiglio SpA SRL', 0.62),
        ]

        records: list[CompanyRecord] = []
        seen_snippets: set[str] = set()

        for query, base_conf in queries:
            try:
                hits = self._yahoo_fetch(query)
                for hit in hits:
                    key = hit["snippet"][:80]
                    if key in seen_snippets:
                        continue
                    seen_snippets.add(key)

                    extracted = self._extract_companies_from_text(
                        hit["snippet"] + " " + hit.get("title", ""),
                        name,
                        base_confidence=base_conf,
                        source_url=hit.get("url", ""),
                        source_name="Web Search",
                    )
                    records.extend(extracted)
            except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
                logger.log_thought(f"[CompanyService/WebSearch] '{query[:50]}' failed: {exc}")

        return records

    def _yahoo_fetch(self, query: str) -> list[dict]:
        """Parse Yahoo search results into title/snippet/url triples."""
        url = f"https://search.yahoo.com/search?p={requests.utils.quote(query)}&n=10&vc=en"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except (requests.exceptions.RequestException, OSError) as e:
            logger.log_detail(f"Yahoo fetch failed for query: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []

        for item in soup.select("div.algo, div.Sr"):
            title_el = item.select_one("h3 a, a.ac-algo-fst")
            snippet_el = item.select_one("p, .compText, .fc-falcon")
            title = title_el.get_text(strip=True) if title_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            href = title_el.get("href", "") if title_el else ""
            if snippet or title:
                results.append({"title": title, "snippet": snippet, "url": href})

        return results

    # ── Text Extraction Engine ────────────────────────────────────────────────

    def _extract_companies_from_text(
        self,
        text: str,
        person_name: str,
        base_confidence: float = 0.5,
        source_url: str = "",
        source_name: str = "",
        country: str | None = None,
    ) -> list[CompanyRecord]:
        """
        Look for a company name, role, status, industry, city and registry number
        inside a +/-200 character context window around the person's name.

        Why a window-based scan: every occurrence of the name can point at a
        separate company affiliation, so all of them are scanned.
        """
        records: list[CompanyRecord] = []
        first_name = person_name.split()[0] if person_name.split() else person_name
        norm_first = self._normalize(first_name)
        norm_text = self._normalize(text)

        positions = [m.start() for m in re.finditer(re.escape(norm_first), norm_text)]
        if not positions:
            return records

        seen_keys: set[str] = set()

        for pos in positions:
            start = max(0, pos - 150)
            end = min(len(text), pos + 250)
            window = text[start:end]

            for match in COMPANY_SUFFIX_RE.finditer(window):
                raw_name = match.group(0).strip()
                if len(raw_name) < 4 or len(raw_name) > 120:
                    continue

                key = self._normalize(raw_name)[:40]
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                role_label, role_cat = self._classify_role_from_text(window)
                status = self._classify_status(window)
                risk_flags = self._detect_risks(window + " " + raw_name)
                sector = self._infer_sector(raw_name + " " + window)
                registry_id = self._extract_registry_id(window)
                company_type = self._extract_company_type(raw_name)

                conf = base_confidence
                if role_cat != "unknown":
                    conf = min(1.0, conf + 0.05)
                if status == "active":
                    conf = min(1.0, conf + 0.03)
                if risk_flags:
                    conf = max(0.1, conf - 0.03)
                if registry_id:
                    conf = min(1.0, conf + 0.08)

                records.append(
                    CompanyRecord(
                        company_name=raw_name,
                        company_type=company_type,
                        role=role_label,
                        role_category=role_cat,
                        status=status,
                        source_url=source_url,
                        source_name=source_name,
                        country=country,
                        confidence=round(conf, 2),
                        registry_id=registry_id,
                        sector=sector,
                        risk_flags=risk_flags,
                        snippet=window.strip(),
                    )
                )

        return records

    # ── Classification Helpers ────────────────────────────────────────────────

    def _classify_role_from_text(self, text: str) -> tuple[str, str]:
        """Return the first matching multilingual role category and its label."""
        text_lower = text.lower()
        for category, pattern_list in ROLE_PATTERNS.items():
            for pattern, label in pattern_list:
                if re.search(pattern, text_lower, re.IGNORECASE | re.UNICODE):
                    return label, category
        return "Unknown", "unknown"

    def _classify_status(self, text: str) -> str:
        for status, patterns in STATUS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE | re.UNICODE):
                    return status
        return "unknown"

    def _detect_risks(self, text: str) -> list[str]:
        """
        Detect risk-signal flags.
        A flag warns the researcher; it never declares the company 'guilty'.
        """
        flags: list[str] = []
        text_lower = text.lower()
        for risk, patterns in RISK_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE | re.UNICODE):
                    flags.append(risk)
                    break
        return flags

    def _infer_sector(self, text: str) -> str | None:
        text_lower = text.lower()
        for sector, pattern in SECTOR_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE | re.UNICODE):
                return sector
        return None

    def _extract_company_type(self, name: str) -> str:
        name_lower = name.lower()
        for suffix, type_name in COMPANY_TYPE_MAP:
            if suffix.lower() in name_lower:
                return type_name
        return "Unknown"

    def _extract_registry_id(self, text: str) -> str | None:
        """
        Recognise registry numbers in several country formats:
          - MERSIS (TR): 16 digits
          - Company No (UK): 8 digits, or 2 letters + 6 digits
          - CIK (US SEC): 10 digits
          - HRB/HRA (DE): HRB/HRA + digits
        """
        patterns = [
            r"\b(\d{16})\b",  # MERSIS (TR)
            r"\b(CIK[\s\-]?\d{7,10})\b",  # SEC CIK (US)
            r"\b(HRB\s*\d{4,8})\b",  # Handelsregister (DE)
            r"\b(HRA\s*\d{4,8})\b",  # Handelsregister (DE)
            r"\b([A-Z]{2}\d{6})\b",  # Companies House (UK)
            r"\b(\d{8})\b",  # Generic 8 digits
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _normalize(self, text: str) -> str:
        """Unicode folding: s-cedilla -> s, g-breve -> g, u-umlaut -> u, and so on."""
        nfkd = unicodedata.normalize("NFKD", text.lower())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _deduplicate(self, records: list[CompanyRecord]) -> list[CompanyRecord]:
        """
        Merge records describing the same company from different sources.
        Merge rules:
          - confidence -> max
          - risk_flags -> union
          - role/status/industry/city/country -> 'unknown'/None values get filled in
          - registry id -> the first one found wins
          - source name -> official APIs (OpenCorporates, SEC, Companies House) win
        """
        merged: dict[str, CompanyRecord] = {}

        authority_sources = ("OpenCorporates", "SEC EDGAR", "Companies House", "KAP", "Ticaret Sicili")

        for rec in records:
            key = self._normalize(rec.company_name)[:40]

            if key not in merged:
                merged[key] = rec
                continue

            ex = merged[key]
            ex.confidence = max(ex.confidence, rec.confidence)
            ex.risk_flags = list(set(ex.risk_flags + rec.risk_flags))

            if ex.role_category == "unknown" and rec.role_category != "unknown":
                ex.role, ex.role_category = rec.role, rec.role_category
            if ex.status == "unknown" and rec.status != "unknown":
                ex.status = rec.status
            if not ex.sector and rec.sector:
                ex.sector = rec.sector
            if not ex.country and rec.country:
                ex.country = rec.country
            if not ex.registry_id and rec.registry_id:
                ex.registry_id = rec.registry_id

            if any(s in rec.source_name for s in authority_sources) and not any(
                s in ex.source_name for s in authority_sources
            ):
                ex.source_name = rec.source_name
                ex.source_url = rec.source_url

        return list(merged.values())


# ─── Singleton ────────────────────────────────────────────────────────────────

company_service = CompanyScraperService()

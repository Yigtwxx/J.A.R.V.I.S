"""
Global Ticari Sicil & Şirket Tarama Servisi
============================================
Kişinin dünya genelindeki şirket bağlantılarını ve yönetim kurulu
üyeliklerini birden fazla resmi/açık kaynaktan paralel olarak toplar.

Kaynak hiyerarşisi (güvenilirlik sırasına göre):
  1. OpenCorporates API  — 140+ ülke, 200M+ şirket kaydı (en kapsamlı açık veri)
  2. SEC EDGAR (ABD)     — ABD halka açık şirket yöneticileri ve pay sahipleri
  3. Companies House (UK)— İngiltere şirket müdür arama API'si
  4. KAP.org.tr (TR)     — Türkiye halka açık şirketler (SPK denetimli)
  5. Ticaret Sicili (TR) — Türkiye resmi gazete arşivi
  6. Web Arama           — Yahoo + çok dilli sorgu çeşitlemeleriyle global kapsam

NOT: MERSİS, TOBB, Europages ve D&B gibi kaynaklar JS-bağımlı arayüzlere
     sahip olduğundan şu an web arama dolaylı yoluyla kapsanmaktadır.
     Playwright entegrasyonu ilerleyen aşamada eklenebilir.
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
    Tek bir şirket kaydı. Kişiyle ilişkisi, kaynak bilgisi,
    güven skoru ve risk profiliyle birlikte tutulur.
    """
    company_name: str
    company_type: str = "Unknown"
    role: str = "Unknown"
    role_category: str = "unknown"   # founder | executive | board_member | shareholder | unknown
    status: str = "unknown"          # active | passive | liquidated | unknown
    source_url: str = ""
    source_name: str = ""
    country: str | None = None    # Şirketin kayıtlı olduğu ülke
    confidence: float = 0.5          # 0.0–1.0; kaynağın otoritesi + bağlam zenginliğine göre
    registry_id: str | None = None  # OpenCorporates id, MERSİS, Company No, CIK, vb.
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
# En yaygın hukuki biçimler: İngilizce, Almanca, Fransızca, İspanyolca,
# İtalyanca, Hollandaca, Portekizce ve Türkçe.
COMPANY_SUFFIX_RE = re.compile(
    r'\b((?:[A-ZÇÖŞİĞÜÀ-Ÿ][A-Za-zÀ-ÿÇçÖöŞşİiĞğÜü0-9&\-\.]{1,30}\s*){1,6})'
    r'(?:'
    # Anglosakson
    r'Inc\.|Inc\b|Corp\.|Corp\b|LLC\b|L\.L\.C\.|Ltd\.|Ltd\b|'
    r'PLC\b|P\.L\.C\.|LLP\b|LP\b|L\.P\.|PLLC\b|'
    # Almanca/İsviçre/Avusturya
    r'GmbH\b|AG\b|KG\b|OHG\b|UG\b|SE\b|'
    # Fransızca/Belçika/İsviçre
    r'S\.A\.\b|SA\b|S\.A\.R\.L\.\b|SARL\b|SAS\b|S\.A\.S\.\b|'
    r'EURL\b|SCI\b|SNC\b|'
    # İspanyolca/Portekizce
    r'S\.L\.\b|SL\b|S\.R\.L\.\b|SRL\b|S\.A\. de C\.V\.\b|'
    # İtalyanca
    r'S\.p\.A\.\b|SpA\b|S\.r\.l\.\b|Srl\b|'
    # Hollandaca/Belçika
    r'B\.V\.\b|BV\b|N\.V\.\b|NV\b|'
    # İskandinav
    r'AB\b|A/S\b|ApS\b|Oy\b|'
    # Türkçe
    r'A\.Ş\.\b|AŞ\b|Ltd\. Şti\.\b|LTD\.ŞTİ\.\b|Holding\b|HOLDİNG\b|'
    r'Grubu\b|GRUP\b|Şirketi\b'
    r')',
    re.UNICODE,
)

# Hukuki tip eşleme tablosu (öncelik sırasına göre — daha uzun suffix önce)
COMPANY_TYPE_MAP = [
    ('Ltd. Şti.',  'Limited Şirket (TR)'),
    ('LTD.ŞTİ.',  'Limited Şirket (TR)'),
    ('A.Ş.',       'Anonim Şirket (TR)'),
    ('Holding',    'Holding'),
    ('HOLDİNG',    'Holding'),
    ('S.A. de C.V.', 'Sociedad Anónima (MX)'),
    ('S.p.A.',     'Società per Azioni (IT)'),
    ('S.r.l.',     'Società a responsabilità limitata (IT)'),
    ('S.A.R.L.',   'Société à responsabilité limitée (FR)'),
    ('S.A.',       'Société Anonyme / S.A.'),
    ('GmbH',       'Gesellschaft mit beschränkter Haftung (DE)'),
    ('B.V.',       'Besloten Vennootschap (NL)'),
    ('N.V.',       'Naamloze Vennootschap (NL)'),
    ('P.L.C.',     'Public Limited Company (UK)'),
    ('PLC',        'Public Limited Company (UK)'),
    ('L.L.C.',     'Limited Liability Company (US)'),
    ('LLC',        'Limited Liability Company (US)'),
    ('Inc.',       'Incorporated (US/CA)'),
    ('Inc',        'Incorporated (US/CA)'),
    ('Corp.',      'Corporation (US/CA)'),
    ('Corp',       'Corporation (US/CA)'),
    ('Ltd.',       'Limited Company'),
    ('Ltd',        'Limited Company'),
    ('LLP',        'Limited Liability Partnership'),
    ('AG',         'Aktiengesellschaft (DE/CH/AT)'),
    ('AB',         'Aktiebolag (SE)'),
    ('A/S',        'Aktieselskab (DK/NO)'),
    ('ApS',        'Anpartsselskab (DK)'),
    ('Oy',         'Osakeyhtiö (FI)'),
    ('SE',         'Societas Europaea (EU)'),
    ('KG',         'Kommanditgesellschaft (DE)'),
    ('SAS',        'Société par Actions Simplifiée (FR)'),
    ('SRL',        'Sociedad de Responsabilidad Limitada'),
    ('Grubu',      'Grup'),
    ('GRUP',       'Grup'),
    ('Şirketi',    'Şirket (TR)'),
]

# ── Rol örüntüleri (çok dilli) ──────────────────────────────────────────────
ROLE_PATTERNS: dict[str, list[tuple[str, str]]] = {
    'founder': [
        (r'\b(co[- ]?founder|founder|founding\s*partner)\b',   'Co-Founder / Founder'),
        (r'\b(kurucu\s*ortak|kurucu)\b',                        'Kurucu / Ortak'),
        (r'\b(gründer|mitgründer)\b',                           'Gründer (DE)'),
        (r'\b(fondateur|co-fondateur)\b',                       'Fondateur (FR)'),
        (r'\b(fundador|cofundador)\b',                          'Fundador (ES)'),
        (r'\bmüteşebbis\b',                                     'Müteşebbis (TR)'),
    ],
    'executive': [
        (r'\bchief\s*executive\s*officer\b|\bceo\b',            'CEO'),
        (r'\bchief\s*financial\s*officer\b|\bcfo\b',            'CFO'),
        (r'\bchief\s*operating\s*officer\b|\bcoo\b',            'COO'),
        (r'\bchief\s*technology\s*officer\b|\bcto\b',           'CTO'),
        (r'\bmanaging\s*director\b|\bmd\b',                     'Managing Director'),
        (r'\bgeneral\s*manager\b',                              'General Manager'),
        (r'\bpresident\b',                                      'President'),
        (r'\bchairman\b|\bchairperson\b',                       'Chairman'),
        (r'\bgeschäftsführer\b',                                'Geschäftsführer (DE)'),
        (r'\bgerant\b|\bprésident[-\s]directeur\b|\bpdg\b',    'Gérant / PDG (FR)'),
        (r'\bgenel\s*müdür\b',                                  'Genel Müdür (TR)'),
        (r'\byönetim\s*kurulu\s*başkan[ıi]\b',                  'YK Başkanı (TR)'),
        (r'\bmurahhas\s*aza\b',                                  'Murahhas Aza (TR)'),
        (r'\byönetici\b|\bdirektör\b',                          'Yönetici / Direktör (TR)'),
        (r'\badministrateur\s*délégué\b',                       'Administrateur Délégué (FR/BE)'),
        (r'\badministrador\s*único\b',                          'Administrador Único (ES)'),
    ],
    'board_member': [
        (r'\bboard\s*(of\s*directors?\s*)?member\b|\bdirector\b', 'Director / Board Member'),
        (r'\bnon[- ]?executive\s*director\b',                   'Non-Executive Director'),
        (r'\bindependent\s*director\b',                         'Independent Director'),
        (r'\bsupervisory\s*board\b|\baufsichtsrat\b',           'Supervisory Board (DE)'),
        (r'\byönetim\s*kurulu\s*üye\b|\byk\s*üye\b',           'YK Üyesi (TR)'),
        (r'\bdenetim\s*kurulu\b',                               'Denetim Kurulu Üyesi (TR)'),
        (r'\badministrateur\b',                                 'Administrateur (FR)'),
        (r'\bconsejero\b',                                      'Consejero (ES)'),
        (r'\bamministratore\b',                                 'Amministratore (IT)'),
        (r'\bcommissario\b',                                    'Commissario (IT)'),
    ],
    'shareholder': [
        (r'\bshareholder\b|\bstockholder\b',                    'Shareholder'),
        (r'\bbeneficial\s*owner\b',                             'Beneficial Owner'),
        (r'\bmajority\s*owner\b|\bminority\s*owner\b',          'Owner'),
        (r'\bprincipal\s*shareholder\b',                        'Principal Shareholder'),
        (r'\bhissedar\b|\bpay\s*sahibi\b|\bsermayedar\b',       'Hissedar / Pay Sahibi (TR)'),
        (r'\bortak\b',                                          'Ortak (TR)'),
        (r'\bactionnaire\b',                                    'Actionnaire (FR)'),
        (r'\bgesellschafter\b',                                 'Gesellschafter (DE)'),
        (r'\baccionista\b',                                     'Accionista (ES)'),
        (r'\bazionista\b',                                      'Azionista (IT)'),
    ],
}

STATUS_PATTERNS = {
    'liquidated': [
        r'\b(liquidat|dissolv|wound\s*up|struck\s*off|winding\s*up)\b',
        r'\b(tasfiye|iflas|konkordato|kapatıl|feshedil|kapandı)\b',
        r'\b(aufgelöst|insolvent|liquidation)\b',
        r'\b(en\s*liquidation|radié|dissous)\b',
        r'\b(liquidazione|fallimento|cancellata)\b',
    ],
    'passive': [
        r'\b(dormant|inactive|dissolved|non[- ]?trading)\b',
        r'\b(pasif|faaliyetsiz|faal\s*değil)\b',
        r'\b(ruhend|inaktiv)\b',
    ],
    'active': [
        r'\b(active|trading|operating|incorporated)\b',
        r'\b(aktif|faal[^i]|faaliyet\s*göster)\b',
        r'\b(aktiv|in\s*betrieb)\b',
        r'\b(en\s*activité|actif)\b',
    ],
}

# Risk sinyalleri — araştırmacıyı uyarır, şirketi mahkûm etmez
RISK_PATTERNS = {
    'offshore': [
        r'\b(bvi|british\s*virgin\s*islands|cayman|bermuda|jersey|guernsey|'
        r'isle\s*of\s*man|malta|cyprus|kıbrıs|bahamas|panama|seychelles|'
        r'mauritius|samoa|vanuatu|liechtenstein|andorra|monaco|offshore|'
        r'tax\s*haven|vergi\s*cenneti)\b',
    ],
    'shell_company': [
        r'\b(shell\s*company|paravan\s*şirket|nominee|front\s*company|'
        r'mailbox\s*company|letterbox\s*company|sanal\s*ofis)\b',
    ],
    'liquidated':     [r'\b(liquidat|iflas|tasfiye|konkordato|insolvent)\b'],
    'pep_related':    [r'\b(politician|siyasetçi|minister|bakan|senator|'
                       r'congress|parliament|meclis|deputy|milletvekili)\b'],
    'sanction':       [r'\b(sanctioned|sanction|embargo|ofac|eu\s*list|yaptırım)\b'],
    'high_risk_sector': [r'\b(gambling|casino|cryptocurrency\s*exchange|'
                         r'arms|weapons|narco|kumar|silah)\b'],
}

# ── Sektör tespiti (global) ─────────────────────────────────────────────────
SECTOR_PATTERNS = {
    'Technology':    r'\b(technology|tech|software|it\b|digital|cyber|cloud|ai\b|'
                     r'saas|fintech|yazılım|bilişim|teknoloji)\b',
    'Real Estate':   r'\b(real\s*estate|property|gayrimenkul|emlak|reit|immobili)\b',
    'Construction':  r'\b(construction|building|infrastructure|inşaat|yapı|müteahhit)\b',
    'Energy':        r'\b(energy|oil|gas|solar|wind|renewable|enerji|petrol|doğalgaz)\b',
    'Finance':       r'\b(finance|financial|investment|banking|insurance|fund|hedge|'
                     r'private\s*equity|finans|yatırım|sigorta|banka|portföy)\b',
    'Healthcare':    r'\b(health|medical|pharma|hospital|clinic|biotech|'
                     r'sağlık|hastane|ilaç|medikal)\b',
    'Mining':        r'\b(mining|mineral|gold|copper|coal|maden|madencilik)\b',
    'Media':         r'\b(media|publishing|broadcasting|press|news|'
                     r'medya|yayın|gazete|basın)\b',
    'Tourism':       r'\b(tourism|hotel|hospitality|travel|resort|'
                     r'turizm|otel|seyahat)\b',
    'Logistics':     r'\b(logistics|shipping|freight|transport|supply\s*chain|'
                     r'lojistik|nakliye|kargo)\b',
    'Retail':        r'\b(retail|e[- ]?commerce|marketplace|consumer|'
                     r'perakende|e[- ]ticaret|market)\b',
    'Food & Beverage': r'\b(food|beverage|restaurant|agriculture|gıda|tarım|restoran)\b',
    'Education':     r'\b(education|university|academy|training|eğitim|üniversite|kurs)\b',
    'Legal':         r'\b(law\s*firm|legal|attorney|barrister|solicitor|hukuk|avukat)\b',
    'Defense':       r'\b(defense|defence|aerospace|military|savunma|havacılık)\b',
}


# ─── Service ──────────────────────────────────────────────────────────────────

class CompanyScraperService:
    """
    Global Şirket Tarama Servisi.

    Kişiyle ilişkili şirketleri 6 farklı kaynaktan eş zamanlı toplar:
    OpenCorporates, SEC EDGAR, Companies House, KAP, Ticaret Sicili ve web araması.

    Tasarım kararları:
      - ThreadPoolExecutor: IO-bound scraping; mevcut servislerle tutarlı.
      - Çok dilli rol/suffix tespiti: TR, EN, DE, FR, ES, IT, NL, PT, İSK.
      - Dinamik confidence: kaynak otoritesi + bağlam kalitesi = skora yansır.
      - Risk bayrakları: OSINT etiğine uygun — uyarı, suçlama değil.
      - Deduplication: aynı şirket N kaynaktan gelirse birleştirilir,
        confidence yükseltilir, hiçbir bilgi kaybolmaz.
    """

    OPENCORPORATES_SEARCH = "https://api.opencorporates.com/v0.4/officers/search"
    SEC_EDGAR_SEARCH      = "https://efts.sec.gov/LATEST/search-index"
    COMPANIES_HOUSE_SEARCH = "https://find-and-update.company-information.service.gov.uk/search/officers"
    KAP_SEARCH            = "https://www.kap.org.tr/tr/arama"
    TICARET_SICIL_SEARCH  = "https://www.ticaretsiciilgazetesi.gtb.gov.tr/arama"

    def __init__(self, timeout: int = 12):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout

    # ── Public API ────────────────────────────────────────────────────────────

    def search_companies(self, name: str) -> list[dict]:
        """
        Kişinin global şirket bağlantılarını tüm kaynaklardan toplar.

        Args:
            name: Aranacak kişinin tam adı (örn. "Elon Musk", "Ahmet Yılmaz")

        Returns:
            Confidence skoruna göre azalan sırada sıralı dict listesi.
        """
        logger.log_action("CompanyService: Global şirket taraması başlatıldı", target=name)
        records: list[CompanyRecord] = []

        tasks = {
            "OpenCorporates":        lambda: self._search_opencorporates(name),
            "SEC EDGAR (US)":        lambda: self._search_sec_edgar(name),
            "Companies House (UK)":  lambda: self._search_companies_house(name),
            "Wikidata":              lambda: self._search_wikidata(name),
            "KAP (TR)":              lambda: self._search_kap(name),
            "Ticaret Sicili (TR)":   lambda: self._search_ticaret_sicil(name),
            "Web Arama":             lambda: self._search_via_web(name),
        }

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fn): label for label, fn in tasks.items()}
            for future in as_completed(futures):
                label = futures[future]
                try:
                    results = future.result(timeout=self.timeout + 8)
                    records.extend(results)
                    logger.log_action(f"CompanyService {label}: {len(results)} kayıt")
                except Exception as exc:
                    logger.log_warning(f"[CompanyService] {label} başarısız (kritik değil): {exc}")

        merged = self._deduplicate(records)
        merged.sort(key=lambda r: r.confidence, reverse=True)

        if len(merged) >= 5:
            logger.log_thought(
                f"[CompanyService] {len(merged)} şirket — karmaşık ağ yapısı olabilir"
            )

        logger.log_success(f"[CompanyService] Toplam benzersiz şirket: {len(merged)}")
        return [r.to_dict() for r in merged]

    # ── OpenCorporates ────────────────────────────────────────────────────────

    def _search_opencorporates(self, name: str) -> list[CompanyRecord]:
        """
        OpenCorporates officer/director arama API'si.
        140+ ülke, 200M+ kayıt — en geniş kapsamlı açık şirket veritabanı.

        Kısıtlama: Ücretsiz API'de sayfalama sınırı vardır;
        ilk 20 sonuç çekilir (isim netliği yüksekse yeterlidir).
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
                    "[CompanyService/OpenCorporates] API token gerekli (401/403) — "
                    "diğer kaynaklara (SEC/Companies House/web) devrediliyor."
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

                role_raw  = officer.get("position", "")
                role_label, role_cat = self._classify_role_from_text(role_raw)
                if role_label == "Unknown" and role_raw:
                    role_label = role_raw.title()

                status_raw = company.get("current_status", "unknown")
                status = self._map_oc_status(status_raw)

                jurisdiction = company.get("jurisdiction_code", "")
                country = self._jurisdiction_to_country(jurisdiction)

                company_url = (
                    f"https://opencorporates.com{company.get('opencorporates_url', '')}"
                    if company.get("opencorporates_url") else ""
                )

                records.append(CompanyRecord(
                    company_name=company_name,
                    company_type=self._extract_company_type(company_name),
                    role=role_label,
                    role_category=role_cat,
                    status=status,
                    source_url=company_url,
                    source_name="OpenCorporates",
                    country=country,
                    confidence=0.88,   # Yapısal API verisi = yüksek güven
                    registry_id=company.get("company_number"),
                    risk_flags=self._detect_risks(company_name + ' ' + (country or '')),
                    snippet=(
                        f"{role_label} at {company_name} ({country or jurisdiction})"
                        if country or jurisdiction else f"{role_label} at {company_name}"
                    ),
                ))

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/OpenCorporates] Başarısız: {exc}")

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
        """OpenCorporates jurisdiction kodunu insan-okunabilir ülke adına çevirir."""
        mapping = {
            "us": "USA", "gb": "United Kingdom", "de": "Germany",
            "fr": "France", "nl": "Netherlands", "ch": "Switzerland",
            "au": "Australia", "ca": "Canada", "jp": "Japan",
            "cn": "China", "sg": "Singapore", "ie": "Ireland",
            "lu": "Luxembourg", "cy": "Cyprus", "mt": "Malta",
            "ky": "Cayman Islands", "bvi": "British Virgin Islands",
            "tr": "Turkey", "ae": "UAE", "ru": "Russia",
            "se": "Sweden", "dk": "Denmark", "fi": "Finland",
            "no": "Norway", "it": "Italy", "es": "Spain",
            "pt": "Portugal", "be": "Belgium", "at": "Austria",
            "br": "Brazil", "mx": "Mexico", "in": "India",
            "hk": "Hong Kong", "za": "South Africa",
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
            sr = self.session.get(api, params={
                "action": "wbsearchentities", "search": name, "language": "en",
                "format": "json", "type": "item", "limit": 1,
            }, timeout=self.timeout)
            sr.raise_for_status()
            hits = sr.json().get("search", [])
            if not hits:
                return records
            qid = hits[0].get("id")
            if not qid:
                return records

            # 2) Fetch the person's claims
            cr = self.session.get(api, params={
                "action": "wbgetentities", "ids": qid, "props": "claims", "format": "json",
            }, timeout=self.timeout)
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
            lr = self.session.get(api, params={
                "action": "wbgetentities", "ids": "|".join(org_qids),
                "props": "labels", "languages": "en", "format": "json",
            }, timeout=self.timeout)
            lr.raise_for_status()
            entities = lr.json().get("entities", {})

            person_url = f"https://www.wikidata.org/wiki/{qid}"
            for oid in org_qids:
                label = (
                    entities.get(oid, {}).get("labels", {}).get("en", {}).get("value")
                )
                if not label:
                    continue
                records.append(CompanyRecord(
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
                ))
        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/Wikidata] Başarısız: {exc}")
        return records

    # ── SEC EDGAR (USA) ───────────────────────────────────────────────────────

    def _search_sec_edgar(self, name: str) -> list[CompanyRecord]:
        """
        ABD Menkul Kıymetler ve Borsa Komisyonu (SEC) EDGAR tam metin araması.
        DEF 14A (proxy beyanları) ve 10-K (yıllık raporlar) yönetici listelerini kapsar.
        Bu formlar yönetim kurulu üyelerini ve büyük pay sahiplerini açıklamak zorundadır.
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
                for entry in (companies_raw if isinstance(companies_raw, list) else []):
                    company_name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
                    cik = entry.get("id", "") if isinstance(entry, dict) else ""
                    if not company_name:
                        continue

                    role_label, role_cat = self._infer_role_from_form(form_type)

                    records.append(CompanyRecord(
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
                            f"{form_type} filing ({file_date}) — "
                            f"{name} mentioned in relation to {company_name}"
                        ),
                    ))

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/SEC] Başarısız: {exc}")

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
        İngiltere Companies House açık arama sistemi.
        Kayıtlı müdür (director) ve şirket sekreteri aramalarını kapsar.
        Resmi UK hükümeti verisi — yüksek güvenilirlik.
        """
        records: list[CompanyRecord] = []
        try:
            resp = self.session.get(
                self.COMPANIES_HOUSE_SEARCH,
                params={"q": name},
                timeout=self.timeout,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Companies House search results: officer cards
            for card in soup.select('.officer-result, .search-result'):
                card.select_one('.officer-name, h3, .result-name')
                company_el = card.select_one('.company-name, .result-company')
                role_el    = card.select_one('.officer-role, .role')
                link_el    = card.select_one('a')

                if not company_el:
                    continue

                company_name = company_el.get_text(strip=True)
                role_raw     = role_el.get_text(strip=True) if role_el else ""
                role_label, role_cat = self._classify_role_from_text(role_raw)
                href = link_el.get('href', '') if link_el else ''

                records.append(CompanyRecord(
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
                ))

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/CompaniesHouse] Başarısız: {exc}")

        return records

    # ── KAP.org.tr (Turkey, Public Companies) ────────────────────────────────

    def _search_kap(self, name: str) -> list[CompanyRecord]:
        """
        Kamuyu Aydınlatma Platformu — SPK denetimindeki halka açık Türk şirketleri.
        KAP, Borsa İstanbul'da işlem gören şirketlerin yönetim kurulu değişikliklerini
        ve içeriden öğrenen açıklamalarını resmi olarak yayınlar.
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

            soup = BeautifulSoup(resp.text, 'html.parser')
            page_text = soup.get_text(' ', strip=True)

            if first_name.lower() in page_text.lower():
                extracted = self._extract_companies_from_text(
                    page_text, name,
                    base_confidence=0.85,
                    source_url=f"{self.KAP_SEARCH}?q={requests.utils.quote(name)}",
                    source_name="KAP (Kamuyu Aydınlatma Platformu)",
                    country="Turkey",
                )
                for rec in extracted:
                    if rec.role_category in ('board_member', 'executive'):
                        rec.confidence = min(1.0, rec.confidence + 0.10)
                records.extend(extracted)

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/KAP] Başarısız: {exc}")

        return records

    # ── Ticaret Sicili Gazetesi (Turkey) ─────────────────────────────────────

    def _search_ticaret_sicil(self, name: str) -> list[CompanyRecord]:
        """
        T.C. Ticaret Sicili Gazetesi — en yüksek otoriteli Türkiye kaynağı.
        Şirket kuruluş, sermaye artışı, yönetim değişikliği ve tasfiye ilanlarını kapsar.
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

            soup = BeautifulSoup(resp.text, 'html.parser')
            page_text = soup.get_text(' ', strip=True)

            if first_name.lower() in page_text.lower():
                extracted = self._extract_companies_from_text(
                    page_text, name,
                    base_confidence=0.90,
                    source_url=f"{self.TICARET_SICIL_SEARCH}?q={requests.utils.quote(name)}",
                    source_name="Ticaret Sicili Gazetesi (TR)",
                    country="Turkey",
                )
                records.extend(extracted)

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
            logger.log_thought(f"[CompanyService/TicaretSicil] Site erişilemez (kritik değil): {exc}")

        return records

    # ── Web Search (Global, Multi-Language) ──────────────────────────────────

    def _search_via_web(self, name: str) -> list[CompanyRecord]:
        """
        Yahoo arama motoruyla çok dilli şirket sorguları çalıştırır.
        Her sorgu farklı bir rol tipini veya coğrafyayı hedefler:
          - İngilizce: global şirketler ve SEC/Companies House kayıtları
          - Türkçe: Türkiye-spesifik araştırma
          - Crunchbase/LinkedIn: startup ve tech şirketleri
          - Bloomberg/Reuters: halka açık şirket haberleri

        Sonuçlar regex tabanlı text extraction motoruna beslenir.
        """
        queries = [
            # Global İngilizce
            (f'"{name}" CEO founder director company',                  0.65),
            (f'"{name}" board of directors chairman shareholder',       0.68),
            (f'"{name}" executive officer company Inc Corp Ltd',        0.63),
            (f'"{name}" site:opencorporates.com',                       0.82),
            (f'"{name}" site:bloomberg.com CEO director',               0.75),
            (f'"{name}" site:reuters.com company executive',            0.72),
            (f'"{name}" site:crunchbase.com founder',                   0.78),
            (f'"{name}" site:linkedin.com company director',            0.60),
            # Türkçe
            (f'"{name}" yönetim kurulu üyesi şirket',                   0.70),
            (f'"{name}" kurucu ortak A.Ş. Ltd CEO',                    0.75),
            (f'"{name}" MERSİS tescil ticaret sicil',                   0.80),
            (f'"{name}" site:kap.org.tr',                               0.85),
            # Avrupa
            (f'"{name}" Geschäftsführer Aufsichtsrat GmbH AG',         0.65),
            (f'"{name}" directeur gérant conseil administration SA',    0.65),
            (f'"{name}" amministratore consiglio SpA SRL',             0.62),
        ]

        records: list[CompanyRecord] = []
        seen_snippets: set[str] = set()

        for query, base_conf in queries:
            try:
                hits = self._yahoo_fetch(query)
                for hit in hits:
                    key = hit['snippet'][:80]
                    if key in seen_snippets:
                        continue
                    seen_snippets.add(key)

                    extracted = self._extract_companies_from_text(
                        hit['snippet'] + ' ' + hit.get('title', ''),
                        name,
                        base_confidence=base_conf,
                        source_url=hit.get('url', ''),
                        source_name="Web Arama",
                    )
                    records.extend(extracted)
            except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as exc:
                logger.log_thought(f"[CompanyService/WebSearch] '{query[:50]}' başarısız: {exc}")

        return records

    def _yahoo_fetch(self, query: str) -> list[dict]:
        """Yahoo arama sonuçlarını parse eder; title/snippet/url döner."""
        url = f"https://search.yahoo.com/search?p={requests.utils.quote(query)}&n=10&vc=en"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except (requests.exceptions.RequestException, OSError) as e:
            logger.log_detail(f"Yahoo fetch failed for query: {e}")
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        results: list[dict] = []

        for item in soup.select('div.algo, div.Sr'):
            title_el   = item.select_one('h3 a, a.ac-algo-fst')
            snippet_el = item.select_one('p, .compText, .fc-falcon')
            title   = title_el.get_text(strip=True)   if title_el   else ''
            snippet = snippet_el.get_text(strip=True) if snippet_el else ''
            href    = title_el.get('href', '')         if title_el   else ''
            if snippet or title:
                results.append({'title': title, 'snippet': snippet, 'url': href})

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
        Metindeki kişi adı etrafındaki ±200 karakterlik bağlam penceresinde
        şirket adı, rol, durum, sektör, şehir ve kayıt numarası arar.

        Neden pencere tabanlı arama: Kişi adının her geçişi bağımsız
        bir şirket bağlantısını işaret edebilir; tüm geçişleri tarıyoruz.
        """
        records: list[CompanyRecord] = []
        first_name = person_name.split()[0] if person_name.split() else person_name
        norm_first = self._normalize(first_name)
        norm_text  = self._normalize(text)

        positions = [
            m.start() for m in re.finditer(re.escape(norm_first), norm_text)
        ]
        if not positions:
            return records

        seen_keys: set[str] = set()

        for pos in positions:
            start  = max(0, pos - 150)
            end    = min(len(text), pos + 250)
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
                status               = self._classify_status(window)
                risk_flags           = self._detect_risks(window + ' ' + raw_name)
                sector               = self._infer_sector(raw_name + ' ' + window)
                registry_id          = self._extract_registry_id(window)
                company_type         = self._extract_company_type(raw_name)

                conf = base_confidence
                if role_cat != 'unknown':
                    conf = min(1.0, conf + 0.05)
                if status == 'active':
                    conf = min(1.0, conf + 0.03)
                if risk_flags:
                    conf = max(0.1, conf - 0.03)
                if registry_id:
                    conf = min(1.0, conf + 0.08)

                records.append(CompanyRecord(
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
                ))

        return records

    # ── Classification Helpers ────────────────────────────────────────────────

    def _classify_role_from_text(self, text: str) -> tuple[str, str]:
        """İlk eşleşen çok dilli rol kategorisini ve etiketini döner."""
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
        Risk sinyali bayraklarını tespit eder.
        Bayrak = araştırmacıya uyarı; şirketi 'suçlu' ilan etmez.
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
        Farklı ülke formatlarındaki kayıt numaralarını tanır:
          - MERSİS (TR): 16 hane
          - Company No (UK): 8 hane / 2 harf + 6 hane
          - CIK (US SEC): 10 hane
          - HRB/HRA (DE): HRB/HRA + rakamlar
        """
        patterns = [
            r'\b(\d{16})\b',                # MERSİS (TR)
            r'\b(CIK[\s\-]?\d{7,10})\b',   # SEC CIK (US)
            r'\b(HRB\s*\d{4,8})\b',        # Handelsregister (DE)
            r'\b(HRA\s*\d{4,8})\b',        # Handelsregister (DE)
            r'\b([A-Z]{2}\d{6})\b',        # Companies House (UK)
            r'\b(\d{8})\b',                # Genel 8 hane
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _normalize(self, text: str) -> str:
        """Unicode normalleştirme: ş→s, ğ→g, ü→u vb."""
        nfkd = unicodedata.normalize('NFKD', text.lower())
        return ''.join(c for c in nfkd if not unicodedata.combining(c))

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _deduplicate(self, records: list[CompanyRecord]) -> list[CompanyRecord]:
        """
        Aynı şirketi farklı kaynaklardan gelen kayıtları birleştirir.
        Birleştirme kuralları:
          - confidence → max
          - risk_flags → union
          - rol/durum/sektör/şehir/ülke → 'unknown/None' olanlar güncellenir
          - kayıt no → ilk bulunan korunur
          - kaynak adı → resmi API (OpenCorporates, SEC, Companies House) öncelikli
        """
        merged: dict[str, CompanyRecord] = {}

        authority_sources = ('OpenCorporates', 'SEC EDGAR', 'Companies House',
                             'KAP', 'Ticaret Sicili')

        for rec in records:
            key = self._normalize(rec.company_name)[:40]

            if key not in merged:
                merged[key] = rec
                continue

            ex = merged[key]
            ex.confidence = max(ex.confidence, rec.confidence)
            ex.risk_flags = list(set(ex.risk_flags + rec.risk_flags))

            if ex.role_category == 'unknown' and rec.role_category != 'unknown':
                ex.role, ex.role_category = rec.role, rec.role_category
            if ex.status == 'unknown' and rec.status != 'unknown':
                ex.status = rec.status
            if not ex.sector and rec.sector:
                ex.sector = rec.sector
            if not ex.country and rec.country:
                ex.country = rec.country
            if not ex.registry_id and rec.registry_id:
                ex.registry_id = rec.registry_id

            if any(s in rec.source_name for s in authority_sources) and not any(s in ex.source_name for s in authority_sources):
                    ex.source_name = rec.source_name
                    ex.source_url  = rec.source_url

        return list(merged.values())


# ─── Singleton ────────────────────────────────────────────────────────────────

company_service = CompanyScraperService()

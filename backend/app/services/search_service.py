import contextlib
import difflib
import json
import re
import time
import unicodedata
import urllib.parse
from threading import Lock

import requests
import urllib3
from bs4 import BeautifulSoup
from cachetools import TTLCache, cached
from cachetools.keys import hashkey

from app.utils.logger import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Service-level cache for Wikipedia images — same person is often re-queried at
# different search depths; the image rarely changes. Thread-safe (calls run in
# executor threads). Keyed on the normalized query, ignoring the bound instance.
_wiki_image_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)
_wiki_image_lock = Lock()

# Image-search cache — recent public photos for a subject. Shorter TTL than the
# Wikipedia portrait cache since "latest images" should stay reasonably fresh.
_image_search_cache: TTLCache = TTLCache(maxsize=128, ttl=900)
_image_search_lock = Lock()

class SearchService:
    """Service for web search using Google scraping"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    @cached(
        cache=_wiki_image_cache,
        key=lambda self, query: hashkey(query.lower().strip()),
        lock=_wiki_image_lock,
    )
    def search_wikipedia_image(self, query: str) -> str:
        """
        Query Wikipedia API to find a high-quality main image for the person
        """
        try:
            logger.log_thought(f"Querying biographical databases for visual identity of: {query}")

            # 1. First, search for the Wikipedia page title
            search_url = "https://en.wikipedia.org/w/api.php"
            wiki_headers = {'User-Agent': 'JARVIS_Analyzer/1.0 (admin@local)'}
            search_params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": 1
            }

            search_res = self.session.get(search_url, params=search_params, headers=wiki_headers, timeout=5)
            search_data = search_res.json()

            if not search_data.get('query', {}).get('search'):
                return ""

            page_title = search_data['query']['search'][0]['title']

            # Verify the title actually matches what we're looking for
            query_words = set(query.lower().split())
            title_words = set(page_title.lower().split())

            # Allow minor differences like 'Erdoğan' vs 'Erdogan'
            def normalize_text(text):
                return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

            query_words_norm = {normalize_text(w) for w in query_words}
            title_words_norm = {normalize_text(w) for w in title_words}

            # Check if all words from the query exist in the Wikipedia title
            if not query_words_norm.issubset(title_words_norm):
                logger.log_warning(f"Wikipedia result '{page_title}' failed subset check for '{query}'. Skipping visual extraction.")
                return ""

            # 2. Then get the main image (pageimage) for that title
            image_params = {
                "action": "query",
                "format": "json",
                "prop": "pageimages",
                "titles": page_title,
                "pithumbsize": 800  # Request a reasonably large image
            }

            img_res = self.session.get(search_url, params=image_params, headers=wiki_headers, timeout=5)
            img_data = img_res.json()

            pages = img_data.get('query', {}).get('pages', {})
            for _page_id, page_info in pages.items():
                if 'thumbnail' in page_info and 'source' in page_info['thumbnail']:
                    img_url = page_info['thumbnail']['source']
                    logger.log_success(f"Visual identity confirmed. Source: {img_url}")
                    return img_url

            return ""

        except (requests.exceptions.RequestException, OSError, AttributeError, KeyError, ValueError) as e:
            logger.log_warning(f"Failed to extract biographical image: {e}")
            return ""

    @cached(
        cache=_image_search_cache,
        key=lambda self, query, limit=8: hashkey(query.lower().strip(), limit),
        lock=_image_search_lock,
    )
    def search_images(self, query: str, limit: int = 8) -> list[dict[str, str]]:
        """Find recent publicly published images for a person or place.

        Tries DuckDuckGo image search first (best recency/coverage), then
        Openverse (CC-licensed media, keyless), then the Wikipedia portrait as a
        last resort. Every source is wrapped so one failing never zeroes the rest.

        Returns a list of ``{image_url, thumbnail, source_url, title}``.
        """
        logger.log_action("Sweeping public image grid", target=query)

        images = self._ddg_images(query, limit)
        if not images:
            images = self._openverse_images(query, limit)
        if not images:
            wiki = self.search_wikipedia_image(query)
            if wiki:
                images = [{"image_url": wiki, "thumbnail": wiki, "source_url": "", "title": query}]

        if images:
            logger.log_success(f"Retrieved {len(images)} public image(s) for '{query}'")
        else:
            logger.log_warning(f"No public images located for '{query}'")
        return images[:limit]

    def _ddg_images(self, query: str, limit: int) -> list[dict[str, str]]:
        """DuckDuckGo image search — extract the vqd token, then hit i.js."""
        try:
            token_resp = self.session.get(
                "https://duckduckgo.com/", params={"q": query}, timeout=10
            )
            match = re.search(r'vqd=["\']?([\d-]+)', token_resp.text)
            if not match:
                return []
            vqd = match.group(1)

            resp = self.session.get(
                "https://duckduckgo.com/i.js",
                params={"l": "us-en", "o": "json", "q": query, "vqd": vqd, "p": "1"},
                headers={"Referer": "https://duckduckgo.com/"},
                timeout=10,
            )
            resp.raise_for_status()
            data = json.loads(resp.text)

            images: list[dict[str, str]] = []
            for r in data.get("results", [])[:limit]:
                img_url = r.get("image", "")
                if img_url:
                    images.append({
                        "image_url": img_url,
                        "thumbnail": r.get("thumbnail", "") or img_url,
                        "source_url": r.get("url", ""),
                        "title": r.get("title", ""),
                    })
            return images
        except (requests.exceptions.RequestException, OSError, ValueError, KeyError) as e:
            logger.log_warning(f"DuckDuckGo image search failed: {e}")
            return []

    def _openverse_images(self, query: str, limit: int) -> list[dict[str, str]]:
        """Openverse API — free, keyless CC-licensed image search (fallback)."""
        try:
            resp = self.session.get(
                "https://api.openverse.org/v1/images/",
                params={"q": query, "page_size": limit},
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()

            images: list[dict[str, str]] = []
            for r in data.get("results", [])[:limit]:
                img_url = r.get("url", "")
                if img_url:
                    images.append({
                        "image_url": img_url,
                        "thumbnail": r.get("thumbnail", "") or img_url,
                        "source_url": r.get("foreign_landing_url", ""),
                        "title": r.get("title", ""),
                    })
            return images
        except (requests.exceptions.RequestException, OSError, ValueError, KeyError) as e:
            logger.log_warning(f"Openverse image search failed: {e}")
            return []

    def search_yahoo(self, query: str, num_results: int = 5) -> list[dict[str, str]]:
        """
        Search Yahoo and return scraped results
        """
        try:
            logger.log_action("Accessing global data grid", target=query)
            search_url = f"https://search.yahoo.com/search?p={requests.utils.quote(query)}"

            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # Find result containers. Yahoo periodically rotates its result CSS;
            # try the known variants in order so a single markup change does not
            # silently zero out the entire web-search pipeline.
            search_divs = soup.select('div.algo, div.algo-sr, div.Sr, li div.dd.algo')

            for div in search_divs[:num_results]:
                try:
                    # Title: 'h3.title' (classic) → any 'h3 a' → first algo anchor.
                    title_elem = (
                        div.find('h3', class_='title')
                        or div.find('h3')
                        or div.select_one('a.ac-algo-fst')
                    )
                    link_elem = (div.find('a', href=True) if title_elem is None
                                 else (title_elem.find('a', href=True) or div.find('a', href=True)))

                    if title_elem and link_elem:
                        href = link_elem.get('href', '')
                        real_url = href

                        # Yahoo wraps outbound links in a redirector containing RU=<encoded url>
                        if 'RU=' in href:
                            with contextlib.suppress(Exception):
                                real_url = urllib.parse.unquote(href.split('RU=')[1].split('/R')[0])

                        # Snippet: classic sibling of compTitle, else the comp text block.
                        snippet = ''
                        snippet_elem = div.find('div', class_='compTitle')
                        if snippet_elem and snippet_elem.find_next_sibling('div'):
                            snippet = snippet_elem.find_next_sibling('div').text.strip()
                        else:
                            alt = div.select_one('div.compText, p, .fc-falcon')
                            if alt:
                                snippet = alt.get_text(strip=True)

                        results.append({
                            'title': title_elem.get_text(strip=True),
                            'url': real_url,
                            'snippet': snippet
                        })
                except (AttributeError, ValueError, KeyError) as e:
                    logger.log_detail(f"Failed to parse search result: {e}")
                    continue

            if not results:
                logger.log_warning(
                    f"Yahoo yielded 0 parsable results for '{query}' — rerouting to DuckDuckGo."
                )
                return self._search_duckduckgo(query, num_results)

            logger.log_success(f"Extracted {len(results)} pertinent data packets.")
            return results

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as e:
            # Yahoo aggressively rate-limits/blocks scrapers (5xx). Never let a
            # single engine's block take down the whole search pipeline.
            logger.log_warning(f"Yahoo access failed ({e}) — rerouting to DuckDuckGo.")
            return self._search_duckduckgo(query, num_results)

    def _search_duckduckgo(self, query: str, num_results: int = 5) -> list[dict[str, str]]:
        """Fallback web search via DuckDuckGo's HTML endpoint (scraper-friendly).

        Invoked when Yahoo errors out or returns zero results so the search
        pipeline never goes fully dark on a single engine's block.
        """
        try:
            logger.log_action("Rerouting through alternate data grid (DuckDuckGo)", target=query)
            resp = self.session.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                timeout=10,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            results: list[dict[str, str]] = []

            for block in soup.select("div.result, div.web-result")[:num_results]:
                link = block.select_one("a.result__a")
                if not link:
                    continue
                href = link.get("href", "")
                # DDG sometimes wraps outbound links: //duckduckgo.com/l/?uddg=<encoded>
                if "uddg=" in href:
                    with contextlib.suppress(Exception):
                        href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
                snippet_el = block.select_one("a.result__snippet, .result__snippet")
                results.append({
                    "title": link.get_text(strip=True),
                    "url": href,
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })

            if results:
                logger.log_success(f"DuckDuckGo grid yielded {len(results)} data packet(s).")
            else:
                logger.log_warning(f"DuckDuckGo also returned 0 results for '{query}'.")
            return results

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError, KeyError) as e:
            logger.log_error(f"DuckDuckGo fallback failed: {e}")
            return []

    def _is_relevant(self, title: str, snippet: str, query: str, threshold: float = 0.85) -> bool:
        """
        Check if a search result is actually relevant to the target name.
        Uses stricter matching to avoid famous-name hallucinations.
        ``threshold`` controls the fuzzy cutoff (higher = stricter, used by deep search).
        """
        text = f"{title} {snippet}".lower()
        query = query.lower().strip()
        query_words = [w for w in query.split() if len(w) > 2]

        if not query_words:
            return query in text

        # 1. Exact Full Name Match (Highest confidence)
        if query in text:
            return True

        # 2. Split match check:
        # If the query is "Yiğit Erdoğan", we want BOTH "Yiğit" and "Erdoğan" to be present.
        # This prevents "Recep Tayyip Erdoğan" matching "Yiğit Erdoğan" just because of the surname.
        def normalize(t):
            return "".join(c for c in unicodedata.normalize('NFD', t.lower()) if unicodedata.category(c) != 'Mn')

        text_norm = normalize(text)
        query_words_norm = [normalize(w) for w in query_words]

        # All major components of the name must be present in the text
        if all(word in text_norm for word in query_words_norm):
            return True

        # 3. Fuzzy matching for typos (only if the query is unique enough)
        text_words = text_norm.split()
        matches_found = 0
        for word in query_words_norm:
            if word in text_norm or (len(word) >= 4 and difflib.get_close_matches(word, text_words, n=1, cutoff=threshold)):
                matches_found += 1

        # Require at least 80% of query words to match if they are not all present
        return matches_found >= len(query_words)

    def format_search_results(self, results: list[dict[str, str]]) -> str:
        """Format search results for AI context"""
        if not results:
            return "No search results found."

        formatted = ""
        for i, result in enumerate(results, 1):
            formatted += f"{i}. {result['title']}\n"
            formatted += f"   URL: {result['url']}\n"
            if result.get('snippet'):
                formatted += f"   {result['snippet']}\n"
            formatted += "\n"

        return formatted

    def fetch_content(self, url: str) -> str:
        """
        Fetch and clean the visible text from a URL for deep analysis.
        """
        # Skip social media domains as they are often blocked or need JS
        if any(domain in url.lower() for domain in ['instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'facebook.com']):
            return ""

        try:
            logger.log_thought(f"Infiltrating host and extracting raw data packets: {url}")
            response = self.session.get(url, timeout=12)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove noisy elements
            for element in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'form', 'button']):
                element.decompose()

            # Extract and sanitize text
            text = soup.get_text(separator=' ')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)

            return clean_text[:8000]  # Expanded for deeper analysis

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError) as e:
            logger.log_warning(f"Data packet extraction failed for {url}: {str(e)}")
            return ""

    def search_academic_publications(self, query: str) -> str:
        """
        Query Crossref and ORCID to find academic publications for a person.
        """
        academic_context = ""
        try:
            logger.log_action("Scanning academic networks (Crossref/ORCID)", target=query)

            # 1. ORCID Check (just to see if they are a registered researcher)
            orcid_url = f"https://pub.orcid.org/v3.0/search/?q={urllib.parse.quote(query)}"
            try:
                orcid_res = self.session.get(orcid_url, headers={'Accept': 'application/json'}, timeout=5)
                if orcid_res.status_code == 200:
                    orcid_data = orcid_res.json()
                    results = orcid_data.get('result', [])
                    if results:
                        academic_context += f"[ORCID] Verified researcher profile exists. Found {len(results)} potential ORCID matches.\n"
            except (requests.exceptions.RequestException, OSError, ValueError, KeyError) as e:
                logger.log_warning(f"Failed to query ORCID: {e}")

            # 2. Crossref API for Publications
            crossref_url = f"https://api.crossref.org/works?query.author={urllib.parse.quote(query)}&select=title,author,URL,published-print,publisher&rows=5"
            try:
                crossref_res = self.session.get(crossref_url, timeout=5)
                if crossref_res.status_code == 200:
                    cross_data = crossref_res.json()
                    items = cross_data.get('message', {}).get('items', [])

                    if items:
                        academic_context += "\n[Crossref] Top Academic Publications:\n"
                        for i, item in enumerate(items, 1):
                            title = item.get('title', ['Unknown Title'])[0]
                            publisher = item.get('publisher', 'Unknown Publisher')
                            url = item.get('URL', '')

                            # Try to extract year
                            year = "Unknown Date"
                            published_print = item.get('published-print', {})
                            if 'date-parts' in published_print and published_print['date-parts']:
                                year = str(published_print['date-parts'][0][0])

                            academic_context += f"  {i}. \"{title}\" ({year}) - {publisher}. URL: {url}\n"
                    else:
                        academic_context += "\n[Crossref] No major publications found under this exact name.\n"
            except (requests.exceptions.RequestException, OSError, ValueError, KeyError) as e:
                logger.log_warning(f"Failed to query Crossref: {e}")

            if academic_context:
                logger.log_success("Academic intelligence retrieved.")
            return academic_context

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError) as e:
            logger.log_warning(f"Academic sweep failed: {e}")
            return ""

    def search_patents(self, query: str) -> str:
        """
        Query patent databases to find technical patents for a person.
        We'll use a basic Google Patents search via Yahoo for simplicity and reliability,
        as PatentsView is highly specific to US patents and often requires strict formatting.
        """
        try:
            logger.log_action("Scanning patent registries", target=query)
            # Use yahoo to search specifically inside patents.google.com
            patent_query = f"site:patents.google.com inventor \"{query}\""
            results = self.search_yahoo(patent_query, num_results=3)

            patent_context = ""
            if results:
                patent_context += "\n[Patent Registries] Registered Patents / Inventions:\n"
                for i, res in enumerate(results, 1):
                    # Clean up title (Google Patents usually returns 'US1234567B2 - Title...')
                    title = res['title'].replace(' - Google Patents', '')
                    patent_context += f"  {i}. {title}\n"
                    patent_context += f"     URL: {res['url']}\n"

                logger.log_success("Patent intelligence retrieved.")
            return patent_context

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError) as e:
            logger.log_warning(f"Patent sweep failed: {e}")
            return ""

    def search_official_registries(self, query: str) -> str:
        """
        Query public corporate registry databases (OpenCorporates, Companies House, etc.)
        for business links, directorships, or founder statuses, bypassing API key requirements.
        """
        try:
            logger.log_action("Scanning global corporate registries", target=query)

            # Combine major open registries into one Dork search
            registry_query = f"(site:opencorporates.com OR site:find-and-update.company-information.service.gov.uk) \"{query}\""
            results = self.search_yahoo(registry_query, num_results=4)

            official_context = ""
            if results:
                official_context += "\n[Official Registries] Corporate Footprint & Directorships:\n"
                for i, res in enumerate(results, 1):
                    # Clean up the output titles for neat presentation
                    title = res['title'].replace(' - OpenCorporates', '')
                    title = title.replace(' - Find and update company information - GOV.UK', '')

                    official_context += f"  {i}. {title}\n"
                    if res.get('snippet'):
                        official_context += f"     Info: {res['snippet']}\n"
                    official_context += f"     URL: {res['url']}\n\n"

                logger.log_success("Corporate intelligence retrieved.")
            return official_context

        except (requests.exceptions.RequestException, OSError, AttributeError, ValueError) as e:
            logger.log_warning(f"Corporate registry sweep failed: {e}")
            return ""

    def search_person(self, name: str, depth_config=None) -> tuple[str, str, str, list[dict[str, str]]]:
        """
        Search for a person and return (wiki_image_url, formatted_results, deep_context, raw_results).
        ``depth_config`` (DepthConfig | None) scales query count, scrape budget, and relevance strictness.
        """
        logger.log_thought(f"Initiating cross-reference protocol for entity: {name}")

        # Resolve depth parameters
        if depth_config:
            num_queries = depth_config.num_query_variations
            max_scrapes = depth_config.max_deep_scrapes
            relevance_threshold = depth_config.relevance_threshold
            query_delay = depth_config.query_delay_seconds
            tier = depth_config.tier
        else:
            num_queries = 5
            max_scrapes = 4
            relevance_threshold = 0.85
            query_delay = 1.0
            tier = "medium"

        # 1. Fetch visual identity from Wikipedia first
        wiki_image = self.search_wikipedia_image(name)

        # 2. Search with diverse queries — count scales with depth
        base_queries = [
            f"{name} biography OR education",
            f"{name} career OR profession",
            f"{name} interview OR news",
            f"{name} profile",
            f"{name}",
        ]
        deep_queries = [
            f'"{name}" university OR degree OR school',
            f'"{name}" award OR achievement OR recognition',
            f'"{name}" CEO OR founder OR director',
            f'"{name}" controversy OR criticism',
            f'"{name}" blog OR personal site OR portfolio',
            f'"{name}" conference OR speaker OR panel',
            f'"{name}" publication OR paper OR research',
        ]

        # Select queries based on depth
        queries = base_queries[:num_queries]
        if num_queries > len(base_queries):
            queries.extend(deep_queries[:num_queries - len(base_queries)])

        logger.log_thought(f"Search tier: {tier} — firing {len(queries)} query variation(s)")

        all_results = []
        seen_urls = set()
        for query in queries:
            logger.log_action(f"Scanning subspace for: {query}")
            results = self.search_yahoo(query, num_results=5)
            # Deduplicate results by URL and filter irrelevant ones
            for r in results:
                if r['url'] not in seen_urls and self._is_relevant(
                    r.get('title', ''), r.get('snippet', ''), name,
                    threshold=relevance_threshold,
                ):
                    seen_urls.add(r['url'])
                    all_results.append(r)
            logger.log_thought(f"Extracted {len(all_results)} verified data nodes so far.")
            time.sleep(query_delay)

        # 3. Deep-Scraping Protocol: Extract full content from top relevant links
        logger.log_action("Executing deep-packet inspection on primary sources...")
        logger.log_thought(f"Filtering nodes for high-density information (budget: {max_scrapes})...")
        deep_context = ""
        scrapable_results = [
            r for r in all_results
            if not any(d in r['url'].lower() for d in [
                'instagram.com', 'twitter.com', 'x.com',
                'linkedin.com', 'facebook.com', 'youtube.com',
            ])
        ][:max_scrapes]

        for res in scrapable_results:
            parsed_url = urllib.parse.urlparse(res['url'])
            hostname = parsed_url.hostname if parsed_url.scheme and parsed_url.netloc else res['url']
            logger.log_action(f"Infiltrating NODE: {hostname}")
            content = self.fetch_content(res['url'])
            if content:
                deep_context += f"--- NODE: {res['url']} ---\n{content}\n\n"
                logger.log_success(f"Packet integrity verified for {res['url']}")

        logger.log_success("Data aggregation and content synthesis complete.")

        formatted_text = self.format_search_results(all_results)

        return wiki_image, formatted_text, deep_context, all_results

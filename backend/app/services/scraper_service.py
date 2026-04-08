import contextlib
import random
import re
import time
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.depth_config import DepthConfig

import requests
from bs4 import BeautifulSoup

from app.utils.logger import logger


class ScraperService:
    """Service for scraping social media profiles"""

    _USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15',
    ]

    _CB_THRESHOLD = 5  # Skip a search engine after this many consecutive failures

    def __init__(self):
        self.session = requests.Session()
        self._ua_index = 0
        self.session.headers.update({
            'User-Agent': self._USER_AGENTS[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        # Circuit breaker counters — skip engines after consecutive failures
        self._google_fails = 0
        self._yahoo_fails = 0
        self._ddg_fails = 0
        self._bing_fails = 0
        self._brave_fails = 0
        self._startpage_fails = 0
        self._last_request_time = 0.0
        self._search_count = 0  # Total searches in current session

    def _is_url_active(self, url: str) -> bool:
        """Check if a URL is active (returns 200 OK and isn't a known error/login page)"""
        try:
            response = self.session.get(url, timeout=7, allow_redirects=True)

            # 403/429 = bot-blocked but profile likely exists
            if response.status_code in (403, 429):
                return True

            if response.status_code != 200:
                return False

            # If the final URL contains 'login' or 'accounts/login', it's likely restricted/dead
            if "login" in response.url.lower() and "login" not in url.lower():
                return False

            # Check for common 'not found' signatures in content (first 5KB for speed)
            content_snippet = response.text[:5000].lower()
            not_found_signatures = [
                "page not found",
                "this page isn't available",
                "doesn't exist",
                "user not found",
                "account not found",
                "not a valid user",
                "content is currently unavailable",
                "could not be found",
                "no longer available",
                "expired",
                "nobody on reddit goes by that name",
            ]

            return not any(sig in content_snippet for sig in not_found_signatures)
        except Exception:
            return False

    def _rotate_user_agent(self):
        """Rotate User-Agent and set realistic browser headers to reduce blocking."""
        self._ua_index = (self._ua_index + 1) % len(self._USER_AGENTS)
        ua = self._USER_AGENTS[self._ua_index]
        is_firefox = 'Firefox' in ua
        is_safari = 'Safari' in ua and 'Chrome' not in ua and 'Chromium' not in ua
        self.session.headers.update({
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' if is_firefox else 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Upgrade-Insecure-Requests': '1',
        })
        if not is_firefox and not is_safari:
            # Chromium browsers send Client Hints — their absence is a bot signal
            chrome_match = re.search(r'Chrome/(\d+)', ua)
            edge_match = re.search(r'Edg/(\d+)', ua)
            major = chrome_match.group(1) if chrome_match else '134'
            if edge_match:
                edge_major = edge_match.group(1)
                ch_ua = f'"Microsoft Edge";v="{edge_major}", "Chromium";v="{major}", "Not-A.Brand";v="8"'
            else:
                ch_ua = f'"Chromium";v="{major}", "Google Chrome";v="{major}", "Not-A.Brand";v="8"'
            is_mac = 'Macintosh' in ua
            self.session.headers.update({
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'sec-ch-ua': ch_ua,
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"' if is_mac else '"Windows"',
            })
        else:
            # Firefox and Safari don't send Client Hints or Sec-Fetch
            for key in ('Sec-Fetch-Dest', 'Sec-Fetch-Mode', 'Sec-Fetch-Site',
                        'Sec-Fetch-User', 'sec-ch-ua', 'sec-ch-ua-mobile',
                        'sec-ch-ua-platform'):
                self.session.headers.pop(key, None)

    def _all_engines_broken(self) -> bool:
        """True when every search engine has tripped its circuit breaker."""
        return (self._google_fails >= self._CB_THRESHOLD
                and self._yahoo_fails >= self._CB_THRESHOLD
                and self._ddg_fails >= self._CB_THRESHOLD
                and self._bing_fails >= self._CB_THRESHOLD
                and self._brave_fails >= self._CB_THRESHOLD
                and self._startpage_fails >= self._CB_THRESHOLD)

    def _extract_urls_from_google(self, query: str, domain_pattern: str, max_results: int = 3) -> list:
        """Search via Google HTML results."""
        try:
            self._rotate_user_agent()
            self.session.cookies.clear()
            self.session.headers['Referer'] = 'https://www.google.com/'
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num=10&hl=en"
            response = self.session.get(search_url, timeout=15)

            if response.status_code != 200:
                self._google_fails += 1
                logger.log_warning(f"Google returned status {response.status_code}")
                return []

            # Detect consent/captcha page
            if 'consent.google.com' in response.url or 'sorry/index' in response.url:
                self._google_fails += 1
                logger.log_warning("Google consent/captcha page detected (URL redirect)")
                return []

            # Also detect in-page blocking (captcha/cookie notice in body)
            body_lower = response.text[:3000].lower()
            blocking_signals = [
                'our systems have detected unusual traffic',
                'please show you',
                'recaptcha',
                'g-recaptcha',
                'before you continue to google',
                'consent.google',
            ]
            if any(sig in body_lower for sig in blocking_signals):
                self._google_fails += 1
                logger.log_warning("Google blocking detected (in-page signal)")
                return []

            self._google_fails = 0
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # Primary: <div class="g"> containers
            for item in soup.find_all('div', class_='g'):
                link = item.find('a', href=True)
                if not link:
                    continue
                href = link.get('href', '')
                # Google sometimes wraps URLs in /url?q= redirects
                if href.startswith('/url?q='):
                    try:
                        href = urllib.parse.unquote(href.split('/url?q=')[1].split('&')[0])
                    except IndexError:
                        continue
                if href.startswith('http') and re.search(domain_pattern, href, re.IGNORECASE) and not any(r['url'] == href for r in results):
                    snippet = ""
                    # Try multiple known snippet selectors
                    snippet_elem = (item.find('div', class_='VwiC3b')
                                    or item.find('span', class_='aCOpRe')
                                    or item.find('div', attrs={'style': lambda s: s and '-webkit-line-clamp' in str(s)}))
                    if snippet_elem:
                        snippet = snippet_elem.get_text(strip=True)[:200]
                    results.append({"url": href, "bio": snippet})
                if len(results) >= max_results:
                    break

            # Fallback: scan all <a> tags
            if not results:
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if href.startswith('/url?q='):
                        try:
                            href = urllib.parse.unquote(href.split('/url?q=')[1].split('&')[0])
                        except IndexError:
                            continue
                    if (href.startswith('http')
                            and re.search(domain_pattern, href, re.IGNORECASE)
                            and 'google.com' not in href
                            and 'googleapis.com' not in href
                            and not any(r['url'] == href for r in results)):
                        results.append({"url": href, "bio": ""})
                    if len(results) >= max_results:
                        break

            if results:
                logger.log_success(f"Google found {len(results)} result(s) for: {query}")
            return results

        except Exception as e:
            self._google_fails += 1
            logger.log_error(f"Google search failed for {query}: {e}")
            return []

    def _extract_urls_from_duckduckgo(self, query: str, domain_pattern: str, max_results: int = 3) -> list:
        """Fallback search via DuckDuckGo HTML when Yahoo fails."""
        try:
            self._rotate_user_agent()
            self.session.cookies.clear()
            self.session.headers['Referer'] = 'https://duckduckgo.com/'
            search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            response = self.session.get(search_url, timeout=15)

            if response.status_code != 200:
                self._ddg_fails += 1
                logger.log_warning(f"DuckDuckGo returned status {response.status_code}")
                return []

            self._ddg_fails = 0
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # DuckDuckGo HTML uses class 'result__a' for result links
            for link in soup.find_all('a', class_='result__a', href=True):
                href = link.get('href', '')
                if 'uddg=' in href:
                    try:
                        actual_url = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
                    except IndexError:
                        continue
                else:
                    actual_url = href

                if re.search(domain_pattern, actual_url, re.IGNORECASE) and not any(r['url'] == actual_url for r in results):
                    snippet_elem = link.find_parent('div')
                    snippet = ""
                    if snippet_elem:
                        snippet_text = snippet_elem.find('a', class_='result__snippet')
                        if snippet_text:
                            snippet = snippet_text.text.strip()
                    results.append({"url": actual_url, "bio": snippet})
                if len(results) >= max_results:
                    break

            # Fallback: scan all links if class-based search found nothing
            if not results:
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    actual_url = href
                    if 'uddg=' in href:
                        try:
                            actual_url = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
                        except IndexError:
                            continue
                    if actual_url.startswith('http') and re.search(domain_pattern, actual_url, re.IGNORECASE) and not any(r['url'] == actual_url for r in results):
                        results.append({"url": actual_url, "bio": ""})
                    if len(results) >= max_results:
                        break

            if results:
                logger.log_success(f"DuckDuckGo fallback found {len(results)} result(s) for: {query}")
            return results

        except Exception as e:
            self._ddg_fails += 1
            logger.log_error(f"DuckDuckGo fallback failed for {query}: {e}")
            return []

    def _extract_urls_from_bing(self, query: str, domain_pattern: str, max_results: int = 3) -> list:
        """Third fallback search via Bing when Yahoo and DuckDuckGo both fail."""
        try:
            self._rotate_user_agent()
            self.session.cookies.clear()
            self.session.headers['Referer'] = 'https://www.bing.com/'
            search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
            response = self.session.get(search_url, timeout=15)

            if response.status_code != 200:
                self._bing_fails += 1
                logger.log_warning(f"Bing returned status {response.status_code}")
                return []

            self._bing_fails = 0
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # Primary: <li class="b_algo"> containers
            items = soup.find_all('li', class_='b_algo')
            if not items:
                items = soup.find_all('li', class_=lambda c: c and 'b_algo' in c)

            for item in items:
                link = item.find('a', href=True)
                if not link:
                    continue
                href = link.get('href', '')
                if href.startswith('http') and re.search(domain_pattern, href, re.IGNORECASE) and not any(r['url'] == href for r in results):
                    snippet = ""
                    snippet_elem = item.find('p') or item.find('div', class_='b_caption')
                    if snippet_elem:
                        snippet = snippet_elem.text.strip()[:200]
                    results.append({"url": href, "bio": snippet})
                if len(results) >= max_results:
                    break

            # Fallback: scan all <a> tags
            if not results:
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if href.startswith('http') and re.search(domain_pattern, href, re.IGNORECASE) and 'bing.com' not in href and 'microsoft.com' not in href and not any(r['url'] == href for r in results):
                        results.append({"url": href, "bio": ""})
                    if len(results) >= max_results:
                        break

            if results:
                logger.log_success(f"Bing fallback found {len(results)} result(s) for: {query}")
            return results

        except Exception as e:
            self._bing_fails += 1
            logger.log_error(f"Bing fallback failed for {query}: {e}")
            return []

    def _extract_urls_from_brave(self, query: str, domain_pattern: str, max_results: int = 3) -> list:
        """Search via Brave Search HTML results. Brave is less aggressive with blocking."""
        try:
            self._rotate_user_agent()
            self.session.cookies.clear()
            self.session.headers['Referer'] = 'https://search.brave.com/'
            search_url = f"https://search.brave.com/search?q={urllib.parse.quote(query)}&source=web"
            response = self.session.get(search_url, timeout=15)

            if response.status_code != 200:
                self._brave_fails += 1
                logger.log_warning(f"Brave returned status {response.status_code}")
                return []

            self._brave_fails = 0
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # Primary: Brave uses <div class="snippet"> for result containers
            for item in soup.find_all('div', class_=lambda c: c and ('snippet' in c if isinstance(c, str) else any('snippet' in cls for cls in c))):
                link = item.find('a', href=True)
                if not link:
                    continue
                href = link.get('href', '')
                if href.startswith('http') and re.search(domain_pattern, href, re.IGNORECASE) and not any(r['url'] == href for r in results):
                    snippet = ""
                    snippet_elem = item.find('div', class_=lambda c: c and ('snippet-description' in str(c) or 'description' in str(c)))
                    if not snippet_elem:
                        snippet_elem = item.find('p')
                    if snippet_elem:
                        snippet = snippet_elem.get_text(strip=True)[:200]
                    results.append({"url": href, "bio": snippet})
                if len(results) >= max_results:
                    break

            # Fallback: scan all <a> tags
            if not results:
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if (href.startswith('http')
                            and re.search(domain_pattern, href, re.IGNORECASE)
                            and 'brave.com' not in href
                            and not any(r['url'] == href for r in results)):
                        results.append({"url": href, "bio": ""})
                    if len(results) >= max_results:
                        break

            if results:
                logger.log_success(f"Brave found {len(results)} result(s) for: {query}")
            return results

        except Exception as e:
            self._brave_fails += 1
            logger.log_error(f"Brave search failed for {query}: {e}")
            return []

    def _throttle_request(self) -> None:
        """Add a small random delay between search requests to avoid rate limiting."""
        self._search_count += 1
        now = time.time()
        elapsed = now - self._last_request_time
        # Reduced delay: fast enough to finish in time, slow enough to avoid blocks
        base_delay = 0.4 + (self._search_count * 0.02)  # 0.4s → 0.6s over 10 searches
        min_delay = max(0.2, base_delay - 0.2)
        max_delay = min(1.5, base_delay + 0.3)
        target_delay = random.uniform(min_delay, max_delay)
        if elapsed < target_delay:
            time.sleep(target_delay - elapsed)
        self._last_request_time = time.time()

    def _reset_circuit_breakers(self) -> None:
        """Reset all circuit breaker counters for a fresh search session.
        Also clears cookies and rotates UA to reduce tracking-based blocking."""
        self._google_fails = 0
        self._yahoo_fails = 0
        self._ddg_fails = 0
        self._bing_fails = 0
        self._brave_fails = 0
        self._startpage_fails = 0
        self._search_count = 0
        self.session.cookies.clear()
        self._rotate_user_agent()

    def _search_all_engines(self, query: str, domain_pattern: str, max_results: int = 3) -> list:
        """Search Google → DuckDuckGo → Brave → Bing → Yahoo with circuit-breaker.
        Engines that have failed consecutively are skipped automatically.
        Order prioritizes less-aggressive-blocking engines as fallbacks."""
        logger.log_action("Scanning global networks for targeted node", target=query)
        results: list = []

        self._throttle_request()

        # --- Google (primary) ---------------------------------------------
        if not results and self._google_fails < self._CB_THRESHOLD:
            results = self._extract_urls_from_google(query, domain_pattern, max_results)

        # --- Startpage (Google proxy, no captcha) -------------------------
        if not results and self._startpage_fails < self._CB_THRESHOLD:
            time.sleep(random.uniform(0.1, 0.4))
            results = self._extract_urls_from_startpage(query, domain_pattern, max_results)

        # --- DuckDuckGo fallback (lenient, scraper-friendly) ---------------
        if not results and self._ddg_fails < self._CB_THRESHOLD:
            time.sleep(random.uniform(0.1, 0.4))
            results = self._extract_urls_from_duckduckgo(query, domain_pattern, max_results)

        # --- Brave fallback (privacy-focused, less blocking) ---------------
        if not results and self._brave_fails < self._CB_THRESHOLD:
            time.sleep(random.uniform(0.1, 0.4))
            results = self._extract_urls_from_brave(query, domain_pattern, max_results)

        # --- Bing fallback ------------------------------------------------
        if not results and self._bing_fails < self._CB_THRESHOLD:
            time.sleep(random.uniform(0.1, 0.4))
            results = self._extract_urls_from_bing(query, domain_pattern, max_results)

        # --- Yahoo fallback -----------------------------------------------
        if not results and self._yahoo_fails < self._CB_THRESHOLD:
            time.sleep(random.uniform(0.1, 0.4))
            results = self._extract_urls_from_yahoo(query, domain_pattern, max_results)

        if results:
            logger.log_success(f"Search found {len(results)} result(s) for: {query}")

        return results

    def _extract_urls_from_yahoo(self, query: str, domain_pattern: str, max_results: int = 3) -> list:
        """Search via Yahoo HTML results."""
        try:
            self._rotate_user_agent()
            self.session.cookies.clear()
            self.session.headers['Referer'] = 'https://search.yahoo.com/'
            search_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}"

            response = self.session.get(search_url, timeout=15)

            if response.status_code != 200:
                self._yahoo_fails += 1
                logger.log_warning(f"Yahoo returned status {response.status_code} for query: {query}")
                return []

            self._yahoo_fails = 0
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # Attempt 1: Primary selector
            items = soup.find_all('div', class_='algo')

            # Attempt 2: Class contains 'algo'
            if not items:
                items = soup.find_all('div', class_=lambda c: c and 'algo' in c)

            # Attempt 3: Any result-like container with data-bk attribute
            if not items:
                items = soup.find_all(['li', 'div'], attrs={'data-bk': True})

            # Attempt 4: Search result containers (Sr class)
            if not items:
                items = soup.find_all('div', class_=lambda c: c and ('Sr' in c or 'dd' in c or 'searchCenterMiddle' in c))

            if items:
                for item in items:
                    link_elem = item.find('a', href=True)
                    snippet_elem = item.find('div', class_='compTitle')

                    if not link_elem:
                        continue

                    href = link_elem.get('href', '')
                    try:
                        actual_url = None
                        if 'RU=' in href:
                            actual_url = urllib.parse.unquote(href.split('RU=')[1].split('/R')[0])
                        elif href.startswith('http') and re.search(domain_pattern, href, re.IGNORECASE):
                            actual_url = href

                        if actual_url and re.search(domain_pattern, actual_url, re.IGNORECASE):
                            if not any(r['url'] == actual_url for r in results):
                                snippet = ""
                                sibling = snippet_elem.find_next_sibling('div') if snippet_elem else None
                                if sibling:
                                    snippet = sibling.text.strip()
                                results.append({"url": actual_url, "bio": snippet})
                            if len(results) >= max_results:
                                break
                    except IndexError:
                        pass

            # Fallback: Extract ALL <a> tags and filter by domain pattern
            if not results:
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href', '')
                    actual_url = None
                    if 'RU=' in href:
                        with contextlib.suppress(IndexError):
                            actual_url = urllib.parse.unquote(href.split('RU=')[1].split('/R')[0])
                    elif href.startswith('http') and re.search(domain_pattern, href, re.IGNORECASE):
                        actual_url = href

                    if actual_url and re.search(domain_pattern, actual_url, re.IGNORECASE):
                        if not any(r['url'] == actual_url for r in results):
                            results.append({"url": actual_url, "bio": ""})
                        if len(results) >= max_results:
                            break

            if results:
                logger.log_success(f"Yahoo found {len(results)} result(s) for: {query}")
            return results

        except Exception as e:
            self._yahoo_fails += 1
            logger.log_error(f"Yahoo search failed for {query}: {e}")
            return []

    def _extract_urls_from_startpage(self, query: str, domain_pattern: str, max_results: int = 3) -> list:
        """Search via Startpage — proxies Google results without CAPTCHAs."""
        try:
            self._rotate_user_agent()
            self.session.cookies.clear()
            self.session.headers['Referer'] = 'https://www.startpage.com/'
            search_url = f"https://www.startpage.com/do/dsearch?query={urllib.parse.quote(query)}&cat=web"
            response = self.session.get(search_url, timeout=15)

            if response.status_code != 200:
                self._startpage_fails += 1
                logger.log_warning(f"Startpage returned status {response.status_code}")
                return []

            self._startpage_fails = 0
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # Primary: Startpage result links
            for link in soup.find_all('a', class_=lambda c: c and ('result-link' in str(c) or 'w-gl__result-url' in str(c)), href=True):
                href = link.get('href', '')
                if href.startswith('http') and re.search(domain_pattern, href, re.IGNORECASE) and not any(r['url'] == href for r in results):
                    snippet = ""
                    parent = link.find_parent('div', class_=lambda c: c and 'result' in str(c))
                    if parent:
                        snippet_elem = parent.find('p', class_=lambda c: c and 'description' in str(c))
                        if not snippet_elem:
                            snippet_elem = parent.find('p')
                        if snippet_elem:
                            snippet = snippet_elem.get_text(strip=True)[:200]
                    results.append({"url": href, "bio": snippet})
                if len(results) >= max_results:
                    break

            # Fallback: scan all <a> tags
            if not results:
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if (href.startswith('http')
                            and re.search(domain_pattern, href, re.IGNORECASE)
                            and 'startpage.com' not in href
                            and not any(r['url'] == href for r in results)):
                        results.append({"url": href, "bio": ""})
                    if len(results) >= max_results:
                        break

            if results:
                logger.log_success(f"Startpage found {len(results)} result(s) for: {query}")
            return results

        except Exception as e:
            self._startpage_fails += 1
            logger.log_error(f"Startpage search failed for {query}: {e}")
            return []

    INSTAGRAM_RESERVED_PATHS = {
        'p', 'reel', 'reels', 'explore', 'tags', 'accounts',
        'stories', 'tv', 'direct', 'ar', 'about', 'legal',
        'developer', 'security', 'privacy', 'help', 'press'
    }

    @staticmethod
    def _ascii_name(name: str) -> str:
        """Normalize Turkish/diacritical chars to ASCII (ğ→g, ö→o, ş→s, etc.)"""
        nfkd = unicodedata.normalize('NFD', name.strip())
        return nfkd.encode('ascii', errors='ignore').decode().strip()

    def _platform_queries(self, name: str, site_pattern: str, extra_terms: str = '', max_queries: int = 3) -> list[str]:
        """Build an ordered list of search queries for a platform.
        Handles both full names and usernames; adds ASCII variant for Turkish names.
        max_queries limits how many queries are returned to control total search time."""
        is_username = ' ' not in name.strip() and len(name.strip()) >= 3
        ascii = self._ascii_name(name)
        queries: list[str] = []
        if is_username:
            # For usernames: site-specific search is most reliable
            queries.append(f'site:{site_pattern}/{name.strip()}')
            if extra_terms:
                queries.append(f'@{name.strip()} {extra_terms}')
        else:
            # For full names: try ASCII variant first (Turkish names), then quoted name
            if ascii and ascii.lower() != name.lower():
                queries.append(f'"{ascii}" site:{site_pattern}')
            queries.append(f'"{name}" site:{site_pattern}')
            if len(queries) < max_queries:
                bare = ascii if ascii and ascii.lower() != name.lower() else name
                queries.append(f'{bare} {extra_terms or site_pattern}')
        return queries[:max_queries]

    def find_instagram_profile(self, name: str) -> list:
        """Try to find Instagram profile URLs and bios"""
        pattern = r'instagram\.com/([a-zA-Z0-9._]+)'
        valid_profiles = []
        for query in self._platform_queries(name, 'instagram.com', 'instagram'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match and match.group(1).lower() not in self.INSTAGRAM_RESERVED_PATHS:
                    u = f"https://www.instagram.com/{match.group(1)}/"
                    if not any(p['url'] == u for p in valid_profiles):
                        valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    TWITTER_NON_PROFILE = {
        'home', 'login', 'logout', 'signup', 'intent', 'i',
        'settings', 'privacy', 'notifications', 'messages',
        'explore', 'search', 'hashtag', 'trending', 'en', 'news',
        'status', 'share', 'tos', 'rules', 'about', 'help',
        'download', 'compose', 'who_to_follow', 'lists', 'moments',
        'bookmarks', 'communities', 'spaces', 'premium',
    }

    def find_twitter_profile(self, name: str) -> list:
        """Try to find X (Twitter) profile URLs and bios."""
        pattern = r'(twitter|x)\.com/([a-zA-Z0-9_]+)'
        valid_profiles = []
        for query in self._platform_queries(name, 'x.com', 'twitter'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    username = match.group(2)
                    if (username.lower() not in self.TWITTER_NON_PROFILE
                            and 1 <= len(username) <= 15):
                        u = f"https://x.com/{username}"
                        if not any(p['url'] == u for p in valid_profiles):
                            valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_linkedin_profile(self, name: str) -> list:
        """Try to find LinkedIn profile URLs and bios"""
        pattern = r'linkedin\.com/in/([a-zA-Z0-9-]+)'
        valid_profiles = []
        for query in self._platform_queries(name, 'linkedin.com/in', 'linkedin'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    u = f"https://www.linkedin.com/in/{match.group(1)}/"
                    if not any(p['url'] == u for p in valid_profiles):
                        valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_spotify_profile(self, name: str) -> list:
        """Try to find Spotify profile URLs and bios"""
        query = f'"{name}" spotify'
        items = self._search_all_engines(query, r'open\.spotify\.com/(user|artist)/([a-zA-Z0-9._-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'open\.spotify\.com/(user|artist)/([a-zA-Z0-9._-]+)', url)
            if match:
                u = f"https://open.spotify.com/{match.group(1)}/{match.group(2)}"
                if not any(p['url'] == u for p in valid_profiles):
                    valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_tiktok_profile(self, name: str) -> list:
        """Try to find TikTok profile URLs and bios"""
        pattern = r'tiktok\.com/@([a-zA-Z0-9._-]+)'
        valid_profiles = []
        for query in self._platform_queries(name, 'tiktok.com', 'tiktok'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    u = f"https://www.tiktok.com/@{match.group(1)}"
                    if not any(p['url'] == u for p in valid_profiles):
                        valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_snapchat_profile(self, name: str) -> list:
        """Try to find Snapchat profile URLs via Yahoo search"""
        pattern = r'snapchat\.com/add/([a-zA-Z0-9._-]+)'
        valid_profiles = []
        for query in self._platform_queries(name, 'snapchat.com/add', 'snapchat'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    u = f"https://www.snapchat.com/add/{match.group(1)}"
                    if not any(p['url'] == u for p in valid_profiles):
                        valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_tumblr_profile(self, name: str) -> list:
        """Try to find Tumblr profile URLs via Yahoo search"""
        pattern = r'([a-zA-Z0-9_-]+)\.tumblr\.com'
        excluded_subdomains = {'www', 'assets', 'media', 'support', 'staff', 'engineering'}
        valid_profiles = []
        is_username = ' ' not in name.strip()
        queries = self._platform_queries(name, 'tumblr.com', 'tumblr')
        if is_username:
            queries.insert(0, f'"{name.strip()}.tumblr.com"')
        for query in queries:
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    subdomain = match.group(1)
                    if subdomain.lower() not in excluded_subdomains:
                        u = f"https://{subdomain}.tumblr.com"
                        if not any(p['url'] == u for p in valid_profiles):
                            valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_youtube_profile(self, name: str) -> list:
        """Try to find YouTube channel URLs via Yahoo search"""
        pattern = r'youtube\.com/(?:@|c/|user/)([a-zA-Z0-9._-]+)'
        valid_profiles = []
        for query in self._platform_queries(name, 'youtube.com', 'youtube channel'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(r'youtube\.com/(@[a-zA-Z0-9._-]+|c/[a-zA-Z0-9._-]+|user/[a-zA-Z0-9._-]+)', url)
                if match:
                    handle = match.group(1)
                    u = f"https://www.youtube.com/{handle}"
                    if not any(p['url'] == u for p in valid_profiles):
                        valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_reddit_profile(self, name: str) -> list:
        """Try to find Reddit user profile URLs via Yahoo search"""
        pattern = r'reddit\.com/u(?:ser)?/([a-zA-Z0-9_-]+)'
        excluded = {'search', 'submit', 'login', 'register', 'wiki'}
        valid_profiles = []
        for query in self._platform_queries(name, 'reddit.com/user', 'reddit'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    username = match.group(1)
                    if username.lower() not in excluded:
                        u = f"https://www.reddit.com/user/{username}"
                        if not any(p['url'] == u for p in valid_profiles):
                            valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_facebook_profile(self, name: str) -> list:
        """Try to find Facebook profile URLs via Yahoo search"""
        pattern = r'facebook\.com/([a-zA-Z0-9._-]+)'
        excluded = {'pages', 'groups', 'events', 'watch', 'login', 'sharer', 'share',
                    'dialog', 'permalink', 'photo', 'video', 'story', 'plugins', 'ads'}
        valid_profiles = []
        for query in self._platform_queries(name, 'facebook.com', 'facebook profile'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    segment = match.group(1)
                    if segment.lower() not in excluded:
                        u = f"https://www.facebook.com/{segment}"
                        if not any(p['url'] == u for p in valid_profiles):
                            valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_pinterest_profile(self, name: str) -> list:
        """Try to find Pinterest profile URLs via Yahoo search"""
        pattern = r'pinterest\.com/([a-zA-Z0-9._-]+)'
        excluded = {'pin', 'search', 'explore', 'ideas', 'today', 'business', 'about', 'settings', 'news_hub', 'login', 'signup'}
        valid_profiles = []
        for query in self._platform_queries(name, 'pinterest.com', 'pinterest'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    segment = match.group(1)
                    if segment.lower() not in excluded:
                        u = f"https://www.pinterest.com/{segment}/"
                        if not any(p['url'] == u for p in valid_profiles):
                            valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_medium_profile(self, name: str) -> list:
        """Try to find Medium profile URLs via Yahoo search"""
        pattern = r'medium\.com/@([a-zA-Z0-9._-]+)'
        excluded = {'about', 'policy', 'creators', 'membership', 'topics', 'tag', 'search'}
        valid_profiles = []
        for query in self._platform_queries(name, 'medium.com', 'medium'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    username = match.group(1)
                    if username.lower() not in excluded:
                        u = f"https://medium.com/@{username}"
                        if not any(p['url'] == u for p in valid_profiles):
                            valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_threads_profile(self, name: str) -> list:
        """Try to find Threads (Meta) profile URLs via Yahoo search"""
        pattern = r'threads\.net/@([a-zA-Z0-9._]+)'
        valid_profiles = []
        for query in self._platform_queries(name, 'threads.net', 'threads'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    u = f"https://www.threads.net/@{match.group(1)}"
                    if not any(p['url'] == u for p in valid_profiles):
                        valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_steam_profile(self, name: str) -> list:
        """Try to find Steam profile URLs via Yahoo search"""
        pattern = r'steamcommunity\.com/id/([a-zA-Z0-9._-]+)'
        valid_profiles = []
        for query in self._platform_queries(name, 'steamcommunity.com/id', 'steam'):
            items = self._search_all_engines(query, pattern)
            for item in items:
                url = item['url']
                match = re.search(pattern, url)
                if match:
                    u = f"https://steamcommunity.com/id/{match.group(1)}"
                    if not any(p['url'] == u for p in valid_profiles):
                        valid_profiles.append({"url": u, "bio": item['bio']})
            if len(valid_profiles) >= 3:
                break
        return valid_profiles[:3]

    def find_discord_mention(self, name: str) -> list:
        """Search for Discord mentions — profiles are private, only detect references"""
        query = f'"{name}" discord server OR profile'
        items = self._search_all_engines(query, r'discord', max_results=2)
        mentions = []
        for item in items:
            snippet = item.get('bio', '').strip()
            if snippet and 'discord' in snippet.lower():
                mentions.append({"url": item['url'], "bio": f"[Mention] {snippet[:200]}"})
        return mentions

    def find_tinder_mention(self, name: str) -> list:
        """Search for Tinder mentions — profiles are private, only detect references"""
        query = f'"{name}" tinder profile'
        items = self._search_all_engines(query, r'tinder', max_results=2)
        mentions = []
        for item in items:
            snippet = item.get('bio', '').strip()
            if snippet and 'tinder' in snippet.lower():
                mentions.append({"url": item['url'], "bio": f"[Mention] {snippet[:200]}"})
        return mentions

    def find_bumble_mention(self, name: str) -> list:
        """Search for Bumble mentions — profiles are private, only detect references"""
        query = f'"{name}" bumble profile'
        items = self._search_all_engines(query, r'bumble', max_results=2)
        mentions = []
        for item in items:
            snippet = item.get('bio', '').strip()
            if snippet and 'bumble' in snippet.lower():
                mentions.append({"url": item['url'], "bio": f"[Mention] {snippet[:200]}"})
        return mentions

    def extract_phone_numbers(self, name: str, deep_context: str) -> list:
        """
        Extract phone numbers from deep web context using regex.
        Supports international formats: +90 555 123 4567, (555) 123-4567, etc.
        """
        if not deep_context:
            return []

        phone_patterns = [
            r'\+?\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{2,4}',  # International
            r'\(\d{3}\)[\s.-]?\d{3}[\s.-]?\d{4}',                              # US (555) 123-4567
            r'\b0\d{3}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b',               # TR 0555 123 45 67
        ]

        found = set()
        name_lower = name.lower()

        # Only extract from lines that seem contextually related to the target name
        for line in deep_context.split('\n'):
            line_lower = line.lower()
            # Proximity check: line should contain part of the name or be near contact info
            name_parts = [w for w in name_lower.split() if len(w) > 2]
            has_name_context = any(part in line_lower for part in name_parts)
            has_contact_keyword = any(kw in line_lower for kw in ['phone', 'tel', 'call', 'contact', 'mobile', 'cell', 'telefon', 'iletişim', 'numara', 'gsm', 'cep'])

            if has_name_context or has_contact_keyword:
                for pattern in phone_patterns:
                    matches = re.findall(pattern, line)
                    for m in matches:
                        cleaned = re.sub(r'[\s.()-]', '', m)
                        # Filter: must be 7-15 digits, not look like a year or ID
                        digits_only = re.sub(r'\D', '', cleaned)
                        if 7 <= len(digits_only) <= 15 and not (len(digits_only) == 4 and digits_only.startswith('20')):
                            found.add(m.strip())

        result = list(found)[:5]  # Cap to 5 numbers
        if result:
            logger.log_success(f"Phone numbers extracted: {len(result)} found")
        return result

    def generate_username_variations(self, username: str) -> list[str]:
        """Generate smart username variations for cross-platform discovery.
        Returns ordered list of unique variants (excluding original), max 15."""
        # Normalize to ASCII (diacritics: ğ→g, ı→i, ş→s, ç→c, ö→o, ü→u, etc.)
        nfkd = unicodedata.normalize('NFD', username.lower())
        base = nfkd.encode('ascii', errors='ignore').decode()

        candidates: list[str] = []
        seen: set[str] = {username.lower(), base if base == username.lower() else ''}

        def _add(s: str) -> None:
            s = s.strip().lower()
            if len(s) >= 3 and s not in seen:
                seen.add(s)
                candidates.append(s)

        # If diacritic-normalized form differs from original, add it first
        if base != username.lower():
            _add(base)

        # Strip trailing repeated characters: "Yigtwxx" → "Yigtwx"
        stripped = re.sub(r'(.)\1+$', r'\1', base)
        _add(stripped)

        # Double last character: "yigtwx" → "yigtwxx"
        if len(base) >= 3:
            _add(base + base[-1])
        if stripped != base and len(stripped) >= 3:
            _add(stripped + stripped[-1])

        # Strip trailing digits: "johndoe123" → "johndoe"
        no_digits = re.sub(r'\d+$', '', base)
        _add(no_digits)
        if no_digits:
            _add(re.sub(r'(.)\1+$', r'\1', no_digits))  # dedup after stripping digits too

        # Append common digit suffixes: "yigtwx" → "yigtwx1", "yigtwx2"
        for d in ['1', '2', '0', '99', '_']:
            _add(base + d)
            if no_digits and no_digits != base:
                _add(no_digits + d)

        # Separator swaps: . ↔ _ ↔ - ↔ (none)
        separators = ['.', '_', '-']
        for sep in separators:
            if sep in base:
                parts = base.split(sep)
                for repl in separators:
                    if repl != sep:
                        _add(repl.join(parts))
                _add(''.join(parts))

        # Strip common suffixes
        for suffix in ['_official', '_real', '_tv', '_yt', '_ig', 'official', 'real']:
            if base.endswith(suffix) and len(base) - len(suffix) >= 3:
                _add(base[:-len(suffix)])

        return candidates[:15]

    def generate_name_username_variations(self, full_name: str) -> list[str]:
        """Generate username candidates from a full real name (e.g. 'Yağmur Özgan').
        Produces concatenated, dot/underscore-separated, consonant-stripped, and
        truncated forms — covering common social-media username conventions."""
        ascii_name = self._ascii_name(full_name)
        parts = [p for p in ascii_name.split() if p]
        if not parts:
            return []

        candidates: list[str] = []
        seen: set[str] = set()

        def _add(s: str) -> None:
            s = s.strip().lower()
            if len(s) >= 3 and s not in seen:
                seen.add(s)
                candidates.append(s)

        first = parts[0]
        last = parts[-1] if len(parts) > 1 else ''

        if last:
            _add(first + last)                    # yagmurozgan
            _add(first + '.' + last)              # yagmur.ozgan
            _add(first + '_' + last)              # yagmur_ozgan
            _add(last + first)                    # ozganyagmur
            _add(last + '.' + first)              # ozgan.yagmur
            _add(first + last[0])                 # yagmuro
            _add(first[0] + last)                 # yozgan
            # Drop vowels from both parts (common in Turkish usernames: yamurzgn)
            vowels = set('aeiou')
            cf = ''.join(c for c in first if c not in vowels)
            cl = ''.join(c for c in last if c not in vowels)
            if len(cf + cl) >= 4:
                _add(cf + cl)                     # ygmrzgn
                _add(cf + '_' + cl)               # ygmr_zgn
            # Truncated forms
            if len(first) > 4:
                _add(first[:4] + last)            # yagmozgan
            if len(last) > 3:
                _add(first + last[:3])            # yagmurozg
            # With digit suffix
            _add(first + last + '1')
            _add(first + last + '_')
        else:
            _add(first)

        # Also add the raw non-ASCII-stripped form (Turkish chars stripped directly)
        raw_strip = re.sub(r'[^a-zA-Z0-9]', '', full_name.strip().lower())
        if raw_strip and len(raw_strip) >= 3 and raw_strip not in seen:
            candidates.insert(0, raw_strip)
            seen.add(raw_strip)

        return candidates[:15]

    def find_all_profiles(self, name: str, depth_config: 'DepthConfig | None' = None) -> dict[str, list]:
        """Find all social media profiles and bios for a person (PARALLEL)
        depth_config controls search effort — lower depth = fewer queries = faster results."""
        logger.log_thought(f"Initiating deep-web scraping protocol for entity: {name}")
        logger.log_action(f"[DIAG] find_all_profiles v4 — name={name}")

        # Time budget: ensures search always completes within a reasonable time
        depth = depth_config.depth if depth_config else 5
        time_budget = {1: 30, 2: 40, 3: 50, 4: 60, 5: 75, 6: 90, 7: 120, 8: 150, 9: 180, 10: 210}.get(depth, 75)
        start_time = time.time()
        max_queries_per_platform = 2 if depth <= 5 else 3
        max_name_variations = min(3, depth_config.max_username_variations if depth_config else 5)
        max_cross_variations = min(5, depth_config.max_username_variations if depth_config else 5)

        def _time_remaining() -> float:
            return max(0.0, time_budget - (time.time() - start_time))

        def _budget_exhausted() -> bool:
            return _time_remaining() <= 0

        # Reset circuit breakers for each new search session
        self._reset_circuit_breakers()

        # Determine if input looks like a username (no spaces)
        input_is_username = ' ' not in name.strip() and len(name.strip()) >= 3

        platform_fns = {
            'instagram': self.find_instagram_profile,
            'twitter': self.find_twitter_profile,
            'linkedin': self.find_linkedin_profile,
            'spotify': self.find_spotify_profile,
            'tiktok': self.find_tiktok_profile,
            'snapchat': self.find_snapchat_profile,
            'tumblr': self.find_tumblr_profile,
            'youtube': self.find_youtube_profile,
            'reddit': self.find_reddit_profile,
            'facebook': self.find_facebook_profile,
            'pinterest': self.find_pinterest_profile,
            'medium': self.find_medium_profile,
            'threads': self.find_threads_profile,
            'steam': self.find_steam_profile,
            'tinder': self.find_tinder_mention,
            'bumble': self.find_bumble_mention,
            'discord': self.find_discord_mention,
        }

        profiles: dict[str, list] = {k: [] for k in platform_fns}

        # Phase 1: Search-based discovery + direct username probe run in parallel
        # Use limited workers (6) to prevent bursts that trigger rate limiting
        DIRECT_TAG = '__direct_username_probe__'
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(fn, name): platform for platform, fn in platform_fns.items()}

            # If input looks like a username, also probe it directly on every platform
            if input_is_username:
                clean_name = name.strip()
                logger.log_action(f"Direct username probe: @{clean_name}")
                futures[executor.submit(self.find_profiles_by_username, clean_name)] = DIRECT_TAG

            direct_hits: dict[str, list] = {}
            try:
                for future in as_completed(futures, timeout=60):
                    tag = futures[future]
                    try:
                        result = future.result()
                        if tag == DIRECT_TAG:
                            direct_hits = result
                        else:
                            profiles[tag] = result
                            if result:
                                label = "mention" if tag in ('tinder', 'bumble') else "profile"
                                logger.log_success(f"{tag.capitalize()} {label} correlated: {len(result)} found")
                    except Exception as e:
                        if tag == DIRECT_TAG:
                            logger.log_warning(f"Direct username probe failed: {e}")
                        else:
                            logger.log_warning(f"{tag.capitalize()} scan failed: {e}")
            except TimeoutError:
                logger.log_warning("Phase 1 scraper executor timed out (60s) — returning partial results")

        # Merge direct username hits into profiles (don't overwrite Yahoo results, add new ones)
        for platform, items in direct_hits.items():
            if items:
                existing_urls = {p['url'] for p in profiles.get(platform, [])}
                for item in items:
                    if item['url'] not in existing_urls:
                        profiles.setdefault(platform, []).append(item)
                if profiles.get(platform):
                    logger.log_success(f"{platform.capitalize()} direct-hit confirmed: @{name.strip()}")

        # Phase 1.5: For real names, probe name-derived username variations via platform search fns.
        # Reset circuit breakers after Phase 1 — engines may have recovered
        found_count_p1 = sum(1 for v in profiles.values() if v)
        SEARCH_PLATFORMS = ('instagram', 'twitter', 'tiktok', 'youtube', 'reddit', 'linkedin', 'threads', 'medium', 'snapchat', 'tumblr', 'pinterest', 'steam')

        if found_count_p1 < 3 and not _budget_exhausted():
            logger.log_action("Resetting search engine circuits for Phase 1.5 discovery...")
            self._reset_circuit_breakers()
            time.sleep(random.uniform(0.3, 0.8))  # Brief cooldown before next wave

        # This runs BEFORE the standard username cross-check so that discovered usernames
        # feed into Phase 2 collection below.
        if not input_is_username and not self._all_engines_broken() and not _budget_exhausted():
            name_unames = self.generate_name_username_variations(name)
            logger.log_action(f"Generated {len(name_unames)} name-based username candidate(s), using top {max_name_variations}")
            for uname in name_unames[:max_name_variations]:
                if _budget_exhausted():
                    logger.log_warning(f"Time budget exhausted ({time_budget}s), skipping remaining Phase 1.5 variations")
                    break
                empty = [p for p in SEARCH_PLATFORMS if not profiles.get(p)]
                if not empty:
                    break
                logger.log_action(f"Probing name-derived username @{uname}")
                # Search each empty platform using its own search function (not blind URL build)
                with ThreadPoolExecutor(max_workers=min(len(empty), 6)) as ex:
                    fut_map = {ex.submit(platform_fns[p], uname): p for p in empty if p in platform_fns}
                    try:
                        for fut in as_completed(fut_map, timeout=30):
                            platform = fut_map[fut]
                            try:
                                results = fut.result()
                                if results and not profiles.get(platform):
                                    for item in results:
                                        item['found_via_name_variation'] = uname
                                    profiles[platform] = results
                                    logger.log_success(f"{platform.capitalize()} matched via name-derived @{uname}")
                            except Exception as e:
                                logger.log_warning(f"{platform} probe for @{uname} failed: {e}")
                    except TimeoutError:
                        logger.log_warning(f"Phase 1.5 scraper timed out (30s) for @{uname}")

        # Phase 2: Collect all found usernames + the input itself
        collected_usernames: list[str] = []
        seen_unames: set[str] = set()

        if _budget_exhausted():
            logger.log_warning(f"Time budget exhausted ({time_budget}s), skipping Phase 2 entirely")
        else:
            # Always add input as a username candidate (if it looks like one)
            if input_is_username:
                raw = name.strip().lower()
                nfkd = unicodedata.normalize('NFD', raw)
                ascii_form = nfkd.encode('ascii', errors='ignore').decode()
                for candidate in [raw, ascii_form]:
                    if candidate and len(candidate) >= 3 and candidate not in seen_unames:
                        collected_usernames.append(candidate)
                        seen_unames.add(candidate)

            # Collect usernames from found profiles
            for platform in ['instagram', 'tiktok', 'twitter', 'youtube', 'reddit', 'snapchat', 'tumblr', 'linkedin', 'pinterest', 'medium', 'threads', 'steam']:
                items = profiles.get(platform, [])
                if items:
                    # Skip search fallback URLs — they don't contain real usernames
                    if items[0].get('bio') == '[SEARCH]':
                        continue
                    url = items[0]['url'].rstrip('/')
                    # Tumblr uses subdomains (username.tumblr.com), not path-based URLs
                    if platform == 'tumblr' and '.tumblr.com' in url:
                        m = re.search(r'//([a-zA-Z0-9_-]+)\.tumblr\.com', url)
                        candidate = m.group(1).lower() if m else ''
                    else:
                        candidate = url.split('/')[-1].lstrip('@').lower()
                    if candidate and len(candidate) >= 3 and candidate not in seen_unames:
                        collected_usernames.append(candidate)
                        seen_unames.add(candidate)

            # Build variation list from ALL collected usernames (input + found profiles)
            all_variations: list[str] = []
            seen_vars: set[str] = set(seen_unames)
            for uname in collected_usernames:
                for var in self.generate_username_variations(uname):
                    if var not in seen_vars:
                        all_variations.append(var)
                        seen_vars.add(var)
                        if len(all_variations) >= max_cross_variations:
                            break
                if len(all_variations) >= max_cross_variations:
                    break

            # Exact cross-check for every collected username on empty platforms
            for uname in collected_usernames:
                if _budget_exhausted():
                    logger.log_warning(f"Time budget exhausted, stopping cross-platform checks")
                    break
                empty = [p for p in ('instagram','tiktok','twitter','youtube','reddit','snapchat','tumblr','linkedin','pinterest','medium','threads','steam')
                         if not profiles.get(p)]
                if not empty:
                    break
                logger.log_action(f"Cross-platform username check for: @{uname}")
                cross = self.find_profiles_by_username(uname)
                for platform, results in cross.items():
                    if results and not profiles.get(platform):
                        profiles[platform] = results
                        logger.log_success(f"{platform.capitalize()} cross-matched via username @{uname}")

            # Variation checks — only for platforms still without results
            if all_variations and not self._all_engines_broken() and not _budget_exhausted():
                logger.log_action(f"Scanning {len(all_variations)} username variation(s) across uncovered platforms")
                for var in all_variations:
                    if _budget_exhausted():
                        logger.log_warning(f"Time budget exhausted, stopping variation scan")
                        break
                    empty = [p for p in ('instagram','tiktok','twitter','youtube','reddit','snapchat','tumblr','linkedin','pinterest','medium','threads','steam')
                             if not profiles.get(p)]
                    if empty:
                        cross = self.find_profiles_by_username(var)
                        for platform, results in cross.items():
                            if results and not profiles.get(platform):
                                for item in results:
                                    item['found_via_variation'] = var
                                profiles[platform] = results
                                logger.log_success(f"{platform.capitalize()} matched via variation @{var}")
                    else:
                        break

        # Last resort: if still nothing found for a real name, search key platforms
        # using the simple ASCII-stripped username — via search functions (NOT blind URL build)
        found_count = sum(1 for v in profiles.values() if v)
        if found_count == 0 and not input_is_username and not self._all_engines_broken() and not _budget_exhausted():
            fallback_username = re.sub(r'[^a-zA-Z0-9]', '', name.strip().lower())
            if len(fallback_username) >= 3:
                logger.log_action(f"Last resort search for @{fallback_username}")
                for platform in ('instagram', 'twitter', 'tiktok', 'youtube'):
                    if _budget_exhausted():
                        break
                    fn = platform_fns.get(platform)
                    if fn and not profiles.get(platform):
                        try:
                            results = fn(fallback_username)
                            if results:
                                for item in results:
                                    item['found_via_fallback'] = True
                                profiles[platform] = results
                                logger.log_success(f"{platform.capitalize()} fallback found: @{fallback_username}")
                        except Exception as e:
                            logger.log_warning(f"Fallback {platform} search failed: {e}")

        # Inject platform search URLs for platforms that returned no results
        search_urls = self._platform_search_urls(name)
        for platform, search_url in search_urls.items():
            if not profiles.get(platform):
                profiles[platform] = [{"url": search_url, "bio": "[SEARCH]"}]
                logger.log_action(f"Search fallback injected for {platform}")

        elapsed = time.time() - start_time
        found_final = sum(1 for v in profiles.values() if v)
        logger.log_success(f"Profile scan completed in {elapsed:.1f}s — {found_final} platform(s) found")
        return profiles

    @staticmethod
    def _platform_search_urls(name: str) -> dict[str, str]:
        """Generate platform-specific search URLs for a given name."""
        encoded = urllib.parse.quote(name)
        return {
            'instagram':  f"https://www.google.com/search?q=site:instagram.com+{encoded}",
            'twitter':    f"https://x.com/search?q={encoded}&f=user",
            'linkedin':   f"https://www.linkedin.com/search/results/people/?keywords={encoded}",
            'spotify':    f"https://open.spotify.com/search/{encoded}",
            'tiktok':     f"https://www.tiktok.com/search/user?q={encoded}",
            'snapchat':   f"https://www.snapchat.com/add/{encoded}",
            'tumblr':     f"https://www.tumblr.com/search/{encoded}",
            'youtube':    f"https://www.youtube.com/results?search_query={encoded}",
            'reddit':     f"https://www.reddit.com/search/?q={encoded}&type=user",
            'facebook':   f"https://www.facebook.com/search/people/?q={encoded}",
            'pinterest':  f"https://www.pinterest.com/search/users/?q={encoded}",
            'medium':     f"https://medium.com/search?q={encoded}",
            'threads':    f"https://www.threads.net/search?q={encoded}&serp_type=default",
            'steam':      f"https://steamcommunity.com/search/users/#text={encoded}",
        }

    def _is_instagram_username_valid(self, username: str) -> bool:
        """Check Instagram username format validity. Not used for profile discovery
        (format-only validation creates false positives); retained as a utility helper."""
        return (
            3 <= len(username) <= 30
            and bool(re.match(r'^[a-zA-Z0-9._]+$', username))
            and username.lower() not in self.INSTAGRAM_RESERVED_PATHS
        )

    def find_profiles_by_username(self, username: str) -> dict[str, list]:
        """
        Verify a username via HTTP check on platforms that support it.

        Non-verifiable platforms (Instagram, Twitter/X, TikTok, Snapchat) always
        return empty — they cannot be HTTP-checked (login redirects, 403s, SPAs)
        and format-only validation creates false positives.  These platforms are
        discovered exclusively via search-based methods in Phase 1 and Phase 1.5.

        Returns dict matching find_all_profiles format.
        """
        results: dict[str, list] = {}

        # Instagram: _is_url_active always fails (login redirect) and format-only
        # validation creates false positives.  Rely on search-based discovery
        # (Phase 1 / Phase 1.5) which returns real, indexed profile URLs.
        results['instagram'] = []

        # Twitter/X: always returns 403 for bots, so HTTP verification is
        # impossible.  Same rationale as Instagram — search-based discovery only.
        results['twitter'] = []

        # HTTP-verified platforms: only accept if URL actually resolves to an existing profile.
        # Run verifications in parallel to minimise latency.
        verifiable = {
            'youtube':   f"https://www.youtube.com/@{username}",
            'reddit':    f"https://www.reddit.com/user/{username}",
            'medium':    f"https://medium.com/@{username}",
            'pinterest': f"https://www.pinterest.com/{username}/",
            'tumblr':    f"https://{username}.tumblr.com",
            'steam':     f"https://steamcommunity.com/id/{username}",
            'linkedin':  f"https://www.linkedin.com/in/{username}/",
            'threads':   f"https://www.threads.net/@{username}",
        }

        with ThreadPoolExecutor(max_workers=len(verifiable)) as ex:
            fut_map = {ex.submit(self._is_url_active, url): (platform, url)
                       for platform, url in verifiable.items()}
            try:
                for fut in as_completed(fut_map, timeout=30):
                    platform, url = fut_map[fut]
                    try:
                        if fut.result():
                            results[platform] = [{"url": url, "bio": ""}]
                            logger.log_success(f"{platform.capitalize()} URL verified: @{username}")
                        else:
                            results[platform] = []
                            logger.log_warning(f"{platform.capitalize()} URL inactive for @{username}")
                    except Exception as exc:
                        results[platform] = []
                        logger.log_warning(f"{platform.capitalize()} verification error for @{username}: {exc}")
            except TimeoutError:
                logger.log_warning(f"URL verification timed out (30s) for @{username}")

        # TikTok and Snapchat: SPA rendering makes HTTP verification unreliable.
        # Rely on Phase 1 / Phase 1.5 search-based discovery for these platforms.
        results['tiktok'] = []
        results['snapchat'] = []

        return results

    def fetch_avatar_from_url(self, url: str) -> str | None:
        """Extract og:image avatar from a public social media profile page."""
        try:
            resp = self.session.get(url, timeout=8, allow_redirects=True)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, 'html.parser')
            tag = soup.find('meta', property='og:image')
            if not tag:
                tag = soup.find('meta', attrs={'name': 'twitter:image'})
            img_url = tag.get('content', '').strip() if tag else ''
            return img_url if img_url.startswith('http') else None
        except Exception:
            return None

    def format_social_profiles(self, profiles: dict[str, list]) -> str:
        """Format social media profiles and their bios for AI context"""
        formatted = "Social Media Profiles and Bios:\n"

        found_any = False
        for platform, items in profiles.items():
            if items:
                found_any = True
                label = "MENTION" if platform in ('tinder', 'bumble', 'discord') else platform.upper()
                formatted += f"[{label}: {platform.upper()}]\n"
                for item in items:
                    formatted += f"- URL: {item['url']}\n"
                    if item.get('bio'):
                        formatted += f"  Bio/Snippet: {item['bio']}\n"
                formatted += "\n"

        if not found_any:
            formatted += "No social media profiles found.\n"

        return formatted

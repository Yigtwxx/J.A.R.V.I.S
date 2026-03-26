import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
from app.utils.logger import logger
import re
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed


class ScraperService:
    """Service for scraping social media profiles"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

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
                "sorry, this page isn't available",
                "doesn't exist",
                "user not found",
                "account not found",
                "not a valid user",
                "content is currently unavailable",
                "expired"
            ]

            if any(sig in content_snippet for sig in not_found_signatures):
                return False

            return True
        except Exception:
            return False

    def _extract_urls_from_yahoo(self, query: str, domain_pattern: str, max_results: int = 3) -> list:
        """Helper to search Yahoo and extract domain URLs with snippets/bios"""
        results = []
        try:
            logger.log_action("Scanning global networks for targeted node", target=query)
            search_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}"

            response = self.session.get(search_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Attempt 1: Primary selector
            items = soup.find_all('div', class_='algo')

            # Attempt 2: Class contains 'algo'
            if not items:
                items = soup.find_all('div', class_=lambda c: c and 'algo' in c)

            # Attempt 3: Any result-like container with data-bk attribute
            if not items:
                items = soup.find_all(['li', 'div'], attrs={'data-bk': True})

            if items:
                for item in items:
                    link_elem = item.find('a', href=True)
                    snippet_elem = item.find('div', class_='compTitle')

                    if not link_elem:
                        continue

                    href = link_elem.get('href', '')
                    try:
                        if 'RU=' in href:
                            actual_url = urllib.parse.unquote(href.split('RU=')[1].split('/R')[0])
                            if re.search(domain_pattern, actual_url, re.IGNORECASE):
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
            else:
                # Fallback: Extract ALL <a> tags and filter by domain pattern
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href', '')
                    if 'RU=' in href:
                        try:
                            actual_url = urllib.parse.unquote(href.split('RU=')[1].split('/R')[0])
                            if re.search(domain_pattern, actual_url, re.IGNORECASE):
                                if not any(r['url'] == actual_url for r in results):
                                    results.append({"url": actual_url, "bio": ""})
                                if len(results) >= max_results:
                                    break
                        except IndexError:
                            pass

            return results

        except Exception as e:
            logger.log_error(f"Network scan failed during {query} extraction: {e}")
            return []

    INSTAGRAM_RESERVED_PATHS = {
        'p', 'reel', 'reels', 'explore', 'tags', 'accounts',
        'stories', 'tv', 'direct', 'ar', 'about', 'legal',
        'developer', 'security', 'privacy', 'help', 'press'
    }

    def find_instagram_profile(self, name: str) -> list:
        """Try to find Instagram profile URLs and bios"""
        query = f'"{name}" instagram profile'
        items = self._extract_urls_from_yahoo(query, r'instagram\.com/([a-zA-Z0-9._]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'instagram\.com/([a-zA-Z0-9._]+)', url)
            if match and match.group(1).lower() not in self.INSTAGRAM_RESERVED_PATHS:
                u = f"https://www.instagram.com/{match.group(1)}/"
                if not any(p['url'] == u for p in valid_profiles):
                    valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    TWITTER_NON_PROFILE = {
        'home', 'login', 'logout', 'signup', 'intent', 'i',
        'settings', 'privacy', 'notifications', 'messages',
        'explore', 'search', 'hashtag', 'trending', 'en', 'news',
        'status', 'share', 'tos', 'rules', 'about', 'help',
        'download', 'compose', 'who_to_follow', 'lists', 'moments',
        'bookmarks', 'communities', 'spaces', 'premium',
    }

    def find_twitter_profile(self, name: str) -> list:
        """Try to find X (Twitter) profile URLs and bios.
        X.com blocks all bot requests with 403, so _is_url_active always
        returns True regardless of whether the profile exists.  We rely on
        Yahoo site-search instead (same approach as Instagram).
        """
        query = f'site:x.com "{name}"'
        items = self._extract_urls_from_yahoo(query, r'(twitter|x)\.com/([a-zA-Z0-9_]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'(twitter|x)\.com/([a-zA-Z0-9_]+)', url)
            if match:
                username = match.group(2)
                if (username.lower() not in self.TWITTER_NON_PROFILE
                        and 1 <= len(username) <= 15):
                    u = f"https://x.com/{username}"
                    if not any(p['url'] == u for p in valid_profiles):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_linkedin_profile(self, name: str) -> list:
        """Try to find LinkedIn profile URLs and bios"""
        query = f'"{name}" linkedin'
        items = self._extract_urls_from_yahoo(query, r'linkedin\.com/in/([a-zA-Z0-9-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'linkedin\.com/in/([a-zA-Z0-9-]+)', url)
            if match:
                u = f"https://www.linkedin.com/in/{match.group(1)}/"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_spotify_profile(self, name: str) -> list:
        """Try to find Spotify profile URLs and bios"""
        query = f'"{name}" spotify'
        items = self._extract_urls_from_yahoo(query, r'open\.spotify\.com/(user|artist)/([a-zA-Z0-9._-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'open\.spotify\.com/(user|artist)/([a-zA-Z0-9._-]+)', url)
            if match:
                u = f"https://open.spotify.com/{match.group(1)}/{match.group(2)}"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_tiktok_profile(self, name: str) -> list:
        """Try to find TikTok profile URLs and bios"""
        query = f'"{name}" tiktok'
        items = self._extract_urls_from_yahoo(query, r'tiktok\.com/@([a-zA-Z0-9._-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'tiktok\.com/@([a-zA-Z0-9._-]+)', url)
            if match:
                u = f"https://www.tiktok.com/@{match.group(1)}"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_snapchat_profile(self, name: str) -> list:
        """Try to find Snapchat profile URLs via Yahoo search"""
        query = f'"{name}" snapchat'
        items = self._extract_urls_from_yahoo(query, r'snapchat\.com/add/([a-zA-Z0-9._-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'snapchat\.com/add/([a-zA-Z0-9._-]+)', url)
            if match:
                u = f"https://www.snapchat.com/add/{match.group(1)}"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_tumblr_profile(self, name: str) -> list:
        """Try to find Tumblr profile URLs via Yahoo search"""
        query = f'"{name}" tumblr'
        items = self._extract_urls_from_yahoo(query, r'([a-zA-Z0-9_-]+)\.tumblr\.com')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'([a-zA-Z0-9_-]+)\.tumblr\.com', url)
            if match:
                subdomain = match.group(1)
                if subdomain.lower() in ['www', 'assets', 'media', 'support', 'staff', 'engineering']:
                    continue
                u = f"https://{subdomain}.tumblr.com"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_youtube_profile(self, name: str) -> list:
        """Try to find YouTube channel URLs via Yahoo search"""
        query = f'"{name}" youtube channel'
        items = self._extract_urls_from_yahoo(query, r'youtube\.com/(?:@|c/|user/)([a-zA-Z0-9._-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'youtube\.com/(@[a-zA-Z0-9._-]+|c/[a-zA-Z0-9._-]+|user/[a-zA-Z0-9._-]+)', url)
            if match:
                handle = match.group(1)
                u = f"https://www.youtube.com/{handle}"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_reddit_profile(self, name: str) -> list:
        """Try to find Reddit user profile URLs via Yahoo search"""
        query = f'"{name}" reddit'
        items = self._extract_urls_from_yahoo(query, r'reddit\.com/u(?:ser)?/([a-zA-Z0-9_-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'reddit\.com/u(?:ser)?/([a-zA-Z0-9_-]+)', url)
            if match:
                username = match.group(1)
                if username.lower() in ['search', 'submit', 'login', 'register', 'wiki']:
                    continue
                u = f"https://www.reddit.com/user/{username}"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_facebook_profile(self, name: str) -> list:
        """Try to find Facebook profile URLs via Yahoo search"""
        query = f'"{name}" facebook profile'
        items = self._extract_urls_from_yahoo(query, r'facebook\.com/([a-zA-Z0-9._-]+)')
        excluded = {'pages', 'groups', 'events', 'watch', 'login', 'sharer', 'share',
                    'dialog', 'permalink', 'photo', 'video', 'story', 'plugins', 'ads'}
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'facebook\.com/([a-zA-Z0-9._-]+)', url)
            if match:
                segment = match.group(1)
                if segment.lower() in excluded:
                    continue
                u = f"https://www.facebook.com/{segment}"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_pinterest_profile(self, name: str) -> list:
        """Try to find Pinterest profile URLs via Yahoo search"""
        query = f'"{name}" pinterest'
        items = self._extract_urls_from_yahoo(query, r'pinterest\.com/([a-zA-Z0-9._-]+)')
        excluded = {'pin', 'search', 'explore', 'ideas', 'today', 'business', 'about', 'settings', 'news_hub'}
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'pinterest\.com/([a-zA-Z0-9._-]+)', url)
            if match:
                segment = match.group(1)
                if segment.lower() in excluded:
                    continue
                u = f"https://www.pinterest.com/{segment}/"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_medium_profile(self, name: str) -> list:
        """Try to find Medium profile URLs via Yahoo search"""
        query = f'"{name}" medium.com'
        items = self._extract_urls_from_yahoo(query, r'medium\.com/@([a-zA-Z0-9._-]+)')
        excluded = {'about', 'policy', 'creators', 'membership', 'topics', 'tag', 'search'}
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'medium\.com/@([a-zA-Z0-9._-]+)', url)
            if match:
                username = match.group(1)
                if username.lower() in excluded:
                    continue
                u = f"https://medium.com/@{username}"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_threads_profile(self, name: str) -> list:
        """Try to find Threads (Meta) profile URLs via Yahoo search"""
        query = f'"{name}" threads.net'
        items = self._extract_urls_from_yahoo(query, r'threads\.net/@([a-zA-Z0-9._]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'threads\.net/@([a-zA-Z0-9._]+)', url)
            if match:
                username = match.group(1)
                u = f"https://www.threads.net/@{username}"
                if not any(p['url'] == u for p in valid_profiles):
                    valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_steam_profile(self, name: str) -> list:
        """Try to find Steam profile URLs via Yahoo search"""
        query = f'"{name}" steamcommunity.com'
        items = self._extract_urls_from_yahoo(query, r'steamcommunity\.com/id/([a-zA-Z0-9._-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'steamcommunity\.com/id/([a-zA-Z0-9._-]+)', url)
            if match:
                username = match.group(1)
                u = f"https://steamcommunity.com/id/{username}"
                if not any(p['url'] == u for p in valid_profiles):
                    if self._is_url_active(u):
                        valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_discord_mention(self, name: str) -> list:
        """Search for Discord mentions — profiles are private, only detect references"""
        query = f'"{name}" discord server OR profile'
        items = self._extract_urls_from_yahoo(query, r'discord', max_results=2)
        mentions = []
        for item in items:
            snippet = item.get('bio', '').strip()
            if snippet and 'discord' in snippet.lower():
                mentions.append({"url": item['url'], "bio": f"[Mention] {snippet[:200]}"})
        return mentions

    def find_tinder_mention(self, name: str) -> list:
        """Search for Tinder mentions — profiles are private, only detect references"""
        query = f'"{name}" tinder profile'
        items = self._extract_urls_from_yahoo(query, r'tinder', max_results=2)
        mentions = []
        for item in items:
            snippet = item.get('bio', '').strip()
            if snippet and 'tinder' in snippet.lower():
                mentions.append({"url": item['url'], "bio": f"[Mention] {snippet[:200]}"})
        return mentions

    def find_bumble_mention(self, name: str) -> list:
        """Search for Bumble mentions — profiles are private, only detect references"""
        query = f'"{name}" bumble profile'
        items = self._extract_urls_from_yahoo(query, r'bumble', max_results=2)
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

    def find_all_profiles(self, name: str) -> Dict[str, list]:
        """Find all social media profiles and bios for a person (PARALLEL)"""
        logger.log_thought(f"Initiating deep-web scraping protocol for entity: {name}")

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

        profiles: Dict[str, list] = {k: [] for k in platform_fns}

        # Phase 1: Yahoo searches + direct username probe run in parallel
        DIRECT_TAG = '__direct_username_probe__'
        with ThreadPoolExecutor(max_workers=18) as executor:
            futures = {executor.submit(fn, name): platform for platform, fn in platform_fns.items()}

            # If input looks like a username, also probe it directly on every platform
            if input_is_username:
                clean_name = name.strip()
                logger.log_action(f"Direct username probe: @{clean_name}")
                futures[executor.submit(self.find_profiles_by_username, clean_name)] = DIRECT_TAG

            direct_hits: Dict[str, list] = {}
            for future in as_completed(futures):
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

        # Merge direct username hits into profiles (don't overwrite Yahoo results, add new ones)
        for platform, items in direct_hits.items():
            if items:
                existing_urls = {p['url'] for p in profiles.get(platform, [])}
                for item in items:
                    if item['url'] not in existing_urls:
                        profiles.setdefault(platform, []).append(item)
                if profiles.get(platform):
                    logger.log_success(f"{platform.capitalize()} direct-hit confirmed: @{name.strip()}")

        # Phase 2: Collect all found usernames + the input itself
        collected_usernames: list[str] = []
        seen_unames: set[str] = set()

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
                url = items[0]['url'].rstrip('/')
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
                    if len(all_variations) >= 15:
                        break
            if len(all_variations) >= 15:
                break

        # Exact cross-check for every collected username on empty platforms
        for uname in collected_usernames:
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
        if all_variations:
            logger.log_action(f"Scanning {len(all_variations)} username variation(s) across uncovered platforms")
            for var in all_variations:
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

        return profiles

    def _is_instagram_username_valid(self, username: str) -> bool:
        """Instagram doesn't allow _is_url_active (login redirect). Validate format instead."""
        return (
            3 <= len(username) <= 30
            and bool(re.match(r'^[a-zA-Z0-9._]+$', username))
            and username.lower() not in self.INSTAGRAM_RESERVED_PATHS
        )

    def find_profiles_by_username(self, username: str) -> Dict[str, list]:
        """
        Directly verify a username across all major platforms by constructing
        the profile URL and checking if it is active.
        Returns dict matching find_all_profiles format.
        """
        # Instagram: _is_url_active always fails (login redirect) — use format validation
        ig_url = f"https://www.instagram.com/{username}/"
        results: Dict[str, list] = {}
        if self._is_instagram_username_valid(username):
            results['instagram'] = [{"url": ig_url, "bio": ""}]
            logger.log_success(f"Instagram username candidate accepted: @{username}")
        else:
            results['instagram'] = []

        # Twitter/X: _is_url_active always returns True (403 bot-block) — use format validation
        if (1 <= len(username) <= 15
                and re.match(r'^[a-zA-Z0-9_]+$', username)
                and username.lower() not in self.TWITTER_NON_PROFILE):
            results['twitter'] = [{"url": f"https://x.com/{username}", "bio": ""}]
            logger.log_success(f"Twitter/X username candidate accepted: @{username}")
        else:
            results['twitter'] = []

        candidates = {
            'tiktok':    f"https://www.tiktok.com/@{username}",
            'snapchat':  f"https://www.snapchat.com/add/{username}",
            'tumblr':    f"https://{username}.tumblr.com",
            'youtube':   f"https://www.youtube.com/@{username}",
            'reddit':    f"https://www.reddit.com/user/{username}",
            'linkedin':  f"https://www.linkedin.com/in/{username}/",
            'pinterest': f"https://www.pinterest.com/{username}/",
            'medium':    f"https://medium.com/@{username}",
            'threads':   f"https://www.threads.net/@{username}",
            'steam':     f"https://steamcommunity.com/id/{username}",
        }
        for k in candidates:
            results[k] = []

        with ThreadPoolExecutor(max_workers=11) as executor:
            futures = {
                executor.submit(self._is_url_active, url): platform
                for platform, url in candidates.items()
            }
            for future in as_completed(futures):
                platform = futures[future]
                try:
                    if future.result():
                        results[platform] = [{"url": candidates[platform], "bio": ""}]
                        logger.log_success(
                            f"{platform.capitalize()} username hit confirmed: @{username}"
                        )
                except Exception as e:
                    logger.log_warning(f"{platform.capitalize()} username check failed: {e}")

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

    def format_social_profiles(self, profiles: Dict[str, list]) -> str:
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

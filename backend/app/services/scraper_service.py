import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
from app.jarvis_logger import logger
import re
import urllib.parse
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

# Suppress warnings
warnings.filterwarnings('ignore')


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
            # For social media, we often get 200 but on a 'login' or 'not found' page
            response = self.session.get(url, timeout=7, allow_redirects=True)
            
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
            
            # Find result items
            items = soup.find_all('div', class_='algo')
            
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
                                # Extract snippet as bio
                                snippet = ""
                                sibling = snippet_elem.find_next_sibling('div') if snippet_elem else None
                                if sibling:
                                    snippet = sibling.text.strip()
                                
                                results.append({"url": actual_url, "bio": snippet})
                            if len(results) >= max_results:
                                break
                except IndexError:
                    pass
            
            return results
            
        except Exception as e:
            logger.log_error(f"Network scan failed during {query} extraction: {e}")
            return []

    def find_instagram_profile(self, name: str) -> list:
        """Try to find Instagram profile URLs and bios"""
        query = f"{name} instagram"
        items = self._extract_urls_from_yahoo(query, r'instagram\.com/([a-zA-Z0-9._]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'instagram\.com/([a-zA-Z0-9._]+)', url)
            if match and match.group(1) not in ['p', 'reel', 'explore', 'tags']:
                u = f"https://www.instagram.com/{match.group(1)}/"
                if not any(p['url'] == u for p in valid_profiles) and self._is_url_active(u): 
                    valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles
    
    def find_twitter_profile(self, name: str) -> list:
        """Try to find X (Twitter) profile URLs and bios"""
        query = f"{name} twitter"
        items = self._extract_urls_from_yahoo(query, r'(twitter|x)\.com/([a-zA-Z0-9_]+)')
        valid_profiles = []
        for item in items:
             url = item['url']
             match = re.search(r'(twitter|x)\.com/([a-zA-Z0-9_]+)', url)
             if match:
                 u = f"https://x.com/{match.group(2)}"
                 if not any(p['url'] == u for p in valid_profiles) and self._is_url_active(u): 
                     valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles
    
    def find_linkedin_profile(self, name: str) -> list:
        """Try to find LinkedIn profile URLs and bios"""
        query = f"{name} linkedin"
        items = self._extract_urls_from_yahoo(query, r'linkedin\.com/in/([a-zA-Z0-9-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'linkedin\.com/in/([a-zA-Z0-9-]+)', url)
            if match:
                u = f"https://www.linkedin.com/in/{match.group(1)}/"
                if not any(p['url'] == u for p in valid_profiles) and self._is_url_active(u): 
                    valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_spotify_profile(self, name: str) -> list:
        """Try to find Spotify profile URLs and bios"""
        query = f"{name} spotify profile"
        items = self._extract_urls_from_yahoo(query, r'open\.spotify\.com/(user|artist)/([a-zA-Z0-9._-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'open\.spotify\.com/(user|artist)/([a-zA-Z0-9._-]+)', url)
            if match:
                u = f"https://open.spotify.com/{match.group(1)}/{match.group(2)}"
                if not any(p['url'] == u for p in valid_profiles) and self._is_url_active(u): 
                    valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles

    def find_tiktok_profile(self, name: str) -> list:
        """Try to find TikTok profile URLs and bios"""
        query = f"{name} tiktok"
        items = self._extract_urls_from_yahoo(query, r'tiktok\.com/@([a-zA-Z0-9._-]+)')
        valid_profiles = []
        for item in items:
            url = item['url']
            match = re.search(r'tiktok\.com/@([a-zA-Z0-9._-]+)', url)
            if match:
                u = f"https://www.tiktok.com/@{match.group(1)}"
                if not any(p['url'] == u for p in valid_profiles) and self._is_url_active(u): 
                    valid_profiles.append({"url": u, "bio": item['bio']})
        return valid_profiles
    
    def find_all_profiles(self, name: str) -> Dict[str, list]:
        """Find all social media profiles and bios for a person (PARALLEL)"""
        logger.log_thought(f"Initiating deep-web scraping protocol for entity: {name}")
        
        platform_fns = {
            'instagram': self.find_instagram_profile,
            'twitter': self.find_twitter_profile,
            'linkedin': self.find_linkedin_profile,
            'spotify': self.find_spotify_profile,
            'tiktok': self.find_tiktok_profile,
        }
        
        profiles: Dict[str, list] = {k: [] for k in platform_fns}
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fn, name): platform for platform, fn in platform_fns.items()}
            for future in as_completed(futures):
                platform = futures[future]
                try:
                    result = future.result()
                    profiles[platform] = result
                    if result:
                        logger.log_success(f"{platform.capitalize()} profile correlated: {len(result)} found")
                except Exception as e:
                    logger.log_warning(f"{platform.capitalize()} scan failed: {e}")
        
        return profiles
    
    def format_social_profiles(self, profiles: Dict[str, list]) -> str:
        """Format social media profiles and their bios for AI context"""
        formatted = "Social Media Profiles and Bios:\n"
        
        found_any = False
        for platform, items in profiles.items():
            if items:
                found_any = True
                formatted += f"[{platform.upper()}]\n"
                for item in items:
                    formatted += f"- URL: {item['url']}\n"
                    if item.get('bio'):
                        formatted += f"  Bio/Snippet: {item['bio']}\n"
                formatted += "\n"
        
        if not found_any:
            formatted += "No social media profiles found.\n"
        
        return formatted

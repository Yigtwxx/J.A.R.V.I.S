import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
from app.jarvis_logger import logger
import re
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')


class ScraperService:
    """Service for scraping social media profiles"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def _is_url_active(self, url: str) -> bool:
        """Check if a URL is active (returns 200 OK and isn't a known error/login page)"""
        try:
            # Add specific headers to mimic a browser better
            check_headers = self.headers.copy()
            
            # For social media, we often get 200 but on a 'login' or 'not found' page
            response = requests.get(url, headers=check_headers, timeout=7, allow_redirects=True)
            
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
        """Helper to search Yahoo and extract domain URLs returning up to max_results matches"""
        results = []
        try:
            logger.log_action("Scanning global networks for targeted node", target=query)
            search_url = f"https://search.yahoo.com/search?p={requests.utils.quote(query)}"
            
            response = requests.get(search_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            import urllib.parse
            # Find all links in Yahoo results
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link.get('href', '')
                try:
                    if 'RU=' in href:
                        actual_url = urllib.parse.unquote(href.split('RU=')[1].split('/R')[0])
                        if re.search(domain_pattern, actual_url, re.IGNORECASE):
                            if actual_url not in results:
                                results.append(actual_url)
                            if len(results) >= max_results:
                                break
                except IndexError:
                    pass
            
            return results
            
        except Exception as e:
            logger.log_error(f"Network scan failed during {query} extraction: {e}")
            return []

    def find_instagram_profile(self, name: str) -> Optional[str]:
        """Try to find Instagram profile URLs"""
        query = f"{name} instagram"
        urls = self._extract_urls_from_yahoo(query, r'instagram\.com/([a-zA-Z0-9._]+)')
        valid_urls = []
        for url in urls:
            match = re.search(r'instagram\.com/([a-zA-Z0-9._]+)', url)
            if match and match.group(1) not in ['p', 'reel', 'explore', 'tags']:
                u = f"https://www.instagram.com/{match.group(1)}/"
                if u not in valid_urls and self._is_url_active(u): 
                    valid_urls.append(u)
        return ", ".join(valid_urls) if valid_urls else None
    
    def find_twitter_profile(self, name: str) -> Optional[str]:
        """Try to find X (Twitter) profile URLs"""
        query = f"{name} twitter"
        urls = self._extract_urls_from_yahoo(query, r'(twitter|x)\.com/([a-zA-Z0-9_]+)')
        valid_urls = []
        for url in urls:
             match = re.search(r'(twitter|x)\.com/([a-zA-Z0-9_]+)', url)
             if match:
                 u = f"https://x.com/{match.group(2)}"
                 if u not in valid_urls and self._is_url_active(u): 
                     valid_urls.append(u)
        return ", ".join(valid_urls) if valid_urls else None
    
    def find_linkedin_profile(self, name: str) -> Optional[str]:
        """Try to find LinkedIn profile URLs"""
        query = f"{name} linkedin"
        urls = self._extract_urls_from_yahoo(query, r'linkedin\.com/in/([a-zA-Z0-9-]+)')
        valid_urls = []
        for url in urls:
            match = re.search(r'linkedin\.com/in/([a-zA-Z0-9-]+)', url)
            if match:
                u = f"https://www.linkedin.com/in/{match.group(1)}/"
                if u not in valid_urls and self._is_url_active(u): 
                    valid_urls.append(u)
        return ", ".join(valid_urls) if valid_urls else None

    def find_spotify_profile(self, name: str) -> Optional[str]:
        """Try to find Spotify profile URLs"""
        query = f"{name} spotify profile"
        urls = self._extract_urls_from_yahoo(query, r'open\.spotify\.com/(user|artist)/([a-zA-Z0-9._-]+)')
        valid_urls = []
        for url in urls:
            match = re.search(r'open\.spotify\.com/(user|artist)/([a-zA-Z0-9._-]+)', url)
            if match:
                u = f"https://open.spotify.com/{match.group(1)}/{match.group(2)}"
                if u not in valid_urls and self._is_url_active(u): 
                    valid_urls.append(u)
        return ", ".join(valid_urls) if valid_urls else None

    def find_tiktok_profile(self, name: str) -> Optional[str]:
        """Try to find TikTok profile URLs"""
        query = f"{name} tiktok"
        urls = self._extract_urls_from_yahoo(query, r'tiktok\.com/@([a-zA-Z0-9._-]+)')
        valid_urls = []
        for url in urls:
            match = re.search(r'tiktok\.com/@([a-zA-Z0-9._-]+)', url)
            if match:
                u = f"https://www.tiktok.com/@{match.group(1)}"
                if u not in valid_urls and self._is_url_active(u): 
                    valid_urls.append(u)
        return ", ".join(valid_urls) if valid_urls else None
    
    def find_all_profiles(self, name: str) -> Dict[str, Optional[str]]:
        """Find all social media profiles for a person"""
        import time
        logger.log_thought(f"Initiating deep-web scraping protocol for entity: {name}")
        
        profiles = {
            'instagram': None,
            'twitter': None,
            'linkedin': None,
            'spotify': None,
            'tiktok': None
        }
        
        profiles['instagram'] = self.find_instagram_profile(name)
        if profiles['instagram']: logger.log_success(f"Instagram profile correlated: {profiles['instagram']}")
        time.sleep(1)
        
        profiles['twitter'] = self.find_twitter_profile(name)
        if profiles['twitter']: logger.log_success(f"X (Twitter) profile correlated: {profiles['twitter']}")
        time.sleep(1)
        
        profiles['linkedin'] = self.find_linkedin_profile(name)
        if profiles['linkedin']: logger.log_success(f"LinkedIn profile correlated: {profiles['linkedin']}")
        time.sleep(1)

        profiles['spotify'] = self.find_spotify_profile(name)
        if profiles['spotify']: logger.log_success(f"Spotify profile correlated: {profiles['spotify']}")
        time.sleep(1)

        profiles['tiktok'] = self.find_tiktok_profile(name)
        if profiles['tiktok']: logger.log_success(f"TikTok profile correlated: {profiles['tiktok']}")
        
        return profiles
    
    def format_social_profiles(self, profiles: Dict[str, Optional[str]]) -> str:
        """Format social media profiles for AI context"""
        formatted = "Social Media Profiles:\n"
        
        if profiles.get('instagram'):
            formatted += f"Instagram: {profiles['instagram']}\n"
        
        if profiles.get('twitter'):
            formatted += f"X (Twitter): {profiles['twitter']}\n"
        
        if profiles.get('linkedin'):
            formatted += f"LinkedIn: {profiles['linkedin']}\n"
        
        if profiles.get('spotify'):
            formatted += f"Spotify: {profiles['spotify']}\n"
        
        if profiles.get('tiktok'):
            formatted += f"TikTok: {profiles['tiktok']}\n"
        
        if not any(profiles.values()):
            formatted += "No social media profiles found.\n"
        
        return formatted

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
    
    def _extract_url_from_yahoo(self, query: str, domain_pattern: str) -> Optional[str]:
        """Helper to search Yahoo and extract a specific domain URL"""
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
                            return actual_url
                except IndexError:
                    pass
            
            return None
            
        except Exception as e:
            logger.log_error(f"Network scan failed during {query} extraction: {e}")
            return None

    def find_instagram_profile(self, name: str) -> Optional[str]:
        """Try to find Instagram profile URL"""
        query = f"{name} instagram"
        url = self._extract_url_from_yahoo(query, r'instagram\.com/([a-zA-Z0-9._]+)')
        if url:
            # Clean up URL
            match = re.search(r'instagram\.com/([a-zA-Z0-9._]+)', url)
            if match:
                return f"https://www.instagram.com/{match.group(1)}/"
        return None
    
    def find_twitter_profile(self, name: str) -> Optional[str]:
        """Try to find X (Twitter) profile URL"""
        query = f"{name} twitter"
        # X or Twitter domain
        url = self._extract_url_from_yahoo(query, r'(twitter|x)\.com/([a-zA-Z0-9_]+)')
        if url:
             match = re.search(r'(twitter|x)\.com/([a-zA-Z0-9_]+)', url)
             if match:
                 return f"https://x.com/{match.group(2)}"
        return None
    
    def find_linkedin_profile(self, name: str) -> Optional[str]:
        """Try to find LinkedIn profile URL"""
        query = f"{name} linkedin"
        url = self._extract_url_from_yahoo(query, r'linkedin\.com/in/([a-zA-Z0-9-]+)')
        if url:
            match = re.search(r'linkedin\.com/in/([a-zA-Z0-9-]+)', url)
            if match:
                return f"https://www.linkedin.com/in/{match.group(1)}/"
        return None
    
    def find_all_profiles(self, name: str) -> Dict[str, Optional[str]]:
        """Find all social media profiles for a person"""
        import time
        logger.log_thought(f"Initiating deep-web scraping protocol for entity: {name}")
        
        profiles = {
            'instagram': None,
            'twitter': None,
            'linkedin': None
        }
        
        profiles['instagram'] = self.find_instagram_profile(name)
        if profiles['instagram']: logger.log_success(f"Instagram profile correlated: {profiles['instagram']}")
        time.sleep(1)
        
        profiles['twitter'] = self.find_twitter_profile(name)
        if profiles['twitter']: logger.log_success(f"X (Twitter) profile correlated: {profiles['twitter']}")
        time.sleep(1)
        
        profiles['linkedin'] = self.find_linkedin_profile(name)
        if profiles['linkedin']: logger.log_success(f"LinkedIn profile correlated: {profiles['linkedin']}")
        
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
        
        if not any(profiles.values()):
            formatted += "No social media profiles found.\n"
        
        return formatted

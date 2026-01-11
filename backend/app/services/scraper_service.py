import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
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
    
    def find_instagram_profile(self, name: str) -> Optional[str]:
        """
        Try to find Instagram profile URL
        
        Args:
            name: Person's name
        
        Returns:
            Instagram profile URL or None
        """
        try:
            # Search Google for Instagram profile
            query = f"{name} instagram"
            search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            
            response = requests.get(search_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find Instagram links
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if 'instagram.com' in href:
                    # Extract clean Instagram URL
                    match = re.search(r'instagram\.com/([a-zA-Z0-9._]+)', href)
                    if match:
                        username = match.group(1)
                        return f"https://www.instagram.com/{username}/"
            
            return None
        
        except Exception as e:
            print(f"Instagram scraping error: {e}")
            return None
    
    def find_twitter_profile(self, name: str) -> Optional[str]:
        """
        Try to find X (Twitter) profile URL
        
        Args:
            name: Person's name
        
        Returns:
            Twitter profile URL or None
        """
        try:
            # Search Google for Twitter profile
            query = f"{name} twitter"
            search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            
            response = requests.get(search_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find Twitter/X links
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if 'twitter.com' in href or 'x.com' in href:
                    # Extract clean Twitter URL
                    match = re.search(r'(twitter|x)\.com/([a-zA-Z0-9_]+)', href)
                    if match:
                        username = match.group(2)
                        return f"https://x.com/{username}"
            
            return None
        
        except Exception as e:
            print(f"Twitter scraping error: {e}")
            return None
    
    def find_linkedin_profile(self, name: str) -> Optional[str]:
        """
        Try to find LinkedIn profile URL
        
        Args:
            name: Person's name
        
        Returns:
            LinkedIn profile URL or None
        """
        try:
            # Search Google for LinkedIn profile
            query = f"{name} linkedin"
            search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            
            response = requests.get(search_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find LinkedIn links
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if 'linkedin.com/in/' in href:
                    # Extract clean LinkedIn URL
                    match = re.search(r'linkedin\.com/in/([a-zA-Z0-9-]+)', href)
                    if match:
                        username = match.group(1)
                        return f"https://www.linkedin.com/in/{username}/"
            
            return None
        
        except Exception as e:
            print(f"LinkedIn scraping error: {e}")
            return None
    
    def find_all_profiles(self, name: str) -> Dict[str, Optional[str]]:
        """
        Find all social media profiles for a person
        
        Args:
            name: Person's name
        
        Returns:
            Dictionary with all found profile URLs
        """
        import time
        
        profiles = {
            'instagram': None,
            'twitter': None,
            'linkedin': None
        }
        
        # Find each profile with delays to avoid rate limiting
        profiles['instagram'] = self.find_instagram_profile(name)
        time.sleep(1)
        
        profiles['twitter'] = self.find_twitter_profile(name)
        time.sleep(1)
        
        profiles['linkedin'] = self.find_linkedin_profile(name)
        
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

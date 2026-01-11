import requests
from typing import Dict, Optional
from app.config import get_settings
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

settings = get_settings()


class GitHubService:
    """Service for GitHub API interactions"""
    
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.headers = {
            'Accept': 'application/vnd.github.v3+json',
        }
        
        if settings.github_token:
            self.headers['Authorization'] = f'token {settings.github_token}'
    
    def search_user(self, username: str) -> Optional[Dict]:
        """
        Search for GitHub user by username
        
        Args:
            username: GitHub username or real name
        
        Returns:
            User profile data or None
        """
        try:
            # First try direct username lookup
            user_data = self._get_user_by_username(username)
            if user_data:
                return user_data
            
            # If not found, search by name
            search_url = f"{self.base_url}/search/users"
            params = {'q': username, 'per_page': 1}
            
            response = requests.get(search_url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data['total_count'] > 0:
                user_login = data['items'][0]['login']
                return self._get_user_by_username(user_login)
            
            return None
        
        except Exception as e:
            print(f"GitHub search error: {e}")
            return None
    
    def _get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user profile by exact username"""
        try:
            user_url = f"{self.base_url}/users/{username}"
            response = requests.get(user_url, headers=self.headers, timeout=10)
            
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            user_data = response.json()
            
            # Get repositories
            repos = self._get_user_repos(username)
            
            return {
                'username': user_data.get('login'),
                'name': user_data.get('name'),
                'bio': user_data.get('bio'),
                'company': user_data.get('company'),
                'location': user_data.get('location'),
                'email': user_data.get('email'),
                'blog': user_data.get('blog'),
                'twitter': user_data.get('twitter_username'),
                'public_repos': user_data.get('public_repos'),
                'followers': user_data.get('followers'),
                'following': user_data.get('following'),
                'profile_url': user_data.get('html_url'),
                'avatar_url': user_data.get('avatar_url'),
                'repositories': repos
            }
        
        except Exception as e:
            print(f"Error fetching GitHub user: {e}")
            return None
    
    def _get_user_repos(self, username: str, max_repos: int = 5) -> list:
        """Get user's top repositories"""
        try:
            repos_url = f"{self.base_url}/users/{username}/repos"
            params = {
                'sort': 'updated',
                'per_page': max_repos
            }
            
            response = requests.get(repos_url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            repos_data = response.json()
            
            repos = []
            for repo in repos_data:
                repos.append({
                    'name': repo.get('name'),
                    'description': repo.get('description'),
                    'url': repo.get('html_url'),
                    'stars': repo.get('stargazers_count'),
                    'language': repo.get('language')
                })
            
            return repos
        
        except Exception as e:
            print(f"Error fetching repos: {e}")
            return []
    
    def format_github_data(self, github_data: Dict) -> str:
        """Format GitHub data for AI context"""
        if not github_data:
            return "No GitHub profile found."
        
        formatted = f"GitHub Profile: {github_data.get('profile_url', '')}\n"
        formatted += f"Username: {github_data.get('username', 'N/A')}\n"
        
        if github_data.get('name'):
            formatted += f"Name: {github_data['name']}\n"
        
        if github_data.get('bio'):
            formatted += f"Bio: {github_data['bio']}\n"
        
        if github_data.get('company'):
            formatted += f"Company: {github_data['company']}\n"
        
        if github_data.get('location'):
            formatted += f"Location: {github_data['location']}\n"
        
        formatted += f"Public Repos: {github_data.get('public_repos', 0)}\n"
        formatted += f"Followers: {github_data.get('followers', 0)}\n"
        
        if github_data.get('repositories'):
            formatted += "\nTop Repositories:\n"
            for repo in github_data['repositories']:
                formatted += f"  - {repo['name']}"
                if repo.get('language'):
                    formatted += f" ({repo['language']})"
                if repo.get('stars'):
                    formatted += f" - ⭐ {repo['stars']}"
                formatted += "\n"
                if repo.get('description'):
                    formatted += f"    {repo['description']}\n"
        
        return formatted

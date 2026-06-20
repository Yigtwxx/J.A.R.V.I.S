
from threading import Lock

import requests
from cachetools import TTLCache, cached
from cachetools.keys import hashkey

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()

# Service-level cache for resolved GitHub profiles. Short TTL keeps data fresh
# while collapsing duplicate lookups during a single investigation. Thread-safe.
_github_user_cache: TTLCache = TTLCache(maxsize=256, ttl=900)
_github_user_lock = Lock()


class GitHubService:
    """Service for GitHub API interactions"""

    def __init__(self):
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github.v3+json',
        })

        if settings.github_token:
            self.session.headers['Authorization'] = f'token {settings.github_token}'
            logger.log_success("GitHub authentication protocol loaded.")

    @cached(
        cache=_github_user_cache,
        key=lambda self, username: hashkey(username.lower().strip()),
        lock=_github_user_lock,
    )
    def search_user(self, username: str) -> dict | None:
        """
        Search for GitHub user by username
        """
        try:
            logger.log_thought(f"Querying GitHub central servers for entity: {username}")
            # First try direct username lookup
            user_data = self._get_user_by_username(username)
            if user_data:
                logger.log_success("Direct GitHub profile match confirmed.")
                return user_data

            # If not found, search by name
            logger.log_warning("Direct match failed. Initiating fuzzy search protocol...")
            search_url = f"{self.base_url}/search/users"
            params = {'q': username, 'per_page': 1}

            response = self.session.get(search_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data['total_count'] > 0:
                user_login = data['items'][0]['login']
                logger.log_action("Correlated identity found", target=user_login)
                return self._get_user_by_username(user_login)

            logger.log_error("No GitHub profile correlations found.")
            return None

        except Exception as e:
            logger.log_error(f"GitHub neural connection severed: {e}")
            return None

    def _get_user_by_username(self, username: str) -> dict | None:
        """Get user profile by exact username"""
        try:
            logger.log_action("Downloading profile schematics", target=username)
            user_url = f"{self.base_url}/users/{username}"
            response = self.session.get(user_url, timeout=10)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            user_data = response.json()

            # Get repositories
            repos = self._get_user_repos(username)

            # Get recent commit activity
            recent_commits = self._get_recent_commits(username)

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
                'last_active': user_data.get('updated_at'),
                'created_at': user_data.get('created_at'),
                'repositories': repos,
                'recent_commits': recent_commits,
            }

        except Exception as e:
            logger.log_error(f"Error fetching GitHub user node: {e}")
            return None

    def _get_recent_commits(self, username: str, max_commits: int = 20) -> list:
        """Get recent commit activity across user's public repos."""
        try:
            events_url = f"{self.base_url}/users/{username}/events/public"
            response = self.session.get(events_url, params={"per_page": 100}, timeout=10)
            if response.status_code != 200:
                return []
            events = response.json()
            commits = []
            for event in events:
                if event.get("type") == "PushEvent":
                    for commit in event.get("payload", {}).get("commits", []):
                        commits.append({
                            "date": event.get("created_at", ""),
                            "message": commit.get("message", ""),
                            "repo": event.get("repo", {}).get("name", ""),
                        })
                        if len(commits) >= max_commits:
                            return commits
            return commits
        except Exception as e:
            logger.log_warning(f"Failed to fetch recent commits: {e}")
            return []

    def _get_user_repos(self, username: str, max_repos: int = 5) -> list:
        """Get user's top repositories"""
        try:
            logger.log_action("Extracting repository blueprints", target=username)
            repos_url = f"{self.base_url}/users/{username}/repos"
            params = {
                'sort': 'updated',
                'per_page': max_repos
            }

            response = self.session.get(repos_url, params=params, timeout=10)
            response.raise_for_status()

            repos_data = response.json()

            repos = []
            for repo in repos_data:
                repos.append({
                    'name': repo.get('name'),
                    'description': repo.get('description'),
                    'url': repo.get('html_url'),
                    'stars': repo.get('stargazers_count'),
                    'language': repo.get('language'),
                    'updated_at': repo.get('updated_at')
                })

            return repos

        except Exception as e:
            logger.log_error(f"Error fetching repository nodes: {e}")
            return []

    def format_github_data(self, github_data: dict) -> str:
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

        if github_data.get('last_active'):
            formatted += f"Last Account Activity: {github_data['last_active']}\n"

        if github_data.get('repositories'):
            formatted += "\nTop Repositories:\n"
            for repo in github_data['repositories']:
                formatted += f"  - {repo['name']}"
                if repo.get('language'):
                    formatted += f" ({repo['language']})"
                if repo.get('stars'):
                    formatted += f" - ⭐ {repo['stars']}"
                if repo.get('updated_at'):
                    formatted += f" [Last updated: {repo['updated_at']}]"
                formatted += "\n"
                if repo.get('description'):
                    formatted += f"    {repo['description']}\n"

        return formatted

import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import time
import warnings

# Suppress InsecureRequestWarning
warnings.filterwarnings('ignore', message='Unverified HTTPS request')


class SearchService:
    """Service for web search using Google scraping"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def search_google(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """
        Search Google and return scraped results
        
        Args:
            query: Search query
            num_results: Number of results to return
        
        Returns:
            List of search results with title, url, snippet
        """
        try:
            # Format query for Google
            search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            
            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Find search result divs
            search_divs = soup.find_all('div', class_='g')
            
            for div in search_divs[:num_results]:
                try:
                    # Extract title and link
                    title_elem = div.find('h3')
                    link_elem = div.find('a')
                    snippet_elem = div.find('div', class_=['VwiC3b', 'yXK7lf'])
                    
                    if title_elem and link_elem:
                        results.append({
                            'title': title_elem.get_text(),
                            'url': link_elem.get('href', ''),
                            'snippet': snippet_elem.get_text() if snippet_elem else ''
                        })
                except Exception as e:
                    continue
            
            return results
        
        except Exception as e:
            print(f"Google search error: {e}")
            return []
    
    def format_search_results(self, results: List[Dict[str, str]]) -> str:
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
    
    def search_person(self, name: str) -> str:
        """
        Search for a person and return formatted results
        
        Args:
            name: Person's name
        
        Returns:
            Formatted search results
        """
        # Search with multiple queries for better results
        queries = [
            f"{name} profile",
            f"{name} github",
            f"{name} linkedin",
        ]
        
        all_results = []
        for query in queries:
            results = self.search_google(query, num_results=3)
            all_results.extend(results)
            time.sleep(1)  # Be nice to Google
        
        return self.format_search_results(all_results)

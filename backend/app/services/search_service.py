import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from app.jarvis_logger import logger
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
            
            search_res = requests.get(search_url, params=search_params, headers=wiki_headers, timeout=5)
            search_data = search_res.json()
            
            if not search_data.get('query', {}).get('search'):
                return ""
                
            page_title = search_data['query']['search'][0]['title']
            
            # 2. Then get the main image (pageimage) for that title
            image_params = {
                "action": "query",
                "format": "json",
                "prop": "pageimages",
                "titles": page_title,
                "pithumbsize": 800  # Request a reasonably large image
            }
            
            img_res = requests.get(search_url, params=image_params, headers=wiki_headers, timeout=5)
            img_data = img_res.json()
            
            pages = img_data.get('query', {}).get('pages', {})
            for page_id, page_info in pages.items():
                if 'thumbnail' in page_info and 'source' in page_info['thumbnail']:
                    img_url = page_info['thumbnail']['source']
                    logger.log_success(f"Visual identity confirmed. Source: {img_url}")
                    return img_url
                    
            return ""
            
        except Exception as e:
            logger.log_warning(f"Failed to extract biographical image: {e}")
            return ""
    
    def search_yahoo(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """
        Search Yahoo and return scraped results
        """
        try:
            logger.log_action("Accessing global data grid", target=query)
            search_url = f"https://search.yahoo.com/search?p={requests.utils.quote(query)}"
            
            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            import urllib.parse
            # Find result divs
            search_divs = soup.find_all('div', class_='algo')
            
            for div in search_divs[:num_results]:
                try:
                    # Extract title, link, snippet
                    title_elem = div.find('h3', class_='title')
                    link_elem = div.find('a', href=True)
                    snippet_elem = div.find('div', class_='compTitle')
                    
                    if title_elem and link_elem:
                        href = link_elem.get('href', '')
                        real_url = href
                        
                        if 'RU=' in href:
                            try:
                                real_url = urllib.parse.unquote(href.split('RU=')[1].split('/R')[0])
                            except:
                                pass
                                
                        snippet = snippet_elem.find_next_sibling('div').text.strip() if snippet_elem and snippet_elem.find_next_sibling('div') else ''
                            
                        results.append({
                            'title': title_elem.text.strip(),
                            'url': real_url,
                            'snippet': snippet
                        })
                except Exception as e:
                    continue
            
            logger.log_success(f"Extracted {len(results)} pertinent data packets.")
            return results
        
        except Exception as e:
            logger.log_error(f"Global grid access denied or timed out: {e}")
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
    
    def search_person(self, name: str) -> tuple[str, str]:
        """
        Search for a person and return (wiki_image_url, formatted_results)
        """
        logger.log_thought(f"Initiating cross-reference protocol for entity: {name}")
        
        # 1. Fetch visual identity from Wikipedia first
        wiki_image = self.search_wikipedia_image(name)
        
        # 2. Search with multiple queries for better results
        queries = [
            f"{name} profile",
            f"{name} github",
            f"{name} linkedin",
        ]
        
        all_results = []
        for query in queries:
            results = self.search_yahoo(query, num_results=3)
            all_results.extend(results)
            time.sleep(1)  # Be nice to Yahoo
        
        logger.log_success("Data aggregation complete.")
        
        formatted_text = self.format_search_results(all_results)
            
        return wiki_image, formatted_text

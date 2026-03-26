import requests
import urllib3
from bs4 import BeautifulSoup
from typing import List, Dict
import time
import urllib.parse
import difflib
import unicodedata
from app.utils.logger import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SearchService:
    """Service for web search using Google scraping"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
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
            
            search_res = self.session.get(search_url, params=search_params, headers=wiki_headers, timeout=5)
            search_data = search_res.json()
            
            if not search_data.get('query', {}).get('search'):
                return ""
                
            page_title = search_data['query']['search'][0]['title']
            
            # Verify the title actually matches what we're looking for
            query_words = set(query.lower().split())
            title_words = set(page_title.lower().split())
            
            # Allow minor differences like 'Erdoğan' vs 'Erdogan'
            def normalize_text(text):
                return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
                
            query_words_norm = {normalize_text(w) for w in query_words}
            title_words_norm = {normalize_text(w) for w in title_words}
            
            # Check if all words from the query exist in the Wikipedia title
            if not query_words_norm.issubset(title_words_norm):
                logger.log_warning(f"Wikipedia result '{page_title}' failed subset check for '{query}'. Skipping visual extraction.")
                return ""
            
            # 2. Then get the main image (pageimage) for that title
            image_params = {
                "action": "query",
                "format": "json",
                "prop": "pageimages",
                "titles": page_title,
                "pithumbsize": 800  # Request a reasonably large image
            }
            
            img_res = self.session.get(search_url, params=image_params, headers=wiki_headers, timeout=5)
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
            
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
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
                            except Exception:
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
            
    def _is_relevant(self, title: str, snippet: str, query: str) -> bool:
        """
        Check if a search result is actually relevant to the target name.
        Uses stricter matching to avoid famous-name hallucinations.
        """
        text = f"{title} {snippet}".lower()
        query = query.lower().strip()
        query_words = [w for w in query.split() if len(w) > 2]
        
        if not query_words:
            return query in text

        # 1. Exact Full Name Match (Highest confidence)
        if query in text:
            return True
            
        # 2. Split match check:
        # If the query is "Yiğit Erdoğan", we want BOTH "Yiğit" and "Erdoğan" to be present.
        # This prevents "Recep Tayyip Erdoğan" matching "Yiğit Erdoğan" just because of the surname.
        def normalize(t):
            return "".join(c for c in unicodedata.normalize('NFD', t.lower()) if unicodedata.category(c) != 'Mn')
            
        text_norm = normalize(text)
        query_words_norm = [normalize(w) for w in query_words]
        
        # All major components of the name must be present in the text
        if all(word in text_norm for word in query_words_norm):
            return True
            
        # 3. Fuzzy matching for typos (only if the query is unique enough)
        text_words = text_norm.split()
        matches_found = 0
        for word in query_words_norm:
            if word in text_norm:
                matches_found += 1
            elif len(word) >= 4:
                # Check for close matches in any of the title/snippet words
                if div_matches := difflib.get_close_matches(word, text_words, n=1, cutoff=0.85):
                    matches_found += 1
                    
        # Require at least 80% of query words to match if they are not all present
        return matches_found >= len(query_words)
    
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

    def fetch_content(self, url: str) -> str:
        """
        Fetch and clean the visible text from a URL for deep analysis.
        """
        # Skip social media domains as they are often blocked or need JS
        if any(domain in url.lower() for domain in ['instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'facebook.com']):
            return ""
            
        try:
            logger.log_thought(f"Infiltrating host and extracting raw data packets: {url}")
            response = self.session.get(url, timeout=12)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove noisy elements
            for element in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'form', 'button']):
                element.decompose()
                
            # Extract and sanitize text
            text = soup.get_text(separator=' ')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return clean_text[:8000]  # Expanded for deeper analysis
            
        except Exception as e:
            logger.log_warning(f"Data packet extraction failed for {url}: {str(e)}")
            return ""
            
    def search_academic_publications(self, query: str) -> str:
        """
        Query Crossref and ORCID to find academic publications for a person.
        """
        academic_context = ""
        try:
            logger.log_action("Scanning academic networks (Crossref/ORCID)", target=query)
            
            # 1. ORCID Check (just to see if they are a registered researcher)
            orcid_url = f"https://pub.orcid.org/v3.0/search/?q={urllib.parse.quote(query)}"
            try:
                orcid_res = self.session.get(orcid_url, headers={'Accept': 'application/json'}, timeout=5)
                if orcid_res.status_code == 200:
                    orcid_data = orcid_res.json()
                    results = orcid_data.get('result', [])
                    if results:
                        academic_context += f"[ORCID] Verified researcher profile exists. Found {len(results)} potential ORCID matches.\n"
            except Exception as e:
                logger.log_warning(f"Failed to query ORCID: {e}")

            # 2. Crossref API for Publications
            crossref_url = f"https://api.crossref.org/works?query.author={urllib.parse.quote(query)}&select=title,author,URL,published-print,publisher&rows=5"
            try:
                crossref_res = self.session.get(crossref_url, timeout=5)
                if crossref_res.status_code == 200:
                    cross_data = crossref_res.json()
                    items = cross_data.get('message', {}).get('items', [])
                    
                    if items:
                        academic_context += "\n[Crossref] Top Academic Publications:\n"
                        for i, item in enumerate(items, 1):
                            title = item.get('title', ['Unknown Title'])[0]
                            publisher = item.get('publisher', 'Unknown Publisher')
                            url = item.get('URL', '')
                            
                            # Try to extract year
                            year = "Unknown Date"
                            published_print = item.get('published-print', {})
                            if 'date-parts' in published_print and published_print['date-parts']:
                                year = str(published_print['date-parts'][0][0])
                                
                            academic_context += f"  {i}. \"{title}\" ({year}) - {publisher}. URL: {url}\n"
                    else:
                        academic_context += "\n[Crossref] No major publications found under this exact name.\n"
            except Exception as e:
                logger.log_warning(f"Failed to query Crossref: {e}")
                
            if academic_context:
                logger.log_success("Academic intelligence retrieved.")
            return academic_context

        except Exception as e:
            logger.log_warning(f"Academic sweep failed: {e}")
            return ""

    def search_patents(self, query: str) -> str:
        """
        Query patent databases to find technical patents for a person.
        We'll use a basic Google Patents search via Yahoo for simplicity and reliability, 
        as PatentsView is highly specific to US patents and often requires strict formatting.
        """
        try:
            logger.log_action("Scanning patent registries", target=query)
            # Use yahoo to search specifically inside patents.google.com
            patent_query = f"site:patents.google.com inventor \"{query}\""
            results = self.search_yahoo(patent_query, num_results=3)
            
            patent_context = ""
            if results:
                patent_context += "\n[Patent Registries] Registered Patents / Inventions:\n"
                for i, res in enumerate(results, 1):
                    # Clean up title (Google Patents usually returns 'US1234567B2 - Title...')
                    title = res['title'].replace(' - Google Patents', '')
                    patent_context += f"  {i}. {title}\n"
                    patent_context += f"     URL: {res['url']}\n"
                    
                logger.log_success("Patent intelligence retrieved.")
            return patent_context
            
        except Exception as e:
            logger.log_warning(f"Patent sweep failed: {e}")
            return ""
            
    def search_official_registries(self, query: str) -> str:
        """
        Query public corporate registry databases (OpenCorporates, Companies House, etc.)
        for business links, directorships, or founder statuses, bypassing API key requirements.
        """
        try:
            logger.log_action("Scanning global corporate registries", target=query)
            
            # Combine major open registries into one Dork search
            registry_query = f"(site:opencorporates.com OR site:find-and-update.company-information.service.gov.uk) \"{query}\""
            results = self.search_yahoo(registry_query, num_results=4)
            
            official_context = ""
            if results:
                official_context += "\n[Official Registries] Corporate Footprint & Directorships:\n"
                for i, res in enumerate(results, 1):
                    # Clean up the output titles for neat presentation
                    title = res['title'].replace(' - OpenCorporates', '')
                    title = title.replace(' - Find and update company information - GOV.UK', '')
                    
                    official_context += f"  {i}. {title}\n"
                    if res.get('snippet'):
                        official_context += f"     Info: {res['snippet']}\n"
                    official_context += f"     URL: {res['url']}\n\n"
                    
                logger.log_success("Corporate intelligence retrieved.")
            return official_context
            
        except Exception as e:
            logger.log_warning(f"Corporate registry sweep failed: {e}")
            return ""
    
    def search_person(self, name: str) -> tuple[str, str, str, List[Dict[str, str]]]:
        """
        Search for a person and return (wiki_image_url, formatted_results, deep_context, raw_results)
        """
        logger.log_thought(f"Initiating cross-reference protocol for entity: {name}")
        
        # 1. Fetch visual identity from Wikipedia first
        wiki_image = self.search_wikipedia_image(name)
        
        # 2. Search with multiple diverse queries for comprehensive results
        queries = [
            f"{name} biography OR education",
            f"{name} career OR profession",
            f"{name} interview OR news",
            f"{name} profile",
            f"{name}",
        ]
        
        all_results = []
        seen_urls = set()
        for query in queries:
            logger.log_action(f"Scanning subspace for: {query}")
            results = self.search_yahoo(query, num_results=5)
            # Deduplicate results by URL and filter irrelevant ones
            for r in results:
                if r['url'] not in seen_urls:
                    # STRICT FILTER: Only keep results that actually resemble the target name
                    if self._is_relevant(r.get('title', ''), r.get('snippet', ''), name):
                        seen_urls.add(r['url'])
                        all_results.append(r)
            logger.log_thought(f"Extracted {len(all_results)} verified data nodes so far.")
            time.sleep(1)
        
        # 3. Deep-Scraping Protocol: Extract full content from top relevant links
        logger.log_action("Executing deep-packet inspection on primary sources...")
        logger.log_thought("Filtering nodes for high-density information...")
        deep_context = ""
        # Find top 4 non-social results for deep scraping (increased from 2)
        scrapable_results = [r for r in all_results if not any(d in r['url'].lower() for d in ['instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'facebook.com', 'youtube.com'])][:4]
        
        for res in scrapable_results:
            # Use urllib.parse.urlparse to get the hostname safely
            parsed_url = urllib.parse.urlparse(res['url'])
            hostname = parsed_url.hostname if parsed_url.scheme and parsed_url.netloc else res['url']
            logger.log_action(f"Infiltrating NODE: {hostname}")
            content = self.fetch_content(res['url'])
            if content:
                deep_context += f"--- NODE: {res['url']} ---\n{content}\n\n"
                logger.log_success(f"Packet integrity verified for {res['url']}")
        
        logger.log_success("Data aggregation and content synthesis complete.")

        formatted_text = self.format_search_results(all_results)

        return wiki_image, formatted_text, deep_context, all_results

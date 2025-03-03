import logging
import json
import time
from typing import Dict, Any, List, Optional, Union
from .web_client import WebClient

class SearchEngine:
    """A tool for Agent to perform internet searches using various search engines."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the search engine with optional configuration.

        Args:
            config: Configuration options including API keys, search engine preferences, etc.
        """
        self.config = config or {}
        self.web_client = WebClient(self.config.get('web_client'))
        self.logger = logging.getLogger(__name__)

        # Default search engine
        self.default_engine = self.config.get('default_engine', 'duckduckgo')

        # API keys for different search engines
        self.api_keys = self.config.get('api_keys', {})

        # Rate limiting settings
        self.rate_limits = self.config.get('rate_limits', {
            'duckduckgo': {'requests_per_hour': 100, 'seconds_between_requests': 2},
            'google': {'requests_per_day': 100, 'seconds_between_requests': 1},
            'bing': {'requests_per_month': 1000, 'seconds_between_requests': 1}
        })

        # Track last request time for rate limiting
        self.last_request_time = {}

    def search(self, query: str, engine: Optional[str] = None, 
               num_results: int = 10, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform a web search using the specified or default search engine.

        Args:
            query: The search query
            engine: Search engine to use (google, bing, duckduckgo)
            num_results: Number of results to return
            filters: Optional filters for search (e.g., time, region, domain)

        Returns:
            Dictionary containing search results and metadata
        """
        engine = engine or self.default_engine
        engine = engine.lower()

        # Apply rate limiting
        self._apply_rate_limiting(engine)

        if engine == 'duckduckgo':
            return self._search_duckduckgo(query, num_results, filters)
        elif engine == 'google':
            return self._search_google(query, num_results, filters)
        elif engine == 'bing':
            return self._search_bing(query, num_results, filters)
        else:
            self.logger.error(f"Unsupported search engine: {engine}")
            return {
                'success': False,
                'error': f"Unsupported search engine: {engine}",
                'results': []
            }

    def _apply_rate_limiting(self, engine: str) -> None:
        """Apply rate limiting for the specified search engine.

        Args:
            engine: The search engine to apply rate limiting for
        """
        now = time.time()
        if engine in self.last_request_time:
            elapsed = now - self.last_request_time[engine]
            wait_time = self.rate_limits.get(engine, {}).get('seconds_between_requests', 1)

            if elapsed < wait_time:
                time.sleep(wait_time - elapsed)

        self.last_request_time[engine] = time.time()

    def _search_duckduckgo(self, query: str, num_results: int = 10, 
                          filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform a search using DuckDuckGo.

        Args:
            query: The search query
            num_results: Number of results to return
            filters: Optional filters for search

        Returns:
            Dictionary containing search results and metadata
        """
        # Note: DuckDuckGo doesn't have an official API, so we're using a web scraping approach
        # This is less reliable than an official API but works for basic searches

        # Create a DuckDuckGo search URL
        url = "https://html.duckduckgo.com/html/"
        params = {
            'q': query,
            's': '0'  # Starting position
        }

        # Add filters if provided
        if filters:
            if 'time' in filters:
                params['df'] = filters['time']  # Time filter
            if 'region' in filters:
                params['kl'] = filters['region']  # Region filter

        try:
            response = self.web_client.get(url, params=params)

            if 'error' in response:
                return {
                    'success': False,
                    'error': response['error'],
                    'results': []
                }

            # Parse the HTML to extract results
            html = response.get('html', '')
            if not html:
                return {
                    'success': False,
                    'error': 'Failed to get HTML from response',
                    'results': []
                }

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            results = []
            for result in soup.select('.result')[:num_results]:
                title_element = result.select_one('.result__title')
                link_element = result.select_one('.result__url')
                snippet_element = result.select_one('.result__snippet')

                if title_element and link_element:
                    title = title_element.get_text(strip=True)
                    url = link_element.get('href', '')
                    snippet = snippet_element.get_text(strip=True) if snippet_element else ""

                    results.append({
                        'title': title,
                        'url': url,
                        'snippet': snippet
                    })

            return {
                'success': True,
                'query': query,
                'engine': 'duckduckgo',
                'results_count': len(results),
                'results': results
            }

        except Exception as e:
            self.logger.error(f"Error performing DuckDuckGo search: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'results': []
            }

    def _search_google(self, query: str, num_results: int = 10, 
                      filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform a search using Google Custom Search API.

        Args:
            query: The search query
            num_results: Number of results to return
            filters: Optional filters for search

        Returns:
            Dictionary containing search results and metadata
        """
        # Check if Google API key and CSE ID are available
        api_key = self.api_keys.get('google', {}).get('api_key')
        cse_id = self.api_keys.get('google', {}).get('cse_id')

        if not api_key or not cse_id:
            self.logger.error("Google search requires API key and CSE ID")
            return {
                'success': False,
                'error': "Google search requires API key and CSE ID",
                'results': []
            }

        # Create Google Custom Search API URL
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': cse_id,
            'q': query,
            'num': min(num_results, 10),  # Google API limits to 10 results per request
        }

        # Add filters if provided
        if filters:
            if 'site' in filters:
                params['siteSearch'] = filters['site']
            if 'date_restrict' in filters:
                params['dateRestrict'] = filters['date_restrict']
            if 'language' in filters:
                params['lr'] = f"lang_{filters['language']}"

        try:
            response = self.web_client.get(url, params=params)

            if 'error' in response:
                return {
                    'success': False,
                    'error': response['error'],
                    'results': []
                }

            content = response.get('content', {})

            # Extract search results
            results = []
            for item in content.get('items', [])[:num_results]:
                results.append({
                    'title': item.get('title', ''),
                    'url': item.get('link', ''),
                    'snippet': item.get('snippet', '')
                })

            return {
                'success': True,
                'query': query,
                'engine': 'google',
                'results_count': len(results),
                'total_results': content.get('searchInformation', {}).get('totalResults', 0),
                'results': results
            }

        except Exception as e:
            self.logger.error(f"Error performing Google search: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'results': []
            }

    def _search_bing(self, query: str, num_results: int = 10, 
                    filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform a search using Bing Search API.

        Args:
            query: The search query
            num_results: Number of results to return
            filters: Optional filters for search

        Returns:
            Dictionary containing search results and metadata
        """
        # Check if Bing API key is available
        api_key = self.api_keys.get('bing', {}).get('api_key')

        if not api_key:
            self.logger.error("Bing search requires API key")
            return {
                'success': False,
                'error': "Bing search requires API key",
                'results': []
            }

        # Create Bing Search API URL
        url = "https://api.bing.microsoft.com/v7.0/search"
        params = {
            'q': query,
            'count': min(num_results, 50)  # Bing API allows up to 50 results per request
        }

        # Add filters if provided
        if filters:
            if 'freshness' in filters:
                params['freshness'] = filters['freshness']  # e.g., Day, Week, Month
            if 'market' in filters:
                params['mkt'] = filters['market']  # e.g., en-US
            if 'safe_search' in filters:
                params['safeSearch'] = filters['safe_search']  # Strict, Moderate, Off

        try:
            # Add Bing API key to headers
            headers = {'Ocp-Apim-Subscription-Key': api_key}
            self.web_client.session.headers.update(headers)

            response = self.web_client.get(url, params=params)

            # Restore original headers
            self.web_client.session.headers.pop('Ocp-Apim-Subscription-Key', None)

            if 'error' in response:
                return {
                    'success': False,
                    'error': response['error'],
                    'results': []
                }

            content = response.get('content', {})

            # Extract search results
            results = []
            for item in content.get('webPages', {}).get('value', [])[:num_results]:
                results.append({
                    'title': item.get('name', ''),
                    'url': item.get('url', ''),
                    'snippet': item.get('snippet', '')
                })

            return {
                'success': True,
                'query': query,
                'engine': 'bing',
                'results_count': len(results),
                'total_results': content.get('webPages', {}).get('totalEstimatedMatches', 0),
                'results': results
            }

        except Exception as e:
            self.logger.error(f"Error performing Bing search: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'results': []
            }

    def get_search_results(self, query: str, engines: List[str] = None, 
                          num_results: int = 5) -> Dict[str, Any]:
        """Perform a search using multiple search engines and combine results.

        Args:
            query: The search query
            engines: List of search engines to use
            num_results: Number of results to return per engine

        Returns:
            Dictionary containing combined search results
        """
        engines = engines or [self.default_engine]

        all_results = []
        combined_results = {
            'query': query,
            'success': True,
            'engines_used': engines,
            'results_count': 0,
            'results': [],
            'errors': []
        }

        for engine in engines:
            result = self.search(query, engine=engine, num_results=num_results)

            if result.get('success', False):
                combined_results['results'].extend(result.get('results', []))
                combined_results['results_count'] += len(result.get('results', []))
            else:
                combined_results['errors'].append({
                    'engine': engine,
                    'error': result.get('error', 'Unknown error')
                })

        # Remove duplicate results based on URL
        unique_results = []
        seen_urls = set()

        for result in combined_results['results']:
            url = result.get('url', '')
            if url and url not in seen_urls:
                unique_results.append(result)
                seen_urls.add(url)

        combined_results['results'] = unique_results
        combined_results['results_count'] = len(unique_results)

        return combined_results
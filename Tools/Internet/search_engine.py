import logging
import json
import time
from typing import Dict, Any, List, Optional, Union
from .web_client import WebClient

class SearchEngine:

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.web_client = WebClient(self.config.get('web_client'))
        self.logger = logging.getLogger(__name__)


        self.default_engine = self.config.get('default_engine', 'duckduckgo')


        self.api_keys = self.config.get('api_keys', {})


        self.rate_limits = self.config.get('rate_limits', {
            'duckduckgo': {'requests_per_hour': 100, 'seconds_between_requests': 2},
            'google': {'requests_per_day': 100, 'seconds_between_requests': 1},
            'bing': {'requests_per_month': 1000, 'seconds_between_requests': 1}
        })


        self.last_request_time = {}

    def search(self, query: str, engine: Optional[str] = None, 
               num_results: int = 10, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        engine = engine or self.default_engine
        engine = engine.lower()


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
        now = time.time()
        if engine in self.last_request_time:
            elapsed = now - self.last_request_time[engine]
            wait_time = self.rate_limits.get(engine, {}).get('seconds_between_requests', 1)

            if elapsed < wait_time:
                time.sleep(wait_time - elapsed)

        self.last_request_time[engine] = time.time()

    def _search_duckduckgo(self, query: str, num_results: int = 10, 
                          filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:




        url = "https://html.duckduckgo.com/html/"
        params = {
            'q': query,
            's': '0'                     
        }


        if filters:
            if 'time' in filters:
                params['df'] = filters['time']               
            if 'region' in filters:
                params['kl'] = filters['region']                 

        try:
            response = self.web_client.get(url, params=params)

            if 'error' in response:
                return {
                    'success': False,
                    'error': response['error'],
                    'results': []
                }


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

        api_key = self.api_keys.get('google', {}).get('api_key')
        cse_id = self.api_keys.get('google', {}).get('cse_id')

        if not api_key or not cse_id:
            self.logger.error("Google search requires API key and CSE ID")
            return {
                'success': False,
                'error': "Google search requires API key and CSE ID",
                'results': []
            }


        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': cse_id,
            'q': query,
            'num': min(num_results, 10),                                               
        }


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

        api_key = self.api_keys.get('bing', {}).get('api_key')

        if not api_key:
            self.logger.error("Bing search requires API key")
            return {
                'success': False,
                'error': "Bing search requires API key",
                'results': []
            }


        url = "https://api.bing.microsoft.com/v7.0/search"
        params = {
            'q': query,
            'count': min(num_results, 50)                                                
        }


        if filters:
            if 'freshness' in filters:
                params['freshness'] = filters['freshness']                          
            if 'market' in filters:
                params['mkt'] = filters['market']               
            if 'safe_search' in filters:
                params['safeSearch'] = filters['safe_search']                         

        try:

            headers = {'Ocp-Apim-Subscription-Key': api_key}
            self.web_client.session.headers.update(headers)

            response = self.web_client.get(url, params=params)


            self.web_client.session.headers.pop('Ocp-Apim-Subscription-Key', None)

            if 'error' in response:
                return {
                    'success': False,
                    'error': response['error'],
                    'results': []
                }

            content = response.get('content', {})


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

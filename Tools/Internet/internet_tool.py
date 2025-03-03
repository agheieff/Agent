import logging
import os
import json
from typing import Dict, Any, List, Optional, Union
from .web_client import WebClient
from .search_engine import SearchEngine

class InternetTool:

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.web_client = WebClient(self.config.get('web_client'))
        self.search_engine = SearchEngine(self.config.get('search_engine'))
        self.logger = logging.getLogger(__name__)


        self.cache = {
            'pages': {},
            'searches': {}
        }


        self.cache_size_limit = self.config.get('cache_size_limit', 100)

    def search(self, query: str, engine: Optional[str] = None, 
              num_results: int = 10, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        cache_key = f"{query}_{engine or 'default'}_{num_results}"
        if cache_key in self.cache['searches']:
            self.logger.info(f"Using cached search results for: {query}")
            return self.cache['searches'][cache_key]


        result = self.search_engine.search(query, engine, num_results, filters)


        if result.get('success', False):

            if len(self.cache['searches']) >= self.cache_size_limit:

                oldest_key = next(iter(self.cache['searches']))
                del self.cache['searches'][oldest_key]

            self.cache['searches'][cache_key] = result

        return result

    def browse(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        cache_key = url
        if cache_key in self.cache['pages']:
            self.logger.info(f"Using cached page for: {url}")
            return self.cache['pages'][cache_key]


        result = self.web_client.get(url, params)


        if 'error' not in result:

            if len(self.cache['pages']) >= self.cache_size_limit:

                oldest_key = next(iter(self.cache['pages']))
                del self.cache['pages'][oldest_key]

            self.cache['pages'][cache_key] = result

        return result

    def research(self, query: str, depth: int = 1, 
                max_pages: int = 3, summarize: bool = True) -> Dict[str, Any]:
        self.logger.info(f"Starting research on: {query}")


        research_results = {
            'query': query,
            'depth': depth,
            'max_pages': max_pages,
            'visited_pages': 0,
            'pages_info': [],
            'success': True,
            'errors': []
        }


        search_results = self.search_engine.get_search_results(
            query, 
            engines=self.config.get('research_engines', ['duckduckgo']),
            num_results=max_pages
        )

        if not search_results.get('success', False):
            research_results['success'] = False
            research_results['errors'].append({
                'phase': 'search',
                'error': 'Failed to get search results'
            })
            return research_results


        visited_urls = set()
        pages_to_visit = [(result['url'], 0) for result in search_results.get('results', [])]                

        while pages_to_visit and len(visited_urls) < max_pages * depth:
            current_url, current_depth = pages_to_visit.pop(0)


            if current_url in visited_urls or current_depth >= depth:
                continue


            try:
                self.logger.info(f"Visiting page: {current_url}")
                page_result = self.browse(current_url)

                if 'error' in page_result:
                    research_results['errors'].append({
                        'phase': 'browse',
                        'url': current_url,
                        'error': page_result['error']
                    })
                    continue


                main_content = self.web_client.extract_main_content(page_result.get('html', ''))


                page_info = {
                    'url': current_url,
                    'title': page_result.get('title', ''),
                    'content_summary': main_content[:1000] + ('...' if len(main_content) > 1000 else ''),
                    'depth': current_depth
                }

                research_results['pages_info'].append(page_info)
                visited_urls.add(current_url)
                research_results['visited_pages'] += 1


                if current_depth < depth - 1:
                    links = self.web_client.extract_links(page_result.get('html', ''), current_url)


                    for link in links[:max_pages]:                                         
                        pages_to_visit.append((link['url'], current_depth + 1))

            except Exception as e:
                self.logger.error(f"Error processing page {current_url}: {str(e)}")
                research_results['errors'].append({
                    'phase': 'browse',
                    'url': current_url,
                    'error': str(e)
                })

        return research_results

    def download(self, url: str, local_path: str) -> Dict[str, Any]:
        return self.web_client.download_file(url, local_path)

    def clear_cache(self) -> None:
        self.cache = {
            'pages': {},
            'searches': {}
        }
        self.logger.info("Cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        return {
            'pages_cached': len(self.cache['pages']),
            'searches_cached': len(self.cache['searches']),
            'cache_limit': self.cache_size_limit
        }

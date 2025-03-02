import requests
from bs4 import BeautifulSoup
import json
import logging
from typing import Dict, Any, Optional, Union

class WebClient:
    """A tool for Agent to access the internet and fetch content from websites."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the web client with optional configuration.
        
        Args:
            config: Configuration options including user agents, timeouts, etc.
        """
        self.config = config or {}
        self.session = requests.Session()
        
        # Set user agent if provided, otherwise use a default one
        user_agent = self.config.get('user_agent', 'Agent Research Assistant/1.0')
        self.session.headers.update({'User-Agent': user_agent})
        
        # Configure session with any proxy settings
        if 'proxy' in self.config:
            self.session.proxies.update(self.config['proxy'])
        
        self.logger = logging.getLogger(__name__)
    
    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetch content from a URL using GET method.
        
        Args:
            url: The URL to fetch content from
            params: Optional query parameters
            
        Returns:
            Dictionary containing response data and metadata
        """
        try:
            timeout = self.config.get('timeout', 30)
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '')
            
            result = {
                'status_code': response.status_code,
                'url': response.url,
                'headers': dict(response.headers),
                'content_type': content_type,
            }
            
            # Handle different content types
            if 'application/json' in content_type:
                result['content'] = response.json()
            elif 'text/html' in content_type:
                result['content'] = response.text
                result['html'] = response.text
                # Also parse HTML for easier access
                soup = BeautifulSoup(response.text, 'html.parser')
                result['title'] = soup.title.string if soup.title else None
                result['text'] = soup.get_text(separator=' ', strip=True)
            else:
                result['content'] = response.text
            
            return result
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching URL {url}: {str(e)}")
            return {
                'error': str(e),
                'url': url,
                'success': False
            }
    
    def post(self, url: str, data: Optional[Dict[str, Any]] = None, 
             json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send POST request to a URL.
        
        Args:
            url: The URL to send the POST request to
            data: Optional form data
            json_data: Optional JSON data
            
        Returns:
            Dictionary containing response data and metadata
        """
        try:
            timeout = self.config.get('timeout', 30)
            response = self.session.post(url, data=data, json=json_data, timeout=timeout)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '')
            
            result = {
                'status_code': response.status_code,
                'url': response.url,
                'headers': dict(response.headers),
                'content_type': content_type,
            }
            
            # Handle different content types
            if 'application/json' in content_type:
                result['content'] = response.json()
            else:
                result['content'] = response.text
            
            return result
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error posting to URL {url}: {str(e)}")
            return {
                'error': str(e),
                'url': url,
                'success': False
            }
    
    def extract_main_content(self, html: str) -> str:
        """Extract the main content from an HTML page, filtering out navigation, ads, etc.
        
        Args:
            html: HTML content to process
            
        Returns:
            Extracted main content as text
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove unwanted elements
        for unwanted in soup.select('nav, header, footer, script, style, [class*="ad"], [id*="ad"], .sidebar, #sidebar'):
            unwanted.extract()
        
        # Try to find main content
        main_content = None
        for selector in ['main', 'article', '.content', '#content', '.main', '#main']:
            content = soup.select_one(selector)
            if content:
                main_content = content
                break
        
        # If no main content container found, use body
        if not main_content:
            main_content = soup.body
        
        return main_content.get_text(separator='\n', strip=True) if main_content else ""
    
    def extract_links(self, html: str, base_url: str = "") -> list:
        """Extract all links from an HTML page.
        
        Args:
            html: HTML content to process
            base_url: Base URL to resolve relative links
            
        Returns:
            List of extracted links
        """
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            text = a_tag.get_text(strip=True)
            
            # Handle relative URLs
            if href.startswith('/') and base_url:
                href = base_url.rstrip('/') + href
            
            links.append({
                'url': href,
                'text': text
            })
        
        return links
    
    def download_file(self, url: str, local_path: str) -> Dict[str, Any]:
        """Download a file from a URL and save it locally.
        
        Args:
            url: URL of the file to download
            local_path: Local path to save the file
            
        Returns:
            Dictionary with download status and metadata
        """
        try:
            timeout = self.config.get('timeout', 60)  # Longer timeout for downloads
            with self.session.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                
                # Get content length if available
                content_length = response.headers.get('Content-Length')
                total_size = int(content_length) if content_length else None
                
                with open(local_path, 'wb') as f:
                    downloaded_size = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                
                return {
                    'success': True,
                    'url': url,
                    'local_path': local_path,
                    'file_size': downloaded_size,
                    'content_type': response.headers.get('Content-Type'),
                }
                
        except (requests.exceptions.RequestException, IOError) as e:
            self.logger.error(f"Error downloading file from {url}: {str(e)}")
            return {
                'success': False,
                'url': url,
                'error': str(e)
            }
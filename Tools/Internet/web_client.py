import requests
from bs4 import BeautifulSoup
import json
import logging
from typing import Dict, Any, Optional, Union

class WebClient:

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.session = requests.Session()


        user_agent = self.config.get('user_agent', 'Agent Research Assistant/1.0')
        self.session.headers.update({'User-Agent': user_agent})


        if 'proxy' in self.config:
            self.session.proxies.update(self.config['proxy'])

        self.logger = logging.getLogger(__name__)

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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


            if 'application/json' in content_type:
                result['content'] = response.json()
            elif 'text/html' in content_type:
                result['content'] = response.text
                result['html'] = response.text

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
        soup = BeautifulSoup(html, 'html.parser')


        for unwanted in soup.select('nav, header, footer, script, style, [class*="ad"], [id*="ad"], .sidebar, #sidebar'):
            unwanted.extract()


        main_content = None
        for selector in ['main', 'article', '.content', '#content', '.main', '#main']:
            content = soup.select_one(selector)
            if content:
                main_content = content
                break


        if not main_content:
            main_content = soup.body

        return main_content.get_text(separator='\n', strip=True) if main_content else ""

    def extract_links(self, html: str, base_url: str = "") -> list:
        soup = BeautifulSoup(html, 'html.parser')
        links = []

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            text = a_tag.get_text(strip=True)


            if href.startswith('/') and base_url:
                href = base_url.rstrip('/') + href

            links.append({
                'url': href,
                'text': text
            })

        return links

    def download_file(self, url: str, local_path: str) -> Dict[str, Any]:
        try:
            timeout = self.config.get('timeout', 60)                                
            with self.session.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()


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

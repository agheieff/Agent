import os
import requests
from typing import Dict, Any, Optional

"""
A simpler 'curl'-like tool for making HTTP requests.

Usage:
  /curl method=GET url="https://example.com" [data="..."] [headers="Key:Value,Another:Header"]
  /curl url="http://httpbin.org/post" method=POST data="foo=bar"

Parameters:
  method   - GET, POST, PUT, DELETE, etc. Defaults to GET
  url      - The URL to request (required)
  data     - Body data (string). For POST/PUT typically
  headers  - Comma-separated list of "Key:Value" pairs
  timeout  - Request timeout in seconds (default 20)
  allow_insecure - If True, skip SSL verification (default=False)

Note:
  This tool will only function if `allow_internet` is True in the agent config.
  Otherwise, it will refuse to send requests.
"""

def tool_curl(
    method: str = "GET",
    url: str = None,
    data: str = None,
    headers: str = None,
    timeout: int = 20,
    allow_insecure: bool = False,
    help: bool = False,
    value: str = None,
    **kwargs
) -> Dict[str, Any]:
    if help:
        return {
            "output": (
                "Send an HTTP request, similar to a basic curl.\n\n"
                "Usage:\n"
                "  /curl method=GET url=\"https://example.com\" [data=\"...\"] [headers=\"Key:Value\"]\n"
                "  /curl method=POST url=\"https://httpbin.org/post\" data=\"{\"key\":\"val\"}\" headers=\"Content-Type:application/json\"\n"
            ),
            "error": "",
            "success": True,
            "exit_code": 0
        }

    if not url and value:
        # If user wrote: /curl "https://example.com"
        url = value

    if not url:
        return {
            "output": "",
            "error": "Missing 'url' parameter.",
            "success": False,
            "exit_code": 1
        }

    # Handle headers
    parsed_headers = {}
    if headers:
        # Split by commas, then by colon
        for kv in headers.split(","):
            kv = kv.strip()
            if ":" in kv:
                k, v = kv.split(":", 1)
                parsed_headers[k.strip()] = v.strip()

    # We'll let the Manager or config check the "allow_internet" setting.
    # This function just does the request if authorized.
    try:
        method = method.upper()
        verify_ssl = not allow_insecure
        req_func = getattr(requests, method.lower(), None)
        if not req_func:
            return {
                "output": "",
                "error": f"Unsupported method: {method}",
                "success": False,
                "exit_code": 1
            }

        if data and (method in ["POST","PUT","PATCH"]):
            # Attempt JSON parse? We'll just do raw data for simplicity
            resp = req_func(url, data=data, headers=parsed_headers, timeout=timeout, verify=verify_ssl)
        else:
            resp = req_func(url, headers=parsed_headers, timeout=timeout, verify=verify_ssl)

        return {
            "output": f"Status: {resp.status_code}\n\n{resp.text}",
            "error": "",
            "success": True,
            "exit_code": 0
        }

    except requests.exceptions.RequestException as e:
        return {
            "output": "",
            "error": f"HTTP request error: {str(e)}",
            "success": False,
            "exit_code": 1
        }

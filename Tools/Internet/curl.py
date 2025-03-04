import requests
from typing import Dict, Any
import os

TOOL_NAME = "curl"
TOOL_DESCRIPTION = "Send an HTTP request (GET, POST, etc.), similar to a basic curl."
TOOL_HELP = """
Usage:
  /curl method=<HTTP method> url=<url> [data=<data>] [headers=<header1:value1,header2:value2>] [timeout=<seconds>] [allow_insecure=<true|false>]

Description:
  Sends an HTTP request using the specified method (GET, POST, etc.) to the given URL.
  Optional data and headers can be provided. The 'timeout' parameter (in seconds) is optional,
  and 'allow_insecure' can be set to true to disable SSL verification.
"""
TOOL_EXAMPLES = [
    ("/curl method=GET url=http://example.com", "Sends a GET request to example.com."),
    ("/curl method=POST url=http://example.com/api data='{\"key\":\"value\"}'", "Sends a POST request with JSON data.")
]

async def tool_curl(
    method: str = "GET",
    url: str = None,
    data: str = None,
    headers: str = None,
    timeout: int = 20,
    allow_insecure: bool = False,
    **kwargs
) -> Dict[str, Any]:
    if not url:
        return {
            "output": "",
            "error": "Missing 'url' parameter",
            "success": False,
            "exit_code": 1
        }

    parsed_headers = {}
    if headers:
        for kv in headers.split(","):
            kv = kv.strip()
            if ":" in kv:
                k, v = kv.split(":", 1)
                parsed_headers[k.strip()] = v.strip()

    method = method.upper()
    verify_ssl = not allow_insecure

    try:
        req_func = getattr(requests, method.lower(), None)
        if not req_func:
            return {
                "output": "",
                "error": f"Unsupported method: {method}",
                "success": False,
                "exit_code": 1
            }
        if data and method in ["POST", "PUT", "PATCH"]:
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

import requests
from typing import Dict, Any
import os

TOOL_NAME = "curl"
TOOL_DESCRIPTION = "Send an HTTP request (GET, POST, etc.), similar to a basic curl."

async def tool_curl(
    method: str = "GET",
    url: str = None,
    data: str = None,
    headers: str = None,
    timeout: int = 20,
    allow_insecure: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Make a simple HTTP request. JSON usage example:
    {
      "name": "curl",
      "params": {
        "method": "POST",
        "url": "https://example.com/api",
        "data": "some=payload",
        "headers": "Content-Type:application/x-www-form-urlencoded",
        "timeout": 10,
        "allow_insecure": false
      }
    }
    """
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

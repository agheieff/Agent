import pytest
import requests_mock
from Tools.Internet.curl import tool_curl

@pytest.mark.asyncio
class TestCurlTool:

    async def test_curl_help(self):
        result = tool_curl(help=True)
        assert result["success"] is True
        assert "Usage:" in result["output"]

    async def test_curl_missing_url(self):
        result = tool_curl(method="GET")
        assert result["success"] is False
        assert "Missing 'url'" in result["error"]

    async def test_curl_get_ok(self):
        with requests_mock.Mocker() as m:
            m.get("https://example.com", text="Hello from example")
            result = tool_curl(url="https://example.com", method="GET")
            assert result["success"] is True
            assert "Hello from example" in result["output"]

    async def test_curl_post_data(self):
        with requests_mock.Mocker() as m:
            m.post("http://test.local/submit", text="POST Received", status_code=201)
            result = tool_curl(url="http://test.local/submit", method="POST", data="Some data")
            assert result["success"] is True
            assert "POST Received" in result["output"]
            assert "Status: 201" in result["output"]

    async def test_curl_unsupported_method(self):
        result = tool_curl(url="https://example.com", method="SOMETHING")
        assert result["success"] is False
        assert "Unsupported method" in result["error"]

import pytest
import requests_mock
from Tools.Internet.curl import tool_curl

@pytest.mark.asyncio
class TestCurlTool:

    async def test_missing_url(self):
        result = await tool_curl()
        assert result["success"] is False
        assert "Missing 'url'" in result["error"]

    async def test_get_request(self):
        with requests_mock.Mocker() as m:
            m.get("http://example.com", text="Hello world", status_code=200)
            result = await tool_curl(method="GET", url="http://example.com")
            assert result["success"] is True
            assert "Hello world" in result["output"]
            assert "Status: 200" in result["output"]

    async def test_post_request(self):
        with requests_mock.Mocker() as m:
            m.post("http://example.com/post", text="Posted", status_code=201)
            result = await tool_curl(method="POST", url="http://example.com/post", data="x=1")
            assert result["success"] is True
            assert "Posted" in result["output"]
            assert "Status: 201" in result["output"]

    async def test_unsupported_method(self):
        result = await tool_curl(method="WHATEVER", url="http://example.com")
        assert result["success"] is False
        assert "Unsupported method:" in result["error"]

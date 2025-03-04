import pytest
import requests_mock
import os
from Tools.Telegram.view_messages import tool_telegram_view

@pytest.mark.asyncio
class TestTelegramViewTool:

    async def test_no_token(self):
        original = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        result = tool_telegram_view()
        assert result["success"] is False
        assert "No Telegram bot token" in result["error"]
        if original:
            os.environ["TELEGRAM_BOT_TOKEN"] = original

    async def test_view_no_messages(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE"
        with requests_mock.Mocker() as m:
            m.get("https://api.telegram.org/botFAKE/getUpdates",
                  json={"ok": True, "result": []}, status_code=200)
            result = tool_telegram_view(limit=5)
            assert result["success"] is True
            assert "No new messages available." in result["output"]
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    async def test_view_some_messages(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE"
        sample = {
            "ok": True,
            "result": [
                {
                    "update_id": 101,
                    "message": {
                        "text": "Hello from user",
                        "from": {"username": "testuser"}
                    }
                }
            ]
        }
        with requests_mock.Mocker() as m:
            m.get("https://api.telegram.org/botFAKE/getUpdates",
                  json=sample, status_code=200)
            result = tool_telegram_view(limit=5)
            assert result["success"] is True
            assert "Hello from user" in result["output"]
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

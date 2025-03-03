import pytest
import requests_mock
import os

from Tools.Telegram.view_messages import tool_telegram_view

@pytest.mark.asyncio
class TestTelegramViewTool:

    async def test_help_parameter(self):
        result = tool_telegram_view(help=True)
        assert result["success"] is True
        assert "View recent messages received by your Telegram bot" in result["output"]

    async def test_no_token_in_env_or_param(self):
        original_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        result = tool_telegram_view()
        assert result["success"] is False
        assert "No Telegram bot token provided" in result["error"]
        if original_token:
            os.environ["TELEGRAM_BOT_TOKEN"] = original_token

    async def test_view_no_new_messages(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE_BOT_TOKEN"
        with requests_mock.Mocker() as m:
            m.get("https://api.telegram.org/botFAKE_BOT_TOKEN/getUpdates",
                  json={"ok": True, "result": []}, status_code=200)
            result = tool_telegram_view(limit=5)
            assert result["success"] is True
            assert "No new messages available." in result["output"]
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    async def test_view_messages_success(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE_BOT_TOKEN"
        sample_updates = {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "message": {
                        "text": "Hello from user",
                        "from": {"username": "testuser"}
                    }
                },
                {
                    "update_id": 101,
                    "message": {
                        "text": "Another message",
                        "from": {"first_name": "Alice"}
                    }
                }
            ]
        }
        with requests_mock.Mocker() as m:
            m.get("https://api.telegram.org/botFAKE_BOT_TOKEN/getUpdates",
                  json=sample_updates, status_code=200)
            result = tool_telegram_view(limit=5)
            assert result["success"] is True
            assert "Recent Telegram messages" in result["output"]
            assert "update_id=100, from=testuser, text=Hello from user" in result["output"]
            assert "update_id=101, from=Alice, text=Another message" in result["output"]
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    async def test_telegram_api_error(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE_BOT_TOKEN"
        with requests_mock.Mocker() as m:
            m.get("https://api.telegram.org/botFAKE_BOT_TOKEN/getUpdates",
                  json={"ok": False, "description": "Something went wrong"}, status_code=400)
            result = tool_telegram_view()
            assert result["success"] is False
            assert "Telegram API error" in result["error"]
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

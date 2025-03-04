import pytest
import requests_mock
import os
from Tools.Telegram.send import tool_telegram_send

@pytest.mark.asyncio
class TestTelegramSendTool:

    async def test_no_token_or_env(self):
        # Remove env token if present
        original_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        result = tool_telegram_send(message="hi")
        assert result["success"] is False
        assert "No Telegram bot token provided" in result["error"]

        if original_token:
            os.environ["TELEGRAM_BOT_TOKEN"] = original_token

    async def test_no_chat_id(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "TEST_TOKEN"
        original_cid = os.environ.pop("TELEGRAM_CHAT_ID", None)

        result = tool_telegram_send(message="test msg")
        assert result["success"] is False
        assert "No Telegram chat ID provided." in result["error"]

        if original_cid:
            os.environ["TELEGRAM_CHAT_ID"] = original_cid
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    async def test_send_ok(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE"
        os.environ["TELEGRAM_CHAT_ID"] = "123"

        with requests_mock.Mocker() as m:
            m.post("https://api.telegram.org/botFAKE/sendMessage",
                   json={"ok": True, "result": {"message_id": 100}}, status_code=200)
            result = tool_telegram_send(message="Hello")
            assert result["success"] is True
            assert "Message sent successfully" in result["output"]

        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)

import pytest
import requests_mock
import os

from Tools.Telegram.send import tool_telegram_send

@pytest.mark.asyncio
class TestTelegramSendTool:

    async def test_help_parameter(self):
        result = tool_telegram_send(help=True)
        assert result["success"] is True
        assert "Send a message via Telegram" in result["output"]

    async def test_no_token_in_env_or_param(self):
        # Make sure the environment variable is not set
        original_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)

        result = tool_telegram_send(message="Hello")
        assert result["success"] is False
        assert "No Telegram bot token provided" in result["error"]

        # Restore
        if original_token:
            os.environ["TELEGRAM_BOT_TOKEN"] = original_token

    async def test_no_chat_id_in_env_or_param(self):
        # Provide a token but not a chat_id
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE_BOT_TOKEN"
        original_chat_id = os.environ.pop("TELEGRAM_CHAT_ID", None)

        result = tool_telegram_send(message="Hello")
        assert result["success"] is False
        assert "No Telegram chat ID" in result["error"]

        # Restore
        if original_chat_id:
            os.environ["TELEGRAM_CHAT_ID"] = original_chat_id
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    async def test_no_message_provided(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE_BOT_TOKEN"
        os.environ["TELEGRAM_CHAT_ID"] = "123456"

        result = tool_telegram_send()
        assert result["success"] is False
        assert "No message text provided" in result["error"]

        # Cleanup
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)

    async def test_send_message_success(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE_BOT_TOKEN"
        os.environ["TELEGRAM_CHAT_ID"] = "123456"

        with requests_mock.Mocker() as m:
            # Mock Telegram API response
            m.post("https://api.telegram.org/botFAKE_BOT_TOKEN/sendMessage",
                   json={"ok": True, "result": {"message_id": 1}}, status_code=200)

            result = tool_telegram_send(message="Hello via test")
            assert result["success"] is True
            assert "Message sent successfully" in result["output"]

        # Cleanup
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)

    async def test_send_message_telegram_error(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "FAKE_BOT_TOKEN"
        os.environ["TELEGRAM_CHAT_ID"] = "123456"

        with requests_mock.Mocker() as m:
            # Mock a failure response from Telegram
            m.post("https://api.telegram.org/botFAKE_BOT_TOKEN/sendMessage",
                   json={"ok": False, "error_code": 400, "description": "Bad Request"},
                   status_code=400)

            result = tool_telegram_send(message="Hello fail test")
            assert result["success"] is False
            assert "Telegram API error" in result["error"]

        # Cleanup
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)

import os
import requests
from typing import Dict, Any

"""
Tool for sending a message via Telegram.

Usage:
  /telegram_send message="Hello, world!"
  /telegram_send token=<your_bot_token> chat_id=<your_chat_id> message="Custom message"

Environment variables:
  TELEGRAM_BOT_TOKEN - Default bot token (if not overridden by tool params)
  TELEGRAM_CHAT_ID   - Default chat ID  (if not overridden by tool params)
"""

def tool_telegram_send(
    message: str = None,
    token: str = None,
    chat_id: str = None,
    help: bool = False,
    value: str = None,
    **kwargs
) -> Dict[str, Any]:

    if help:
        return {
            "output": (
                "Send a message via Telegram.\n\n"
                "Usage:\n"
                "  /telegram_send message=\"Hello world\"\n"
                "  /telegram_send token=<BOT_TOKEN> chat_id=<CHAT_ID> message=\"Any message\"\n\n"
                "You can also rely on environment variables:\n"
                "  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID\n"
            ),
            "error": "",
            "success": True,
            "exit_code": 0
        }

    if not message and value:
        message = value

    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    default_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        chat_id = default_chat_id

    if not bot_token.strip():
        return {
            "output": "",
            "error": "No Telegram bot token provided (TELEGRAM_BOT_TOKEN env or 'token=...' param).",
            "success": False,
            "exit_code": 1
        }
    if not chat_id.strip():
        return {
            "output": "",
            "error": "No Telegram chat ID provided (TELEGRAM_CHAT_ID env or 'chat_id=...' param).",
            "success": False,
            "exit_code": 1
        }

    if not message or not message.strip():
        return {
            "output": "",
            "error": "No message text provided.",
            "success": False,
            "exit_code": 1
        }

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            return {
                "output": "",
                "error": f"Telegram API error: {data}",
                "success": False,
                "exit_code": 1
            }

        return {
            "output": f"Message sent successfully to chat {chat_id}.",
            "error": "",
            "success": True,
            "exit_code": 0
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Telegram API error: {str(e)}",
            "success": False,
            "exit_code": 1
        }

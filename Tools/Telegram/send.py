import os
import requests
from typing import Dict, Any

"""
Tool for sending a message via Telegram.

Usage:
  /telegram_send message="Hello, world!"
  /telegram_send token=<your_bot_token> chat_id=<your_chat_id> message="Custom message"

Priority order for token/chat_id:
  1. Direct parameter to the tool
  2. `config["telegram"]["token"]` or `config["telegram"]["chat_id"]` (if passed in)
  3. Environment variables TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
"""

TOOL_NAME = "telegram_send"
TOOL_DESCRIPTION = "Send a message via Telegram"
TOOL_HELP = """
Send a message via Telegram.

Usage:
  /telegram_send message="Hello world"
  /telegram_send token=<BOT_TOKEN> chat_id=<CHAT_ID> message="Any message"

You can also rely on:
- config["telegram"]["token"] and config["telegram"]["chat_id"], or
- environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

Priority order for picking up token/chat_id:
  1) Tool parameter
  2) Config
  3) Environment variable
"""
TOOL_EXAMPLES = [
    ("/telegram_send message=\"Hello world\"", "Send 'Hello world' using config or environment variables for token/chat_id"),
    ("/telegram_send token=123:abc chat_id=9999999999 message=\"Custom message\"", "Specify token and chat_id explicitly"),
]

def tool_telegram_send(
    message: str = None,
    token: str = None,
    chat_id: str = None,
    config: Dict[str, Any] = None,
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
                "You can also rely on config['telegram'] or environment variables.\n"
            ),
            "error": "",
            "success": True,
            "exit_code": 0
        }

    if not message and value:
        message = value


    if not token or not token.strip():
        if config:
            token = config.get("telegram", {}).get("token", "")
    if not token or not token.strip():
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")


    if not chat_id or not chat_id.strip():
        if config:
            chat_id = config.get("telegram", {}).get("chat_id", "")
    if not chat_id or not chat_id.strip():
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")


    if not token.strip():
        return {
            "output": "",
            "error": "No Telegram bot token provided (check tool params, config, or TELEGRAM_BOT_TOKEN).",
            "success": False,
            "exit_code": 1
        }
    if not chat_id.strip():
        return {
            "output": "",
            "error": "No Telegram chat ID provided (check tool params, config, or TELEGRAM_CHAT_ID).",
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
        url = f"https://api.telegram.org/bot{token}/sendMessage"
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

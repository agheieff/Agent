import os
import requests
from typing import Dict, Any

TOOL_NAME = "telegram_send"
TOOL_DESCRIPTION = "Send a message via Telegram to a specified chat_id."

EXAMPLES = {
    "message": "Hello from the agent!",
    "token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
    "chat_id": "12345678"
}

FORMATTER = "telegram"

def tool_telegram_send(
    message: str,
    token: str = None,
    chat_id: str = None,
    config: Dict[str, Any] = None,
    **kwargs
) -> Dict[str, Any]:
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
            "error": "No Telegram bot token provided.",
            "success": False,
            "exit_code": 1
        }
    if not chat_id.strip():
        return {
            "output": "",
            "error": "No Telegram chat ID provided.",
            "success": False,
            "exit_code": 1
        }
    if not message:
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
            "output": f"Message sent via Telegram to chat {chat_id}",
            "error": "",
            "success": True,
            "exit_code": 0,
            "message": message,
            "chat_id": chat_id
        }
    except Exception as e:
        return {
            "output": "",
            "error": f"Telegram API error: {str(e)}",
            "success": False,
            "exit_code": 1
        }

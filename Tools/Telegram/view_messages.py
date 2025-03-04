import os
import requests
from typing import Dict, Any

TOOL_NAME = "telegram_view"
TOOL_DESCRIPTION = "View recent messages received by your Telegram bot."
TOOL_HELP = """
Usage:
  /telegram_view [limit=<number>] [offset=<offset>] [token=<bot token>]

Description:
  Retrieves recent messages for your Telegram bot.
  The 'limit' parameter controls how many messages to return.
  Optionally, an offset or bot token can be provided.
"""
TOOL_EXAMPLES = [
    ("/telegram_view limit=5", "Displays the 5 most recent messages.")
]

def tool_telegram_view(
    limit: int = 5,
    offset: int = None,
    token: str = None,
    config: Dict[str, Any] = None,
    **kwargs
) -> Dict[str, Any]:
    if not token or not token.strip():
        if config:
            token = config.get("telegram", {}).get("token", "")
    if not token or not token.strip():
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    if not token.strip():
        return {
            "output": "",
            "error": "No Telegram bot token provided.",
            "success": False,
            "exit_code": 1
        }

    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params = {}
        if offset is not None:
            params["offset"] = offset

        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            return {
                "output": "",
                "error": f"Telegram API error: {data}",
                "success": False,
                "exit_code": 1
            }

        messages = data.get("result", [])
        if not messages:
            return {
                "output": "No new messages available.",
                "error": "",
                "success": True,
                "exit_code": 0
            }

        messages = messages[-limit:]
        lines = []
        for m in messages:
            update_id = m.get("update_id")
            msg = m.get("message")
            text = ""
            sender = ""
            if msg:
                text = msg.get("text", "")
                sender_info = msg.get("from", {})
                sender = sender_info.get("username") or sender_info.get("first_name", "")
            lines.append(f"update_id={update_id}, from={sender}, text={text}")

        output_text = "Recent Telegram messages:\n\n" + "\n".join(lines)
        return {
            "output": output_text,
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

import os
import requests
from typing import Dict, Any

"""
Tool for viewing recent Telegram messages.

Usage:
  /telegram_view [limit=N]
  /telegram_view token=<BOT_TOKEN> offset=<update_id>

Priority order for token:
  1. Direct parameter to the tool
  2. `config["telegram"]["token"]` (if passed in)
  3. Environment variable TELEGRAM_BOT_TOKEN

Likewise for chat_id if needed. But typically for getUpdates, chat_id is not required.
"""

TOOL_NAME = "telegram_view"
TOOL_DESCRIPTION = "View recent messages received by your Telegram bot"
TOOL_HELP = """
View recent messages received by your Telegram bot.

Usage:
  /telegram_view [limit=N] [offset=update_id]
  /telegram_view token=<BOT_TOKEN> limit=10

You can rely on config['telegram']['token'] or environment variable TELEGRAM_BOT_TOKEN as well.
"""
TOOL_EXAMPLES = [
    ("/telegram_view limit=5", "Show the last 5 updates"),
    ("/telegram_view token=123:abc offset=100", "Use token 123:abc and show updates after update_id=100"),
]

def tool_telegram_view(
    limit: int = 5,
    token: str = None,
    offset: int = None,
    config: Dict[str, Any] = None,
    help: bool = False,
    value: str = None,
    **kwargs
) -> Dict[str, Any]:

    if help:
        return {
            "output": (
                "View recent messages received by your Telegram bot.\n\n"
                "Usage:\n"
                "  /telegram_view [limit=N] [offset=update_id]\n"
                "  /telegram_view token=<BOT_TOKEN> limit=10\n\n"
                "You can also rely on config['telegram']['token'] or environment variables.\n"
            ),
            "error": "",
            "success": True,
            "exit_code": 0
        }


    if not token or not token.strip():
        if config:
            token = config.get("telegram", {}).get("token", "")
    if not token or not token.strip():
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    if not isinstance(limit, int) and value:
        try:
            limit = int(value)
        except:
            pass

    if not limit or limit < 1:
        limit = 5

    if not token.strip():
        return {
            "output": "",
            "error": "No Telegram bot token provided (check tool param, config, or TELEGRAM_BOT_TOKEN).",
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
        formatted = []
        for m in messages:
            update_id = m.get("update_id")
            text = None
            sender = None
            if "message" in m:
                text = m["message"].get("text")
                from_data = m["message"].get("from")
                if from_data:
                    sender = from_data.get("username") or from_data.get("first_name")
            formatted.append(f"update_id={update_id}, from={sender}, text={text}")

        output_text = "Recent Telegram messages:\n\n" + "\n".join(formatted)
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

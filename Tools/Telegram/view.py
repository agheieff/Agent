import os
import requests
from typing import Dict, Any

"""
Tool for viewing recent Telegram messages.

Usage:
  /telegram_view [limit=N]
  /telegram_view token=<BOT_TOKEN> offset=<update_id>

Environment variables:
  TELEGRAM_BOT_TOKEN - Default bot token (if not overridden by tool params)

Notes:
  - This uses getUpdates. By default, it will show the last 'limit' messages
    that the bot has not processed, or that remain in the queue.
  - You can also supply 'offset' to fetch messages beyond that offset.
"""

def tool_telegram_view(
    limit: int = 5,
    token: str = None,
    offset: int = None,
    help: bool = False,
    value: str = None,
    **kwargs
) -> Dict[str, Any]:
    """Retrieve recent messages sent to the bot."""

    if help:
        return {
            "output": (
                "View recent messages received by your Telegram bot.\n\n"
                "Usage:\n"
                "  /telegram_view [limit=N] [offset=update_id]\n"
                "  /telegram_view token=<BOT_TOKEN> limit=10\n\n"
                "Environment:\n"
                "  TELEGRAM_BOT_TOKEN for default bot token\n"
            ),
            "error": "",
            "success": True,
            "exit_code": 0
        }

    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token.strip():
        return {
            "output": "",
            "error": "No Telegram bot token provided (env or param).",
            "success": False,
            "exit_code": 1
        }

    # For a positional param like /telegram_view 5
    if not isinstance(limit, int) and value:
        try:
            limit = int(value)
        except:
            pass

    if not limit or limit < 1:
        limit = 5

    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
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

        # Show the last `limit` messages
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
            "error": f"Error retrieving Telegram messages: {str(e)}",
            "success": False,
            "exit_code": 1
        }

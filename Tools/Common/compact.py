import logging
from typing import Dict, Any, List, Optional

from Prompts.compact import get_compact_prompt

TOOL_NAME = "compact"
TOOL_DESCRIPTION = "Summarize the conversation so far and replace it with a concise summary"


EXAMPLES = {}

FORMATTER = "status"

logger = logging.getLogger(__name__)

async def tool_compact(
    conversation_history: List[Dict[str, str]] = None,
    llm: Any = None,
    **kwargs
) -> Dict[str, Any]:
    if not conversation_history or not isinstance(conversation_history, list):
        return {
            "output": "",
            "error": "No valid conversation history provided to /compact tool.",
            "success": False,
            "exit_code": 1
        }

    if not llm:
        return {
            "output": "",
            "error": "No LLM provided to /compact tool.",
            "success": False,
            "exit_code": 1
        }

    user_and_assistant_messages = [
        msg["content"]
        for msg in conversation_history
        if msg["role"] in ("user", "assistant")
    ]
    if not user_and_assistant_messages:
        return {
            "output": "No user or assistant messages to summarize.",
            "error": "",
            "success": True,
            "exit_code": 0,
            "status": "No messages to compact"
        }

    conversation_text = "\n".join(user_and_assistant_messages)
    prompt_for_summary = get_compact_prompt()

    try:
        async def _get_summary():
            return await llm.get_response(
                prompt=prompt_for_summary,
                system=None,
                conversation_history=[{"role": "user", "content": conversation_text}],
                temperature=0.5,
                max_tokens=1024
            )

        summary_resp = await _get_summary()
        system_content = None
        if conversation_history and conversation_history[0]["role"] == "system":
            system_content = conversation_history[0]["content"]

        conversation_history.clear()
        if system_content:
            conversation_history.append({"role": "system", "content": system_content})

        summary_text = summary_resp or ""
        conversation_history.append({"role": "assistant", "content": summary_text})

        return {
            "output": "Conversation has been compacted into a summary.",
            "error": "",
            "success": True,
            "exit_code": 0,
            "status": "Conversation compacted",
            "summary": summary_text
        }
    except Exception as e:
        logger.exception("Error while summarizing conversation in compact tool")
        return {
            "output": "",
            "error": f"Error generating summary: {str(e)}",
            "success": False,
            "exit_code": 1
        }

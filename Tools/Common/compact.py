import logging
from typing import Dict, Any, List
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
            "error": "No valid conversation history provided to compact tool.",
            "exit_code": 1
        }
    if not llm:
        return {
            "output": "",
            "error": "No LLM provided to compact tool.",
            "exit_code": 1
        }
    user_and_assistant = [
        msg["content"] for msg in conversation_history if msg["role"] in ("user", "assistant")
    ]
    if not user_and_assistant:
        return {
            "output": "No user or assistant messages to summarize.",
            "error": "",
            "exit_code": 0
        }
    conversation_text = "\n".join(user_and_assistant)
    prompt = get_compact_prompt()
    try:
        summary = await llm.get_response(
            prompt=prompt,
            system=None,
            conversation_history=[{"role": "user", "content": conversation_text}],
            temperature=0.5,
            max_tokens=1024
        )
        # Clear existing conversation except system prompt if present.
        system_content = conversation_history[0]["content"] if conversation_history and conversation_history[0]["role"] == "system" else None
        conversation_history.clear()
        if system_content:
            conversation_history.append({"role": "system", "content": system_content})
        conversation_history.append({"role": "assistant", "content": summary or ""})
        return {
            "output": "Conversation has been compacted.",
            "error": "",
            "exit_code": 0,
            "summary": summary or ""
        }
    except Exception as e:
        logger.exception("Error in compact tool")
        return {
            "output": "",
            "error": f"Error generating summary: {str(e)}",
            "exit_code": 1
        }

def display_format(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    if result.get("exit_code", 1) == 0:
        return "[COMPACT]"
    else:
        return f"[COMPACT] Error: {result.get('error', 'Unknown error')}"

import logging
from typing import Dict, Any, List, Optional

from Prompts.compact import get_compact_prompt

TOOL_NAME = "compact"
TOOL_DESCRIPTION = "Summarize the conversation so far and replace it with a concise summary"
TOOL_HELP = """
Usage:
  /compact

No additional parameters are required.

Description:
  Summarizes the entire conversation so far. The tool calls the LLM with a special 
  prompt that requests a concise summary of the conversation. Then it replaces the 
  conversation history with the single summary message.
  
  This helps to reduce token usage and keep the conversation history manageable.
"""
TOOL_EXAMPLES = [
    ("/compact", "Summarize the entire conversation and replace it with the summary.")
]

logger = logging.getLogger(__name__)

def tool_compact(
    conversation_history: List[Dict[str, str]] = None,
    llm: Any = None,
    help: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Summarizes the conversation so far using the given LLM
    and replaces the entire conversation with that summary.
    """
    if help:
        example_text = "\nExamples:\n" + "\n".join(
            [f"  {ex[0]}\n    {ex[1]}" for ex in TOOL_EXAMPLES]
        )
        return {
            "output": f"{TOOL_DESCRIPTION}\n\n{TOOL_HELP}{example_text}",
            "error": "",
            "success": True,
            "exit_code": 0
        }

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

    # Gather everything except system messages, ignoring role=system
    user_and_assistant_messages = [
        msg["content"]
        for msg in conversation_history
        if msg["role"] in ("user", "assistant")
    ]
    if not user_and_assistant_messages:
        # There's nothing to summarize
        return {
            "output": "No user or assistant messages to summarize.",
            "error": "",
            "success": True,
            "exit_code": 0
        }

    conversation_text = "\n".join(user_and_assistant_messages)

    # Use the "compact prompt"
    prompt_for_summary = get_compact_prompt()

    # We do a synchronous call to the LLM or an async call? The standard tools are synchronous?
    # We'll do this as if we had an async call, but typically we can do synchronous in the tool.
    # The rest of the Tools are not strictly async, but let's be consistent with the base approach.

    try:
        import asyncio
        # Because the LLM is typically used with "await llm.get_response(...)"
        # We'll do an async helper:
        async def _get_summary():
            return await llm.get_response(
                prompt=prompt_for_summary,
                system=None,
                conversation_history=[{"role": "user", "content": conversation_text}],
                temperature=0.5,
                max_tokens=1024
            )

        loop = asyncio.get_event_loop()
        summary_resp = loop.run_until_complete(_get_summary())  # Synchronously wait

        # Clear conversation except for the system role (if the first message is system)
        system_content = None
        if conversation_history and conversation_history[0]["role"] == "system":
            system_content = conversation_history[0]["content"]

        conversation_history.clear()
        if system_content:
            conversation_history.append({"role": "system", "content": system_content})

        # Add the summary as an assistant message
        summary_text = summary_resp or ""
        conversation_history.append({"role": "assistant", "content": summary_text})

        return {
            "output": "Conversation has been compacted into a summary.",
            "error": "",
            "success": True,
            "exit_code": 0
        }
    except Exception as e:
        logger.exception("Error while summarizing conversation in compact tool")
        return {
            "output": "",
            "error": f"Error generating summary: {str(e)}",
            "success": False,
            "exit_code": 1
        }

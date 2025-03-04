import pytest
import asyncio

from Tools.Common.compact import tool_compact

class MockLLM:
    async def get_response(
        self,
        prompt: str,
        system: str,
        conversation_history: list,
        temperature: float = 0.5,
        max_tokens: int = 1024,
        **kwargs
    ):

        return "This is a MOCK summary of the conversation."

@pytest.mark.asyncio
class TestCompactTool:

    async def test_no_conversation_provided(self):
        result = await tool_compact(llm=MockLLM())
        assert result["success"] is False
        assert "No valid conversation history" in result["error"]

    async def test_no_llm_provided(self):
        conversation_history = [
            {"role": "user", "content": "Hello, I'd like to summarize."}
        ]
        result = await tool_compact(conversation_history=conversation_history)
        assert result["success"] is False
        assert "No LLM provided" in result["error"]

    async def test_no_user_or_assistant_messages_to_summarize(self):
        conversation_history = [
            {"role": "system", "content": "System instructions."}
        ]
        result = await tool_compact(conversation_history=conversation_history, llm=MockLLM())
        assert result["success"] is True
        assert "No user or assistant messages to summarize." in result["output"]

    async def test_summarize_successful(self):
        conversation_history = [
            {"role": "system", "content": "System prompt..."},
            {"role": "user", "content": "Hello there!"},
            {"role": "assistant", "content": "Hi, how can I help?"}
        ]

        result = await tool_compact(conversation_history=conversation_history, llm=MockLLM())
        assert result["success"] is True
        assert "Conversation has been compacted" in result["output"]

        assert len(conversation_history) == 2
        assert "MOCK summary" in conversation_history[-1]["content"]

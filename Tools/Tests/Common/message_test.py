import pytest
import asyncio
from Tools.Common.message import tool_message, EXAMPLES

@pytest.mark.asyncio
async def test_message_success():
    result = await tool_message(text="Hello, this is a test message")
    assert result["exit_code"] == 0
    assert result["output"] == "Hello, this is a test message"
    assert result.get("message") == "Hello, this is a test message"
    assert result["error"] == ""

@pytest.mark.asyncio
async def test_message_empty():
    result = await tool_message(text="")
    assert result["exit_code"] != 0
    assert "Missing required parameter" in result["error"]

@pytest.mark.asyncio
async def test_message_special_characters():
    special_msg = "Testing!\n\nWith newlines and *special* characters: 🚀 😀 🔥"
    result = await tool_message(text=special_msg)
    assert result["exit_code"] == 0
    assert result.get("message") == special_msg
    assert result["output"] == special_msg

def test_examples():
    assert isinstance(EXAMPLES, dict)
    assert "text" in EXAMPLES
    assert isinstance(EXAMPLES["text"], str)

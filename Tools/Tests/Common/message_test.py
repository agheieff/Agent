import pytest
import os
import sys


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from Tools.Common.message import tool_message, EXAMPLES


@pytest.mark.asyncio
async def test_message_success():

    result = await tool_message(text="Hello, this is a test message")


    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["output"] == "Hello, this is a test message"
    assert result["message"] == "Hello, this is a test message"
    assert result["error"] == ""


@pytest.mark.asyncio
async def test_message_empty():

    result = await tool_message(text="")


    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "error" in result
    assert "Missing required parameter: text" in result["error"]


@pytest.mark.asyncio
async def test_message_special_characters():

    special_msg = "Testing!\n\nWith newlines and *special* characters: 🚀 😀 🔥"
    result = await tool_message(text=special_msg)


    assert result["success"] is True
    assert result["message"] == special_msg
    assert result["output"] == special_msg


def test_examples():

    assert isinstance(EXAMPLES, dict)
    assert "text" in EXAMPLES
    assert isinstance(EXAMPLES["text"], str)

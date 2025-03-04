import pytest
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from Tools.Common.message import tool_message, EXAMPLES


@pytest.mark.asyncio
async def test_message_success():
    # Call the tool with a valid message
    result = await tool_message(text="Hello, this is a test message")
    
    # Check the result structure
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["output"] == "Hello, this is a test message"
    assert result["message"] == "Hello, this is a test message"
    assert result["error"] == ""


@pytest.mark.asyncio
async def test_message_empty():
    # Call the tool with an empty message
    result = await tool_message(text="")
    
    # Check the result indicates an error
    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "error" in result
    assert "Missing required parameter: text" in result["error"]


@pytest.mark.asyncio
async def test_message_special_characters():
    # Test with message containing special characters
    special_msg = "Testing!\n\nWith newlines and *special* characters: 🚀 😀 🔥"
    result = await tool_message(text=special_msg)
    
    # Check result contains the same special characters
    assert result["success"] is True
    assert result["message"] == special_msg
    assert result["output"] == special_msg


def test_examples():
    """Test that EXAMPLES dictionary has expected structure"""
    assert isinstance(EXAMPLES, dict)
    assert "text" in EXAMPLES
    assert isinstance(EXAMPLES["text"], str)
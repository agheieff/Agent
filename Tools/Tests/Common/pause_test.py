import pytest
import asyncio
from unittest.mock import AsyncMock
from Tools.Common.pause import tool_pause, EXAMPLES

@pytest.mark.asyncio
async def test_pause_success():
    mock_output_manager = AsyncMock()
    mock_output_manager.get_user_input = AsyncMock(return_value="test input")
    
    result = await tool_pause(message="Please provide input:", output_manager=mock_output_manager)
    
    mock_output_manager.get_user_input.assert_called_once_with("Please provide input: ")
    assert result["exit_code"] == 0
    assert "user_input" in result
    assert result["user_input"] == "test input"
    assert result["prompt_message"] == "Please provide input:"

@pytest.mark.asyncio
async def test_pause_missing_message():
    result = await tool_pause(message="", output_manager=AsyncMock())
    assert result["exit_code"] != 0
    assert "Missing required parameter" in result["error"]

@pytest.mark.asyncio
async def test_pause_missing_output_manager():
    result = await tool_pause(message="Please provide input:", output_manager=None)
    assert result["exit_code"] != 0
    assert "No output manager provided" in result["error"]

@pytest.mark.asyncio
async def test_pause_exception_in_output_manager():
    mock_output_manager = AsyncMock()
    mock_output_manager.get_user_input = AsyncMock(side_effect=Exception("Test error"))
    
    result = await tool_pause(message="Please provide input:", output_manager=mock_output_manager)
    assert result["exit_code"] != 0
    assert "Error getting user input" in result["error"]

def test_examples():
    assert isinstance(EXAMPLES, dict)
    assert "message" in EXAMPLES
    assert isinstance(EXAMPLES["message"], str)

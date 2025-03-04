import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from Tools.Common.pause import tool_pause, EXAMPLES


@pytest.mark.asyncio
async def test_pause_success():

    mock_output_manager = AsyncMock()
    mock_output_manager.get_user_input = AsyncMock(return_value="test input")


    result = await tool_pause(
        message="Please provide input:",
        output_manager=mock_output_manager
    )


    mock_output_manager.get_user_input.assert_called_once_with("Please provide input: ")


    assert result["success"] is True
    assert result["exit_code"] == 0
    assert "user_input" in result
    assert result["user_input"] == "test input"
    assert result["prompt_message"] == "Please provide input:"


@pytest.mark.asyncio
async def test_pause_missing_message():

    result = await tool_pause(
        message="",
        output_manager=AsyncMock()
    )


    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "error" in result
    assert "Missing required parameter: message" in result["error"]


@pytest.mark.asyncio
async def test_pause_missing_output_manager():

    result = await tool_pause(
        message="Please provide input:",
        output_manager=None
    )


    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "error" in result
    assert "No output manager provided" in result["error"]


@pytest.mark.asyncio
async def test_pause_raises_exception():

    mock_output_manager = AsyncMock()
    mock_output_manager.get_user_input = AsyncMock(side_effect=Exception("Test error"))


    result = await tool_pause(
        message="Please provide input:",
        output_manager=mock_output_manager
    )


    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "error" in result
    assert "Error getting user input" in result["error"]


def test_examples():

    assert isinstance(EXAMPLES, dict)
    assert "message" in EXAMPLES
    assert isinstance(EXAMPLES["message"], str)

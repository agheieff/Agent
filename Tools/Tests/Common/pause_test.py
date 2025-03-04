import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from Tools.Common.pause import tool_pause, EXAMPLES


@pytest.mark.asyncio
async def test_pause_success():
    # Create a mock output manager
    mock_output_manager = AsyncMock()
    mock_output_manager.get_user_input = AsyncMock(return_value="test input")
    
    # Call the tool with a valid message
    result = await tool_pause(
        message="Please provide input:",
        output_manager=mock_output_manager
    )
    
    # Verify the output manager was called with the right prompt
    mock_output_manager.get_user_input.assert_called_once_with("Please provide input: ")
    
    # Check the result structure
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert "user_input" in result
    assert result["user_input"] == "test input"
    assert result["prompt_message"] == "Please provide input:"


@pytest.mark.asyncio
async def test_pause_missing_message():
    # Call the tool without a message
    result = await tool_pause(
        message="",
        output_manager=AsyncMock()
    )
    
    # Check the result indicates an error
    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "error" in result
    assert "Missing required parameter: message" in result["error"]


@pytest.mark.asyncio
async def test_pause_missing_output_manager():
    # Call the tool without an output manager
    result = await tool_pause(
        message="Please provide input:",
        output_manager=None
    )
    
    # Check the result indicates an error
    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "error" in result
    assert "No output manager provided" in result["error"]


@pytest.mark.asyncio
async def test_pause_raises_exception():
    # Create a mock output manager that raises an exception
    mock_output_manager = AsyncMock()
    mock_output_manager.get_user_input = AsyncMock(side_effect=Exception("Test error"))
    
    # Call the tool
    result = await tool_pause(
        message="Please provide input:",
        output_manager=mock_output_manager
    )
    
    # Check the result indicates an error
    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "error" in result
    assert "Error getting user input" in result["error"]


def test_examples():
    """Test that EXAMPLES dictionary has expected structure"""
    assert isinstance(EXAMPLES, dict)
    assert "message" in EXAMPLES
    assert isinstance(EXAMPLES["message"], str)
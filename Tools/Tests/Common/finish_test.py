import pytest
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from Tools.Common.finish import tool_finish, EXAMPLES


@pytest.mark.asyncio
async def test_finish():
    # Call the tool
    result = await tool_finish()
    
    # Check the result structure
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["output"] == "Conversation ended by agent."
    assert result["error"] == ""
    assert "conversation_ended" in result
    assert result["conversation_ended"] is True


@pytest.mark.asyncio
async def test_finish_with_extra_params():
    # Even with extra parameters, the tool should work the same way
    result = await tool_finish(extra_param="should be ignored")
    
    # Check the result structure (should be the same as without extra params)
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["output"] == "Conversation ended by agent."
    assert result["error"] == ""
    assert result["conversation_ended"] is True


def test_examples():
    """Test that EXAMPLES dictionary exists and is empty"""
    assert isinstance(EXAMPLES, dict)
    assert len(EXAMPLES) == 0  # No parameters needed for this tool
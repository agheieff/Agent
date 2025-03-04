import pytest
import asyncio
from Tools.Common.finish import tool_finish, EXAMPLES

@pytest.mark.asyncio
async def test_finish():
    result = await tool_finish()
    assert result["exit_code"] == 0
    assert result["output"] == "Conversation ended by agent."
    assert result["error"] == ""
    assert "conversation_ended" in result
    assert result["conversation_ended"] is True

@pytest.mark.asyncio
async def test_finish_with_extra_params():
    result = await tool_finish(extra_param="ignored")
    assert result["exit_code"] == 0
    assert result["output"] == "Conversation ended by agent."
    assert result["error"] == ""
    assert result["conversation_ended"] is True

def test_examples():
    assert isinstance(EXAMPLES, dict)
    # In finish, examples dict is empty.
    assert len(EXAMPLES) == 0

import pytest
import os
import sys


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from Tools.Common.finish import tool_finish, EXAMPLES


@pytest.mark.asyncio
async def test_finish():

    result = await tool_finish()


    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["output"] == "Conversation ended by agent."
    assert result["error"] == ""
    assert "conversation_ended" in result
    assert result["conversation_ended"] is True


@pytest.mark.asyncio
async def test_finish_with_extra_params():

    result = await tool_finish(extra_param="should be ignored")


    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["output"] == "Conversation ended by agent."
    assert result["error"] == ""
    assert result["conversation_ended"] is True


def test_examples():

    assert isinstance(EXAMPLES, dict)
    assert len(EXAMPLES) == 0

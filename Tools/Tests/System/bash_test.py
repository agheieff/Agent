import pytest
import asyncio
from Tools.System.bash import tool_bash

@pytest.mark.asyncio
class TestBashTool:

    async def test_simple_command(self):
        result = await tool_bash(command="echo Hello")
        assert result["success"] is True
        assert "Hello" in result["output"]

    async def test_timeout(self):
        # Command should exceed the timeout and be killed
        result = await tool_bash(command="sleep 2", timeout=1)
        assert result["success"] is False
        assert "timed out" in result["error"].lower()

    async def test_no_timeout(self):
        result = await tool_bash(command="true", timeout=0)
        assert result["success"] is True
        assert result["exit_code"] == 0

    async def test_error_command(self):
        result = await tool_bash(command="ls /no_such_dir_exists")
        assert result["success"] is False
        assert result["exit_code"] != 0

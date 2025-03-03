import os
import pytest
import asyncio
import tempfile

from Tools.System.bash import tool_bash

@pytest.mark.asyncio
class TestBashTool:

    async def test_help(self):
        result = await tool_bash(help=True)
        assert result["success"] is True
        assert "Execute arbitrary bash commands" in result["output"]

    async def test_simple_command(self):
        result = await tool_bash(command="echo 'Hello World'")
        assert result["success"] is True
        assert "Hello World" in result["output"]
        assert result["exit_code"] == 0

    async def test_multiline_command(self):
        command = """echo "Line 1"
echo "Line 2"
echo "Line 3"
"""
        result = await tool_bash(command=command)
        assert result["success"] is True
        out = result["output"]
        assert "Line 1" in out
        assert "Line 2" in out
        assert "Line 3" in out

    async def test_timeout(self):

        result = await tool_bash(command="sleep 3", timeout=1)
        assert result["success"] is False
        assert "timed out" in result["error"].lower()
        assert result["exit_code"] == 124

    async def test_no_timeout(self):

        result = await tool_bash(command="sleep 1", timeout=0)
        assert result["success"] is True

    async def test_error_command(self):

        result = await tool_bash(command="ls /no_such_file_exists")
        assert result["success"] is False
        assert "No such file or directory" in result["output"] or "no_such_file_exists" in result["output"]
        assert result["exit_code"] != 0

import unittest
import asyncio
from unittest.mock import AsyncMock, patch
from Core.agent_runner import AgentRunner
from Core.tool_parser import ToolCallParser

class TestStreamingBehavior(unittest.TestCase):
    def setUp(self):
        self.parser = ToolCallParser()

    async def simulate_stream(self, chunks):
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0.01)  # Simulate network delay

    @patch('Clients.API.anthropic.AnthropicClient.chat_completion_stream')
    async def test_tool_call_mid_stream(self, mock_stream):
        # Simulate a response that has a tool call after some text
        mock_stream.return_value = self.simulate_stream([
            "Here's some text before the ",
            "tool call: @tool read_file\npath: test.txt\n@end",
            " and this text should never be seen"
        ])

        agent = AgentRunner("anthropic", "claude-3-7-sonnet", use_system_prompt=False)
        await agent._run_chat_cycle("Test prompt")

        # Verify the tool was called and streaming stopped
        self.assertEqual(len(agent.messages), 3)  # User, Assistant (partial), User (tool result)
        self.assertIn("@tool read_file", agent.messages[1].content)
        self.assertNotIn("never be seen", agent.messages[1].content)

    def test_parser_incremental_tool(self):
        chunks = [
            "Some text @tool",
            " read_file\npath: test.txt\n",
            "@end more text"
        ]

        full_text = ""
        tool_detected = False
        for chunk in chunks:
            text, tool_call = self.parser.feed(chunk)
            full_text += text
            if tool_call:
                tool_detected = True
                break

        self.assertTrue(tool_detected)
        self.assertEqual(full_text, "Some text ")
        self.assertEqual(tool_call['tool'], 'read_file')

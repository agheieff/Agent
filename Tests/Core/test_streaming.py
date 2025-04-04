from typing import AsyncGenerator
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
            await asyncio.sleep(0.01)

    @patch('Clients.API.anthropic.AnthropicClient.chat_completion_stream')
    async def test_mid_stream_tool_interrupt(self, mock_stream):
        mock_stream.return_value = self.simulate_stream([
            "Here's some initial text...",
            "@tool read_file\npath: test.txt\n@end",
            "This text should never appear"
        ])

        agent = AgentRunner("anthropic", use_system_prompt=False)
        with patch.object(agent.executor, 'execute', return_value="File content") as mock_exec:
            result = await agent._run_chat_cycle("Test")

            # Verify tool was executed
            mock_exec.assert_called_once_with({
                'tool': 'read_file',
                'args': {'path': 'test.txt'}
            })

            # Verify message history
            self.assertEqual(len(agent.messages), 3)  # user, assistant, tool result
            self.assertIn("initial text", agent.messages[1].content)
            self.assertNotIn("never appear", agent.messages[1].content)

    def test_parser_incremental(self):
        chunks = [
            "Some text @tool",
            " edit_file\nfilename: test.txt\n",
            "content: new content\n@end more text"
        ]

        full_text = ""
        for chunk in chunks:
            text, tool = self.parser.feed(chunk)
            full_text += text
            if tool:
                self.assertEqual(tool['tool'], 'edit_file')
                self.assertEqual(tool['args']['filename'], 'test.txt')
                break

        self.assertEqual(full_text, "Some text ")

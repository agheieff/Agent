from typing import AsyncGenerator
import unittest
import asyncio
import warnings
import pytest
from unittest.mock import AsyncMock, patch
from Core.agent_runner import AgentRunner
from Core.tool_parser import ToolCallParser
from dotenv import load_dotenv

load_dotenv()

# Filter out coroutine warnings for this test
warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine .* was never awaited")

class TestStreamingBehavior(unittest.TestCase):
    def setUp(self):
        self.parser = ToolCallParser()

    async def simulate_stream(self, chunks):
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0.01)

    @patch('Clients.API.anthropic.AnthropicClient.chat_completion_stream')
    def test_mid_stream_tool_interrupt(self, mock_stream):
        async def _test():
            mock_stream.return_value = self.simulate_stream([
                "Here's some initial text...",
                "@tool read_file\npath: test.txt\n@end",
                "This text should never appear"
            ])

            agent = AgentRunner("anthropic", use_system_prompt=False)
            with patch.object(agent.executor, 'execute', return_value="File content"):
                result = await agent._run_chat_cycle("Test")
                # Verify tool was executed
                agent.executor.execute.assert_called_once()
                
                # Assert there are messages in the conversation
                self.assertTrue(len(agent.messages) >= 1)
                
                # Find the message with the initial text
                initial_text_found = False
                for msg in agent.messages:
                    if "initial text" in msg.content:
                        initial_text_found = True
                        break
                self.assertTrue(initial_text_found, "Initial text not found in any message")
                
                # Ensure no message has the "never appear" text
                for msg in agent.messages:
                    self.assertNotIn("never appear", msg.content)
        
        # Use a new event loop to run the test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_test())
        finally:
            loop.close()

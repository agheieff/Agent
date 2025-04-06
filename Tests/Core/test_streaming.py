from typing import AsyncGenerator
import unittest
import asyncio
import warnings
import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from Core.agent_runner import AgentRunner
from Core.tool_parser import ToolCallParser
from dotenv import load_dotenv

load_dotenv()

warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine .* was never awaited")

class TestStreamingBehavior(unittest.TestCase):
    def setUp(self):
        self.parser = ToolCallParser()
        if not os.getenv("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = "test-dummy-key-anthropic"

    async def simulate_stream(self, chunks):
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0.01)

    @patch('Core.agent_runner.AgentRunner._get_client_instance')
    def test_mid_stream_tool_interrupt(self, mock_get_client):

        mock_client = MagicMock()
        mock_client.config.default_model = 'claude-3-5-sonnet-test'
        mock_client.get_available_models.return_value = ['claude-3-5-sonnet-test']
        # Mock the stream method directly on the client instance
        mock_stream_method = AsyncMock()
        mock_client.chat_completion_stream = mock_stream_method
        mock_get_client.return_value = mock_client

        async def _test():
            # Configure the return value for the *first* call to the stream method
            mock_stream_method.return_value = self.simulate_stream([
                "Here's some initial text...",
                "@tool read_file\npath: test.txt\n@end",
                "This text should never appear"
            ])

            # Configure subsequent calls (recursive) to return an empty stream
            async def empty_gen():
                if False: yield
            mock_stream_method.side_effect = [
                self.simulate_stream([
                    "Here's some initial text...",
                    "@tool read_file\npath: test.txt\n@end",
                    "This text should never appear"
                ]),
                empty_gen() # For the recursive call
            ]


            agent = AgentRunner(provider="anthropic", use_system_prompt=False)

            # Mock executor
            mock_executor_execute = MagicMock(return_value="@result read_file\nexit_code: 0\noutput: File content\n@end")
            agent.executor.execute = mock_executor_execute

            # Mock stream closing
            agent.stream_manager.close_stream = AsyncMock()

            # Run the first cycle - this will process the stream and call the tool
            # It will then attempt a recursive call, which will get the empty stream via side_effect
            await agent._run_chat_cycle("Test User Prompt")

            # --- Assertions ---
            # 1. Verify executor was called correctly
            mock_executor_execute.assert_called_once_with("@tool read_file\npath: test.txt\n@end")

            # 2. Check message count (User, Assistant Text Before Tool, Tool Result)
            # The recursive call gets an empty stream, adds empty assistant message.
            self.assertTrue(len(agent.messages) >= 3, f"Expected at least 3 messages, got {len(agent.messages)}")

            # 3. Check message content and order
            self.assertEqual(agent.messages[0].role, 'user')
            self.assertEqual(agent.messages[0].content, 'Test User Prompt')

            self.assertEqual(agent.messages[1].role, 'assistant')
            self.assertEqual(agent.messages[1].content, "Here's some initial text...") # Text before tool

            self.assertEqual(agent.messages[2].role, 'assistant')
            self.assertEqual(agent.messages[2].content, "@result read_file\nexit_code: 0\noutput: File content\n@end") # Tool result

            # 4. Ensure trailing text was ignored
            for msg in agent.messages:
                self.assertNotIn("This text should never appear", msg.content)

            # 5. Check the stream method was called (at least once)
            mock_stream_method.assert_called()


        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_test())
        finally:
            loop.close()
            if os.environ.get("ANTHROPIC_API_KEY") == "test-dummy-key-anthropic":
                del os.environ["ANTHROPIC_API_KEY"]

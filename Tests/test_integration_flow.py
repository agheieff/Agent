import os
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from Core.agent_runner import AgentRunner
from Tools.Core.registry import ToolRegistry

class TestIntegrationFlow(unittest.TestCase):
    def setUp(self):
        # Ensure a dummy API key is present so that the Anthropic client initializes.
        os.environ["ANTHROPIC_API_KEY"] = "dummy-key"

        # Clear the ToolRegistry so we start with a fresh discovery.
        registry = ToolRegistry()
        registry._tools.clear()
        registry._discovered = False

        # Patch the Anthropic client's chat_completion method so no real API call is made.
        self.mock_chat_completion = AsyncMock()
        # Note: Patch the method on the correct target.
        patcher1 = patch("Clients.API.anthropic.AnthropicClient.chat_completion", new=self.mock_chat_completion)
        self.addCleanup(patcher1.stop)
        patcher1.start()

        # Patch the Executor.execute method used to execute tool calls.
        self.mock_execute = MagicMock()
        patcher2 = patch("Core.agent_runner.Executor.execute", new=self.mock_execute)
        self.addCleanup(patcher2.stop)
        patcher2.start()

    def test_tool_call_in_response(self):
        # Simulate an LLM response that contains a tool call.
        tool_call_response = (
            "@tool read_file\n"
            "path: ./my_test_file.txt\n"
            "@end"
        )
        self.mock_chat_completion.return_value = tool_call_response

        # Simulate the tool execution result.
        tool_result = (
            "@result read_file\n"
            "exit_code: 0\n"
            "output: File content: Hello from test!\n"
            "@end"
        )
        self.mock_execute.return_value = tool_result

        # Create an AgentRunner instance with use_system_prompt set to False.
        agent = AgentRunner("anthropic", "claude-3-7-sonnet", use_system_prompt=False)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            response = loop.run_until_complete(agent._run_chat_cycle("User wants to read a file."))
        finally:
            loop.close()

        # The conversation should have two new assistant messages:
        # one for the tool execution result and one for the original tool call response.
        messages = agent.messages

        # Verify that the second-to-last message contains the tool result.
        self.assertEqual(messages[-2].role, "assistant")
        self.assertIn("@result read_file", messages[-2].content)

        # Verify that the last assistant message is the original tool call response.
        self.assertEqual(messages[-1].role, "assistant")
        self.assertEqual(messages[-1].content, tool_call_response)

if __name__ == '__main__':
    unittest.main()

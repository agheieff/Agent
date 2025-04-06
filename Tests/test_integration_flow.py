from typing import AsyncGenerator
import os
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from Core.agent_runner import AgentRunner
from Tools.Core.registry import ToolRegistry
from Clients.base import Message, ProviderConfig, BaseClient # Import necessary base classes

class TestIntegrationFlow(unittest.TestCase):
    def setUp(self):
        # Ensure dummy key is set if not present for AnthropicClient init
        if not os.getenv("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = "dummy-key-anthropic"

        # Mock the client loading process within AgentRunner
        self.mock_get_client_patcher = patch('Core.agent_runner.AgentRunner._get_client_instance')
        self.mock_get_client = self.mock_get_client_patcher.start()
        self.addCleanup(self.mock_get_client_patcher.stop)

        # Setup mock client that _get_client_instance will return
        self.mock_client = MagicMock(spec=BaseClient) # Use spec for better mocking
        self.mock_client.config = MagicMock(spec=ProviderConfig)
        self.mock_client.config.default_model = 'claude-3-5-sonnet-mock'
        self.mock_client.get_available_models.return_value = ['claude-3-5-sonnet-mock', 'claude-3-7-sonnet']
        # Mock the actual API call method if needed, though this test focuses on message flow
        self.mock_client.chat_completion = AsyncMock(return_value="Mocked API Response")
        self.mock_get_client.return_value = self.mock_client

        # Mock the Executor's execute method directly as it's used by AgentRunner
        self.mock_execute_patcher = patch("Core.executor.Executor.execute", return_value = (
            "@result read_file\n"
            "exit_code: 0\n"
            "output: File content: Hello from test!\n"
            "@end"
        ))
        self.mock_execute = self.mock_execute_patcher.start()
        self.addCleanup(self.mock_execute_patcher.stop)


        # Reset tool registry if needed (though mocking execute bypasses it here)
        registry = ToolRegistry()
        registry._tools.clear()
        registry._discovered = False


    def test_tool_call_in_response(self):
        # Instantiate AgentRunner correctly - it will use the mocked _get_client_instance
        agent = AgentRunner(provider="anthropic", model="claude-3-7-sonnet", use_system_prompt=False)

        # Add messages manually to test the sequence storage
        agent.add_message('user', "User wants to read a file.")

        tool_call_response = (
            "@tool read_file\n"
            "path: ./my_test_file.txt\n"
            "@end"
        )
        agent.add_message('assistant', tool_call_response)

        tool_result = (
            "@result read_file\n"
            "exit_code: 0\n"
            "output: File content: Hello from test!\n"
            "@end"
        )
        agent.add_message('assistant', tool_result)

        # Verify messages list
        messages = agent.messages

        self.assertEqual(len(messages), 3)

        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "User wants to read a file.")

        self.assertEqual(messages[1].role, "assistant")
        self.assertEqual(messages[1].content, tool_call_response)

        self.assertEqual(messages[2].role, "assistant")
        self.assertEqual(messages[2].content, tool_result)

        # Clean up dummy key if set
        if os.environ.get("ANTHROPIC_API_KEY") == "dummy-key-anthropic":
            del os.environ["ANTHROPIC_API_KEY"]

if __name__ == '__main__':
    unittest.main()

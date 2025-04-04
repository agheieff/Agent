from typing import AsyncGenerator
import os
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from Core.agent_runner import AgentRunner
from Tools.Core.registry import ToolRegistry
from Clients.base import Message

class TestIntegrationFlow(unittest.TestCase):
    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "dummy-key"

        registry = ToolRegistry()
        registry._tools.clear()
        registry._discovered = False

        self.mock_chat_completion = AsyncMock()
        patcher1 = patch("Clients.API.anthropic.AnthropicClient.chat_completion", new=self.mock_chat_completion)
        self.addCleanup(patcher1.stop)
        patcher1.start()

        self.mock_execute = MagicMock()
        patcher2 = patch("Core.agent_runner.Executor.execute", new=self.mock_execute)
        self.addCleanup(patcher2.stop)
        patcher2.start()

    def test_tool_call_in_response(self):
        # Create an AgentRunner instance with use_system_prompt set to False.
        agent = AgentRunner("anthropic", "claude-3-7-sonnet", use_system_prompt=False)
        
        # Add a user message
        agent.add_message('user', "User wants to read a file.")
        
        # Add the tool call message
        tool_call_response = (
            "@tool read_file\n"
            "path: ./my_test_file.txt\n"
            "@end"
        )
        agent.add_message('assistant', tool_call_response)

        # Add the tool result message
        tool_result = (
            "@result read_file\n"
            "exit_code: 0\n"
            "output: File content: Hello from test!\n"
            "@end"
        )
        agent.add_message('assistant', tool_result)

        # Verify that messages are added correctly
        messages = agent.messages
        
        # Verify the first message is the user message
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "User wants to read a file.")
        
        # Verify that the second message contains the tool call
        self.assertEqual(messages[1].role, "assistant")
        self.assertEqual(messages[1].content, tool_call_response)
        
        # Verify that the third message contains the tool result
        self.assertEqual(messages[2].role, "assistant")
        self.assertEqual(messages[2].content, tool_result)

if __name__ == '__main__':
    unittest.main()
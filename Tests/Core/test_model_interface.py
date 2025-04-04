import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from Clients.API.anthropic import AnthropicClient, ANTHROPIC_CONFIG
from Clients.base import Message

class TestAnthropicInterface(unittest.TestCase):
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('anthropic.AsyncAnthropic')
    def test_generate_response(self, mock_anthropic):
        mock_client_instance = AsyncMock()
        mock_anthropic.return_value = mock_client_instance

        mock_api_message = MagicMock()
        mock_api_message.text = "Mock response"
        mock_api_response = MagicMock()
        mock_api_response.content = [mock_api_message]
        mock_client_instance.messages.create.return_value = mock_api_response

        async def run_test():
            client = AnthropicClient()

            self.assertEqual(client.timeout, 30.0)
            self.assertEqual(client.max_retries, 3)

            messages = [Message(role="user", content="Test")]

            processed_response = await client.chat_completion(
                messages=messages,
                model=ANTHROPIC_CONFIG.default_model
            )

            self.assertEqual(processed_response, "Mock response")

            mock_client_instance.messages.create.assert_called_once()

            call_args, call_kwargs = mock_client_instance.messages.create.call_args
            expected_model_name = ANTHROPIC_CONFIG.models[ANTHROPIC_CONFIG.default_model].name
            self.assertEqual(call_kwargs['model'], expected_model_name)
            self.assertEqual(call_kwargs['messages'], [{'role': 'user', 'content': 'Test'}])
            self.assertNotIn('system', call_kwargs)

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()

import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from Clients.API.anthropic import AnthropicClient, ANTHROPIC_CONFIG
from Clients.base import Message

class TestAnthropicInterface(unittest.TestCase):
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('anthropic.AsyncAnthropic')
    def test_generate_response(self, mock_anthropic):
        # Setup mock client and response
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        
        mock_message = MagicMock()
        mock_message.text = "Mock response"
        
        mock_response = MagicMock()
        mock_response.content = [mock_message]
        mock_client.messages.create.return_value = mock_response
        
        # Create an async function to run the test
        async def run_test():
            client = AnthropicClient()
            # Verify attributes are set
            self.assertEqual(client.timeout, 30.0)
            self.assertEqual(client.max_retries, 3)
            
            messages = [Message(role="user", content="Test")]
            
            response = await client._call_api(
                messages=messages, 
                model=ANTHROPIC_CONFIG.default_model
            )
            processed = client._process_response(response)
            
            self.assertEqual(processed, "Mock response")
            mock_client.messages.create.assert_called_once()
        
        # Run the async test
        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()

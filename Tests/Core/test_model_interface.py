import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from Tests.test_utils import ProviderTestCase
from Clients.API.anthropic import AnthropicClient, ANTHROPIC_CONFIG
from Clients.base import BaseClient

class TestAnthropicInterface(ProviderTestCase):
    provider = "anthropic"
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch.object(BaseClient, '_initialize_client')
    def test_generate_response(self, mock_init_client):
        # Setup mock client and response
        mock_client = MagicMock()
        mock_init_client.return_value = mock_client
        
        mock_message = MagicMock()
        mock_message.text = "Mock response"
        
        mock_response = MagicMock()
        mock_response.content = [mock_message]
        mock_client.messages.create.return_value = mock_response
        
        # Test
        client = AnthropicClient()
        response = client.chat_completion(
            messages=[{"role": "user", "content": "Test"}],
            model=ANTHROPIC_CONFIG.default_model
        )
        
        self.assertEqual(response, "Mock response")
        mock_client.messages.create.assert_called_once()

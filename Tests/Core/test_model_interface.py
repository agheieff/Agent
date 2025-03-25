import unittest
from unittest.mock import MagicMock, patch
from Core.model_interface import ModelInterface
from Tests.test_utils import ProviderTestCase

class TestOpenAIInterface(ProviderTestCase):
    provider = "openai"
    
    @patch("openai.OpenAI")
    def test_generate_response(self, mock_openai):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Test response"
        mock_client.chat.completions.create.return_value = mock_response
        
        interface = ModelInterface("openai")
        response = interface.generate([{"role": "user", "content": "Hello"}])
        
        self.assertEqual(response, "Test response")
        mock_client.chat.completions.create.assert_called_once()

class TestAnthropicInterface(ProviderTestCase):
    provider = "anthropic"
    
    @patch("anthropic.Anthropic")
    def test_generate_response(self, mock_anthropic):
        # Similar mocking for Anthropic
        pass

import pytest
from unittest.mock import patch, MagicMock, call
import json
import logging
from Clients.deepseek import DeepSeekClient

class TestDeepSeekClient:
    @pytest.fixture
    def mock_openai(self):
        with patch('openai.OpenAI') as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            yield mock_client
            
    @pytest.fixture
    def test_client(self, mock_openai):
        return DeepSeekClient(api_key="test-key")
    
    def test_initialization(self, mock_openai):
        client = DeepSeekClient(api_key="test-key")
        mock_openai.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.deepseek.com"
        )
        assert hasattr(client, 'client')
        
    def test_initialization_error(self, mock_openai):
        mock_openai.side_effect = Exception("API Error")
        with pytest.raises(ValueError, match="Failed to initialize DeepSeek client"):
            DeepSeekClient(api_key="test-key")
            
    def test_register_models(self, test_client):
        assert "deepseek-reasoner" in test_client.models
        model_info = test_client.models["deepseek-reasoner"]
        assert model_info.name == "DeepSeek Reasoner"
        assert model_info.api_name == "deepseek-reasoner"
        assert model_info.prefers_separate_system_prompt is False
        assert model_info.input_price == 0.14
        assert model_info.output_price == 2.19
        
    @pytest.mark.asyncio
    async def test_make_api_call_standard(self, test_client):
        mock_chat_completions = MagicMock()
        test_client.client.chat.completions.create = mock_chat_completions
        
        messages = [{"role": "user", "content": "Hello"}]
        await test_client._make_api_call(
            messages=messages,
            model_name="deepseek-reasoner",
            temperature=0.7,
            max_tokens=1000,
            tool_usage=False
        )
        
        # Check standard API call
        mock_chat_completions.assert_called_once_with(
            model="deepseek-reasoner",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        
    @pytest.mark.asyncio
    async def test_make_api_call_with_tools(self, test_client):
        mock_chat_completions = MagicMock()
        test_client.client.chat.completions.create = mock_chat_completions
        
        messages = [{"role": "user", "content": "Hello"}]
        functions = test_client._get_function_schema()
        
        await test_client._make_api_call(
            messages=messages,
            model_name="deepseek-reasoner",
            temperature=0.7,
            max_tokens=1000,
            tool_usage=True
        )
        
        # Check API call with functions
        mock_chat_completions.assert_called_once_with(
            model="deepseek-reasoner",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
            functions=functions,
            function_call="auto"
        )
        
    def test_extract_response_content_standard(self, test_client):
        # Create a mock response with normal content
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello world"
        
        result = test_client.extract_response_content(mock_response)
        assert result == "Hello world"
        
    def test_extract_response_content_with_function_call(self, test_client):
        # Create a mock response with function call
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Action requested"
        mock_response.choices[0].message.function_call = MagicMock()
        mock_response.choices[0].message.function_call.name = "tool"
        mock_response.choices[0].message.function_call.arguments = json.dumps({
            "action": "test_tool",
            "action_input": {"param1": "value1"}
        })
        
        result = test_client.extract_response_content(mock_response)
        parsed_result = json.loads(result)
        
        assert parsed_result["action"] == "test_tool"
        assert parsed_result["action_input"]["param1"] == "value1"
        assert parsed_result["response"] == "Action requested"

if __name__ == "__main__":
    pytest.main(["-v"])
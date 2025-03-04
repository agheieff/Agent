import pytest
from unittest.mock import patch, MagicMock, call
import json
import logging
from Clients.deepseek import DeepSeekClient

class TestDeepSeekClient:
    @pytest.fixture
    def mock_openai(self):

        with patch('Clients.deepseek.OpenAI') as mock_client:
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


        mock_chat_completions.assert_called_once_with(
            model="deepseek-reasoner",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
            functions=functions,
            function_call="auto"
        )

    def test_extract_response_content_standard(self, test_client):

        mock_response = MagicMock()


        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Hello world"

        mock_message.function_call = None

        mock_choice.message = mock_message

        mock_response.choices = [mock_choice]


        with patch('Clients.base.BaseLLMClient.extract_response_content', return_value="Hello world"):
            result = test_client.extract_response_content(mock_response)
            assert result == "Hello world"

    def test_extract_response_content_with_function_call(self, test_client):

        mock_response = MagicMock()


        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Action requested"


        mock_function_call = MagicMock()
        mock_function_call.name = "test_tool"
        mock_function_call.arguments = json.dumps({
            "action_input": {"param1": "value1"}
        })


        mock_message.function_call = mock_function_call

        mock_choice.message = mock_message

        mock_response.choices = [mock_choice]


        with patch('Clients.base.BaseLLMClient.extract_response_content', return_value="Action requested"):
            result = test_client.extract_response_content(mock_response)
            parsed_result = json.loads(result)


            assert parsed_result["action"] == "test_tool"
            assert "action_input" in parsed_result
            assert parsed_result["response"] == "Action requested"

if __name__ == "__main__":
    pytest.main(["-v"])

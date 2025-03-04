import pytest
from unittest.mock import patch, MagicMock
import logging
from Clients.anthropic import AnthropicClient

class TestAnthropicClient:
    @pytest.fixture
    def mock_anthropic(self):

        with patch('anthropic.Client') as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            yield mock_client

    @pytest.fixture
    def test_client(self, mock_anthropic):
        return AnthropicClient(api_key="anthropic-test-key")

    def test_initialization(self, mock_anthropic):
        client = AnthropicClient(api_key="test-key")
        mock_anthropic.assert_called_once_with(api_key="test-key")
        assert hasattr(client, 'client')
        assert client.use_token_efficient_tools is True

    def test_initialization_with_token_efficient_disabled(self, mock_anthropic):
        client = AnthropicClient(api_key="test-key", use_token_efficient_tools=False)
        assert client.use_token_efficient_tools is False

    def test_initialization_error_empty_key(self):
        with pytest.raises(ValueError):
            AnthropicClient(api_key="")

    def test_adjust_prompts(self, test_client):
        system_prompt = "System instructions"
        user_prompt = "User query"

        adjusted_system, adjusted_user = test_client.adjust_prompts(system_prompt, user_prompt)

        assert adjusted_system == system_prompt
        assert adjusted_user == user_prompt

    @pytest.mark.asyncio
    async def test_make_api_call_standard(self, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_completions_create = MagicMock()
        mock_instance.completions.create = mock_completions_create

        client = AnthropicClient(api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]
        await client._make_api_call(
            messages=messages,
            model_name="claude-3-7-sonnet-20250219",
            temperature=0.7,
            max_tokens=1000,
            tool_usage=False
        )

        mock_completions_create.assert_called_once()

        call_args = mock_completions_create.call_args[1]
        assert call_args["model"] == "claude-3-7-sonnet-20250219"
        assert call_args["max_tokens_to_sample"] == 1000
        assert call_args["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_make_api_call_with_tools(self, mock_anthropic):

        mock_instance = mock_anthropic.return_value
        mock_completions_create = MagicMock()
        mock_instance.completions.create = mock_completions_create

        client = AnthropicClient(api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        await client._make_api_call(
            messages=messages,
            model_name="claude-3-7-sonnet-20250219",
            temperature=0.7,
            max_tokens=1000,
            tool_usage=True
        )

        mock_completions_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_response(self, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_completions_create = MagicMock()
        mock_instance.completions.create = mock_completions_create

        mock_response = MagicMock()
        mock_response.completion = "This is a dummy response for testing"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_completions_create.return_value = mock_response

        client = AnthropicClient(api_key="test-key")
        conversation_history = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Tell me about AI"}
        ]

        response = await client.generate_response(conversation_history)

        assert "dummy response for testing" in response

    @pytest.mark.asyncio
    async def test_check_for_user_input_request(self, mock_anthropic):
        client = AnthropicClient(api_key="test-key")
        needs_input, message = await client.check_for_user_input_request("Any response text")

        assert needs_input is False
        assert message is None

    @pytest.mark.asyncio
    async def test_get_response_error_handling(self, mock_anthropic):
        client = AnthropicClient(api_key="test-key")

        with patch.object(client, '_make_api_call', side_effect=Exception("Forced error")):
            response = await client.get_response(
                prompt="Test prompt",
                system="Test system"
            )
            assert response is None

    @pytest.mark.asyncio
    async def test_generate_response_error_handling(self, mock_anthropic):
        client = AnthropicClient(api_key="test-key")

        with patch.object(client, 'get_response', side_effect=Exception("Forced error")):
            response = await client.generate_response([])
            assert "I encountered an error" in response

if __name__ == "__main__":
    pytest.main(["-v"])

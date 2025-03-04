import pytest
from unittest.mock import patch, MagicMock, call
import logging
from Clients.anthropic import AnthropicClient

class TestAnthropicClient:
    @pytest.fixture
    def mock_anthropic(self):
        with patch('anthropic.Anthropic') as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            yield mock_client
            
    @pytest.fixture
    def test_client(self):
        # Use the test key to trigger dummy mode
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
        mock_messages_create = MagicMock()
        mock_instance.messages.create = mock_messages_create
        
        client = AnthropicClient(api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]
        await client._make_api_call(
            messages=messages,
            model_name="claude-3-7-sonnet-20250219",
            temperature=0.7,
            max_tokens=1000,
            tool_usage=False
        )
        
        # Check standard API call
        mock_messages_create.assert_called_once_with(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            temperature=0.7,
            messages=messages
        )
        
    @pytest.mark.asyncio
    async def test_make_api_call_with_tools(self, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_messages_create = MagicMock()
        mock_instance.messages.create = mock_messages_create
        
        client = AnthropicClient(api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]
        tools = client._get_tool_schema()
        
        await client._make_api_call(
            messages=messages,
            model_name="claude-3-7-sonnet-20250219",
            temperature=0.7,
            max_tokens=1000,
            tool_usage=True
        )
        
        # Check API call with tools
        mock_messages_create.assert_called_once_with(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            temperature=0.7,
            messages=messages,
            tools=tools
        )
        
    @pytest.mark.asyncio
    async def test_make_api_call_with_token_efficient_tools(self, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_beta_instance = MagicMock()
        mock_instance.beta = mock_beta_instance
        mock_beta_messages = MagicMock()
        mock_beta_instance.messages = mock_beta_messages
        mock_beta_messages_create = MagicMock()
        mock_beta_messages.create = mock_beta_messages_create
        
        client = AnthropicClient(api_key="test-key", use_token_efficient_tools=True)
        messages = [{"role": "user", "content": "Hello"}]
        tools = client._get_tool_schema()
        
        await client._make_api_call(
            messages=messages,
            model_name="claude-3-7-sonnet-20250219",
            temperature=0.7,
            max_tokens=1000,
            tool_usage=True
        )
        
        # Check beta API call with token-efficient tools
        mock_beta_messages_create.assert_called_once_with(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            temperature=0.7,
            messages=messages,
            tools=tools,
            betas=["token-efficient-tools-2025-02-19"]
        )
        
    @pytest.mark.asyncio
    async def test_generate_response(self, test_client):
        conversation_history = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Tell me about AI"}
        ]
        
        response = await test_client.generate_response(conversation_history)
        
        assert "This is a dummy response for testing" in response
        
    @pytest.mark.asyncio
    async def test_check_for_user_input_request(self, test_client):
        needs_input, message = await test_client.check_for_user_input_request("Any response text")
        
        assert needs_input is False
        assert message is None
        
    @pytest.mark.asyncio
    async def test_get_response_error_handling(self):
        with patch('anthropic.Anthropic', side_effect=Exception("API Error")):
            # Still use test key to avoid actual API calls
            client = AnthropicClient(api_key="anthropic-test-key")
            
            # Force an error in the get_response method
            with patch.object(client, 'client', side_effect=Exception("Forced error")):
                response = await client.get_response(
                    prompt="Test prompt",
                    system="Test system"
                )
                
                assert response is None
                
    @pytest.mark.asyncio
    async def test_generate_response_error_handling(self):
        with patch('anthropic.Anthropic', side_effect=Exception("API Error")):
            # Still use test key to avoid actual API calls
            client = AnthropicClient(api_key="anthropic-test-key")
            
            # Force an error in the get_response method
            with patch.object(client, 'get_response', side_effect=Exception("Forced error")):
                response = await client.generate_response([])
                
                assert "I encountered an error" in response


if __name__ == "__main__":
    pytest.main(["-v"])
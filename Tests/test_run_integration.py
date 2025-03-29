import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, call
from pathlib import Path
from typing import List, Dict, Optional, Any

try:
    from run import run_agent_session, SessionConfig
    from Clients import Message, BaseClient, ProviderConfig, ModelConfig, PricingTier, get_client
    from Core import AgentRunner
    from Core.agent_runner import AgentRunResult, DEFAULT_MCP_TIMEOUT
    from MCP.models import MCPSuccessResponse, MCPErrorResponse
    from MCP.errors import ErrorCode
except ImportError as e:
    pytest.fail(f"Failed to import components for integration tests: {e}", pytrace=False)

TEST_PROVIDER = "mock_provider"
TEST_MODEL = "mock_model"
TEST_AGENT_ID = "test-agent-integration"
MCP_TEST_URL = "http://mock-mcp:8000/mcp"

@pytest.fixture
def mock_llm_client(mocker):
    class TestClient(BaseClient):
        def _initialize_provider_client(self): return MagicMock()
        def _format_messages(self, messages): return messages
        async def _execute_api_call(self, formatted_messages, api_model_name, stream, **kwargs): return MagicMock()
        def _process_response(self, response): return "Response text"
        def _process_stream_chunk(self, chunk): return "Chunk text"
        def _get_sdk_exception_types(self): return ()
        def _extract_error_details(self, error): return None, str(error)
        async def close(self): pass

    fake_config = ProviderConfig(
        name=TEST_PROVIDER,
        api_base="https://api.test",
        api_key_env="TEST_API_KEY",
        models={
            TEST_MODEL: ModelConfig(name=TEST_MODEL, context_length=10000, pricing=PricingTier(input=0.0, output=0.0))
        },
        default_model=TEST_MODEL
    )
    mocker.patch.dict(os.environ, {"TEST_API_KEY": "fake-key"})
    client_instance = TestClient(fake_config)

    client_instance.chat_completion = AsyncMock(return_value="Response text")
    client_instance.stream_chat_completion = AsyncMock()
    client_instance.get_available_models = MagicMock(return_value=[TEST_MODEL])
    client_instance.get_model_config = MagicMock(return_value=fake_config.models[TEST_MODEL])

    client_instance.close = AsyncMock()

    mocker.patch('run.get_client', return_value=client_instance)
    mocker.patch('run.discover_and_validate_providers', return_value=[TEST_PROVIDER])

    return client_instance

@pytest.fixture
def mock_mcp_execution(mocker):
    return mocker.patch('Core.agent_runner.AgentRunner.execute_mcp_operation', new_callable=AsyncMock)


@pytest.fixture(autouse=True)
def mock_env_vars(mocker):
    mocker.patch.dict(os.environ, {
        "MCP_SERVER_URL": MCP_TEST_URL,
        "TEST_API_KEY": "fake-key"
        })

@pytest.mark.asyncio
async def test_run_simple_finish_goal(mock_llm_client, mock_mcp_execution, capsys):
    test_goal = "Achieve simple goal"
    max_steps = 5

    finish_call_json = """
    ```json
    {
        "mcp_operation": {
            "operation_name": "finish_goal",
            "arguments": { "summary": "Goal achieved immediately." }
        }
    }
    ```
    """
    mock_llm_client.chat_completion.return_value = finish_call_json

    session_config = SessionConfig(
        provider=TEST_PROVIDER,
        model=TEST_MODEL,
        goal=test_goal,
        agent_id=TEST_AGENT_ID,
        max_steps=max_steps,
        mcp_url=MCP_TEST_URL,
        mcp_timeout=DEFAULT_MCP_TIMEOUT
    )

    await run_agent_session(session_config)

    captured = capsys.readouterr()
    mock_llm_client.chat_completion.assert_called_once()
    called_messages = mock_llm_client.chat_completion.call_args.kwargs['messages']
    assert any(test_goal in msg.content for msg in called_messages if msg.role == 'user')
    mock_mcp_execution.assert_not_called()
    assert "Agent thinking..." in captured.out
    assert "Final Summary from Agent: Goal achieved immediately." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_mcp_call_then_finish(mock_llm_client, mock_mcp_execution, capsys):
    test_goal = "Read a file then finish"
    target_file = "/path/to/read.txt"
    max_steps = 5

    read_call_json = f"""```json\n{{\n"mcp_operation": {{\n"operation_name": "read_file",\n"arguments": {{"path": "{target_file}"}}\n}}\n}}\n```"""
    finish_call_json = """```json\n{\n"mcp_operation": {\n"operation_name": "finish_goal",\n"arguments": {"summary": "Read file successfully."}\n}\n}\n```"""
    mock_llm_client.chat_completion.side_effect = [read_call_json, finish_call_json]

    mock_mcp_execution.return_value = MCPSuccessResponse(id="mcp-read-1", result={"content": "File content here."})

    session_config = SessionConfig(
        provider=TEST_PROVIDER, model=TEST_MODEL, goal=test_goal,
        agent_id=TEST_AGENT_ID, max_steps=max_steps, mcp_url=MCP_TEST_URL,
        mcp_timeout=DEFAULT_MCP_TIMEOUT
    )

    await run_agent_session(session_config)

    captured = capsys.readouterr()
    assert mock_llm_client.chat_completion.call_count == 2
    mock_mcp_execution.assert_called_once_with(operation_name="read_file", arguments={"path": target_file})

    second_call_args = mock_llm_client.chat_completion.call_args_list[1]
    messages_for_second_call = second_call_args.kwargs['messages']
    success_pattern_found = any("MCP Operation Successful" in msg.content and "File content here" in msg.content for msg in messages_for_second_call if msg.role == 'system')
    assert success_pattern_found, "Expected MCP result message not found in history"

    assert "Final Summary from Agent: Read file successfully." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_ask_user_then_finish(mock_llm_client, mock_mcp_execution, capsys, mocker):
    test_goal = "Confirm action with user"
    max_steps = 5
    user_confirmation = "Yes, proceed."

    ask_question_text = "Should I proceed with the important action?"
    finish_call_json = """```json\n{\n"mcp_operation": {\n"operation_name": "finish_goal",\n"arguments": {"summary": "User confirmed action."}\n}\n}\n```"""
    mock_llm_client.chat_completion.side_effect = [ask_question_text, finish_call_json]

    mock_prompt_input = mocker.patch('run.prompt_for_multiline_input', new_callable=AsyncMock)
    mock_prompt_input.return_value = user_confirmation

    session_config = SessionConfig(
        provider=TEST_PROVIDER, model=TEST_MODEL, goal=test_goal,
        agent_id=TEST_AGENT_ID, max_steps=max_steps, mcp_url=MCP_TEST_URL,
        mcp_timeout=DEFAULT_MCP_TIMEOUT
    )

    await run_agent_session(session_config)

    captured = capsys.readouterr()
    assert mock_llm_client.chat_completion.call_count == 2
    mock_mcp_execution.assert_not_called()
    mock_prompt_input.assert_not_called()

    second_call_args = mock_llm_client.chat_completion.call_args_list[1]
    messages_for_second_call = second_call_args.kwargs['messages']
    assert any(ask_question_text in m.content for m in messages_for_second_call if m.role == 'assistant')

    assert "Final Summary from Agent: User confirmed action." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_reaches_max_steps(mock_llm_client, mock_mcp_execution, capsys):
    test_goal = "Loop indefinitely (test max_steps)"
    max_steps = 3

    mock_llm_client.chat_completion.return_value = "Thinking about the next step..."

    session_config = SessionConfig(
        provider=TEST_PROVIDER, model=TEST_MODEL, goal=test_goal,
        agent_id=TEST_AGENT_ID, max_steps=max_steps, mcp_url=MCP_TEST_URL,
        mcp_timeout=DEFAULT_MCP_TIMEOUT
    )

    await run_agent_session(session_config)

    captured = capsys.readouterr()
    assert mock_llm_client.chat_completion.call_count == max_steps
    mock_mcp_execution.assert_not_called()

    assert "Outcome: max_steps" in captured.out
    assert f"Steps Taken: {max_steps}" in captured.out
    assert "Reason: Reached maximum steps." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()

import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, call
from pathlib import Path
from typing import List, Dict, Optional, Any

# --- Add project root to path if needed (usually handled by root conftest.py) ---
# ... (path setup assumed done by conftest) ...

# --- Updated Imports ---
try:
    # Import the correct function and the config dataclass
    from run import run_agent_session, SessionConfig
    from Clients import Message, BaseClient, ProviderConfig, ModelConfig, PricingTier, get_client
    from Core import AgentRunner
    from Core.agent_runner import DEFAULT_MCP_TIMEOUT # Import default timeout
    from MCP.models import MCPSuccessResponse, MCPErrorResponse
    from MCP.errors import ErrorCode
except ImportError as e:
    pytest.fail(f"Failed to import components for integration tests: {e}", pytrace=False)
# --- End Imports ---


# --- Constants ---
TEST_PROVIDER = "mock_provider"
TEST_MODEL = "mock_model"
TEST_AGENT_ID = "test-agent-integration"
MCP_TEST_URL = "http://mock-mcp:8000/mcp"

# --- Fixtures ---

@pytest.fixture
def mock_llm_client(mocker):
    """Mocks the LLM client used by AgentRunner and handles get_client."""
    # Create a client class that inherits from BaseClient to ensure isinstance checks pass
    class TestClient(BaseClient):
        def _initialize_provider_client(self): return MagicMock()
        def _format_messages(self, messages): return messages
        async def _execute_api_call(self, formatted_messages, api_model_name, stream, **kwargs): return MagicMock()
        def _process_response(self, response): return "Response text" # Default behavior
        def _process_stream_chunk(self, chunk): return "Chunk text"
        def _get_sdk_exception_types(self): return ()
        def _extract_error_details(self, error): return None, str(error)
        # Keep the real definition here, but we'll overwrite it below
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

    # Configure main methods used by AgentRunner
    client_instance.chat_completion = AsyncMock(return_value="Response text") # Default return
    client_instance.stream_chat_completion = AsyncMock()
    client_instance.get_available_models = MagicMock(return_value=[TEST_MODEL])
    client_instance.get_model_config = MagicMock(return_value=fake_config.models[TEST_MODEL])

    client_instance.close = AsyncMock()

    # Patch get_client to return our fully mocked instance when called via to_thread
    mocker.patch('run.get_client', return_value=client_instance)
    mocker.patch('run.discover_and_validate_providers', return_value=[TEST_PROVIDER])

    return client_instance


@pytest.fixture
def mock_mcp_execution(mocker):
    """Mocks the AgentRunner's execute_mcp_operation method."""
    return mocker.patch('Core.agent_runner.AgentRunner.execute_mcp_operation', new_callable=AsyncMock)


@pytest.fixture(autouse=True)
def mock_env_vars(mocker):
    """Mocks environment variables needed."""
    # Ensure MCP_SERVER_URL is set for SessionConfig creation
    mocker.patch.dict(os.environ, {
        "MCP_SERVER_URL": MCP_TEST_URL,
        "TEST_API_KEY": "fake-key" # Ensure API key is present for client init mock if needed
        })

# --- Test Scenarios ---

@pytest.mark.asyncio
async def test_run_simple_finish_goal(mock_llm_client, mock_mcp_execution, capsys):
    """Test a scenario where the agent finishes the goal in one step."""
    test_goal = "Achieve simple goal"
    max_steps = 5

    # Configure mock LLM response
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

    # --- Create SessionConfig directly ---
    session_config = SessionConfig(
        provider=TEST_PROVIDER,
        model=TEST_MODEL,
        goal=test_goal,
        agent_id=TEST_AGENT_ID,
        max_steps=max_steps,
        mcp_url=MCP_TEST_URL,
        mcp_timeout=DEFAULT_MCP_TIMEOUT # Use imported default
    )

    # --- Call the actual execution function ---
    await run_agent_session(session_config)

    # Assertions
    captured = capsys.readouterr()
    mock_llm_client.chat_completion.assert_called_once()
    called_messages = mock_llm_client.chat_completion.call_args.kwargs['messages']
    assert any(test_goal in msg.content for msg in called_messages if msg.role == 'user')
    mock_mcp_execution.assert_not_called()
    assert "Agent thinking..." in captured.out
    # Note: The specific "Agent initiated 'finish_goal'" log comes from AgentRunner
    # The final summary print comes from run_agent_session
    assert "Final Summary from Agent: Goal achieved immediately." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_mcp_call_then_finish(mock_llm_client, mock_mcp_execution, capsys):
    """Test agent makes one MCP call, then finishes."""
    test_goal = "Read a file then finish"
    target_file = "/path/to/read.txt"
    max_steps = 5

    # Mock LLM Responses (Sequence)
    read_call_json = f"""```json\n{{\n"mcp_operation": {{\n"operation_name": "read_file",\n"arguments": {{"path": "{target_file}"}}\n}}\n}}\n```"""
    finish_call_json = """```json\n{{\n"mcp_operation": {{\n"operation_name": "finish_goal",\n"arguments": {"summary": "Read file successfully."}\n}}\n}}\n```"""
    mock_llm_client.chat_completion.side_effect = [read_call_json, finish_call_json]

    # Mock MCP Response
    mock_mcp_execution.return_value = MCPSuccessResponse(id="mcp-read-1", result={"content": "File content here."})

    # --- Create SessionConfig ---
    session_config = SessionConfig(
        provider=TEST_PROVIDER, model=TEST_MODEL, goal=test_goal,
        agent_id=TEST_AGENT_ID, max_steps=max_steps, mcp_url=MCP_TEST_URL,
        mcp_timeout=DEFAULT_MCP_TIMEOUT
    )

    # --- Run Main Execution Logic ---
    await run_agent_session(session_config)

    # Assertions
    captured = capsys.readouterr()
    assert mock_llm_client.chat_completion.call_count == 2
    mock_mcp_execution.assert_called_once_with(operation_name="read_file", arguments={"path": target_file})

    # Check history passed to second LLM call contains the system message with MCP result
    second_call_args = mock_llm_client.chat_completion.call_args_list[1]
    messages_for_second_call = second_call_args.kwargs['messages']
    success_pattern_found = any("MCP Operation Successful" in msg.content and "File content here" in msg.content for msg in messages_for_second_call)
    assert success_pattern_found, "Expected MCP result message not found in history"

    # Check logs/output (adjust based on AgentRunner logging)
    # assert "Agent wants to execute: read_file" in captured.out # This log is in AgentRunner DEBUG
    # assert "MCP Operation Result (read_file):" in captured.out # This print is not in refactored run.py
    assert "Final Summary from Agent: Read file successfully." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_ask_user_then_finish(mock_llm_client, mock_mcp_execution, capsys, mocker):
    """Test agent asks user a question, gets input, then finishes."""
    test_goal = "Confirm action with user"
    max_steps = 5
    user_confirmation = "Yes, proceed."

    # Mock LLM Responses
    ask_question_text = "Should I proceed with the important action?"
    finish_call_json = """```json\n{{\n"mcp_operation": {{\n"operation_name": "finish_goal",\n"arguments": {"summary": "User confirmed action."}\n}}\n}}\n```"""
    mock_llm_client.chat_completion.side_effect = [ask_question_text, finish_call_json]

    # Mock User Input - Patch the helper in run.py
    # NOTE: Because run_agent_session doesn't handle user input directly anymore,
    # this scenario tests AgentRunner returning plain text, but the test setup
    # won't automatically feed input back in. We'll simulate the agent getting
    # the input in the *next* turn's history.
    # For this test, we assert the agent tried to ask, then finishes (as per side_effect).
    mock_prompt_input = mocker.patch('run.prompt_for_multiline_input', new_callable=AsyncMock)
    mock_prompt_input.return_value = user_confirmation # Mocking this won't affect the run_agent_session call directly

    # --- Create SessionConfig ---
    session_config = SessionConfig(
        provider=TEST_PROVIDER, model=TEST_MODEL, goal=test_goal,
        agent_id=TEST_AGENT_ID, max_steps=max_steps, mcp_url=MCP_TEST_URL,
        mcp_timeout=DEFAULT_MCP_TIMEOUT
    )

    # --- Run Main Execution Logic ---
    await run_agent_session(session_config)

    # Assertions
    captured = capsys.readouterr()
    assert mock_llm_client.chat_completion.call_count == 2 # First call asks, second finishes
    mock_mcp_execution.assert_not_called()
    mock_prompt_input.assert_not_called() # run_agent_session doesn't call this directly

    # Check history passed to second call (assuming AgentRunner added the assistant's question)
    second_call_args = mock_llm_client.chat_completion.call_args_list[1]
    messages_for_second_call = second_call_args.kwargs['messages']
    # The history should contain the assistant's question from the first turn.
    # It won't contain the user's reply because that interaction happens outside run_agent_session.
    assert any(ask_question_text in m.content for m in messages_for_second_call if m.role == 'assistant')

    # The output won't show the user prompt because run_agent_session doesn't do it.
    # assert "Agent Response:" in captured.out # Not printed by run_agent_session
    # assert ask_question_text in captured.out # Not printed by run_agent_session
    # assert "User Input Required." in captured.out # Not printed by run_agent_session

    assert "Final Summary from Agent: User confirmed action." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_reaches_max_steps(mock_llm_client, mock_mcp_execution, capsys):
    """Test that the loop stops correctly when max_steps is reached."""
    test_goal = "Loop indefinitely (test max_steps)"
    max_steps = 3 # Set a small limit

    # Configure mock LLM to always return a non-finishing text response
    mock_llm_client.chat_completion.return_value = "Thinking about the next step..."

    # --- Create SessionConfig ---
    session_config = SessionConfig(
        provider=TEST_PROVIDER, model=TEST_MODEL, goal=test_goal,
        agent_id=TEST_AGENT_ID, max_steps=max_steps, mcp_url=MCP_TEST_URL,
        mcp_timeout=DEFAULT_MCP_TIMEOUT
    )

    # --- Run Main Execution Logic ---
    await run_agent_session(session_config) # Corrected function call

    # Assertions
    captured = capsys.readouterr()
    assert mock_llm_client.chat_completion.call_count == max_steps
    mock_mcp_execution.assert_not_called()

    # Check output for max steps message
    # AgentRunner logs the step count, run_agent_session prints the final result
    # assert f"--- Step {max_steps}/{max_steps} ---" in captured.out # Check AgentRunner logs if needed
    assert "Outcome: max_steps" in captured.out
    assert f"Steps Taken: {max_steps}" in captured.out
    assert "Reason: Reached maximum steps." in captured.out # Check final message from result
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()

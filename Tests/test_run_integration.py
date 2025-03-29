import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, call # Import call for checking mock calls
from pathlib import Path
from typing import List, Dict, Optional, Any

# --- Add project root to path if needed (usually handled by root conftest.py) ---
# import sys
# project_root = Path(__file__).parent.parent.resolve()
# if str(project_root) not in sys.path:
#     sys.path.insert(0, str(project_root))
# --- End Path Setup ---

# Import the main function and relevant classes from run.py context
# We need to import `main` from `run` module
try:
    from run import run_agent_session as run_main# Import the main async function
    from Clients import Message, BaseClient, ProviderConfig, ModelConfig, PricingTier, get_client
    from Core import AgentRunner # Need AgentRunner for type hints if mocking instances
    from MCP.models import MCPSuccessResponse, MCPErrorResponse # For mocking MCP results
    from MCP.errors import ErrorCode
except ImportError as e:
    pytest.fail(f"Failed to import components for integration tests: {e}", pytrace=False)

# --- Constants ---
TEST_PROVIDER = "mock_provider" # Use a consistent mock provider name
TEST_MODEL = "mock_model"
TEST_AGENT_ID = "test-agent-integration"
MCP_TEST_URL = "http://mock-mcp:8000/mcp"

# --- Fixtures ---

@pytest.fixture
def mock_llm_client(mocker):
    """Mocks the LLM client used by AgentRunner and handles get_client."""
    # Create a client class that inherits from BaseClient to ensure isinstance checks pass
    class TestClient(BaseClient):
        def _initialize_provider_client(self):
            return MagicMock()

        def _format_messages(self, messages):
            return messages

        async def _execute_api_call(self, formatted_messages, api_model_name, stream, **kwargs):
            # For non-streaming, return a mock response object if needed by _process_response
            # For streaming, return an async iterator mock if needed
            return MagicMock() # Simple mock for this test setup

        def _process_response(self, response):
             # Return the value expected from chat_completion mock
            return "Response text"

        def _process_stream_chunk(self, chunk):
             # Return the value expected from stream_chat_completion mock if used
            return "Chunk text"

        # Add other abstract methods if BaseClient requires them
        def _get_sdk_exception_types(self):
            return ()
        def _extract_error_details(self, error):
            return None, str(error)


    # Create a fake config
    fake_config = ProviderConfig(
        name=TEST_PROVIDER,
        api_base="https://api.test",
        api_key_env="TEST_API_KEY",
        models={
            TEST_MODEL: ModelConfig(
                name=TEST_MODEL,
                context_length=10000,
                pricing=PricingTier(input=0.0, output=0.0)
            )
        },
        default_model=TEST_MODEL
    )

    # Set environment variable for API key
    mocker.patch.dict(os.environ, {"TEST_API_KEY": "fake-key"})

    # Create an instance of our TestClient class
    client_instance = TestClient(fake_config)
    # Configure the main methods used by the run loop
    client_instance.chat_completion = AsyncMock(return_value="Response text")
    client_instance.stream_chat_completion = AsyncMock() # Define if needed
    client_instance.close = AsyncMock()
    
    # Make sure required methods are available
    client_instance.get_available_models = lambda: [TEST_MODEL]
    client_instance.get_model_config = lambda model: fake_config.models[TEST_MODEL]
    
    # Return the actual instance, not a mock
    return client_instance

    # Patch asyncio.to_thread SPECIFICALLY for get_client to return our instance
    # This avoids interfering with other potential uses of asyncio.to_thread
    original_to_thread = asyncio.to_thread
    async def mock_to_thread_for_get_client(func, *args, **kwargs):
        if func == get_client and args and args[0] == TEST_PROVIDER:
            # print(f"DEBUG: Mocking to_thread for get_client('{args[0]}')") # Debug print
            return client_instance
        # print(f"DEBUG: Passing through to_thread call for {func.__name__}") # Debug print
        # Fallback to original for other functions (like input, if not mocked elsewhere)
        return await original_to_thread(func, *args, **kwargs)

    mocker.patch('run.asyncio.to_thread', side_effect=mock_to_thread_for_get_client)

    # Mock provider validation (assuming run.py uses this)
    mocker.patch('run.discover_and_validate_providers', return_value=[TEST_PROVIDER])

    return client_instance


@pytest.fixture
def mock_mcp_execution(mocker):
    """Mocks the AgentRunner's execute_mcp_operation method."""
    # Patch the method *where it's defined* (in the Core.agent_runner module)
    return mocker.patch('Core.agent_runner.AgentRunner.execute_mcp_operation', new_callable=AsyncMock)

# Removed the mock_user_input fixture as we will patch prompt_for_multiline_input directly

@pytest.fixture(autouse=True) # Apply automatically to tests in this file
def mock_env_vars(mocker):
    """Mocks environment variables needed by run.py"""
    mocker.patch.dict(os.environ, {"MCP_SERVER_URL": MCP_TEST_URL})

# --- Test Scenarios ---

@pytest.mark.asyncio
async def test_run_simple_finish_goal(mock_llm_client, mock_mcp_execution, capsys):
    """Test a scenario where the agent finishes the goal in one step."""
    test_goal = "Achieve simple goal"
    max_steps = 5

    # Configure mock LLM response to call finish_goal immediately
    finish_call_json = """
    ```json
    {
        "mcp_operation": {
            "operation_name": "finish_goal",
            "arguments": {
                "summary": "Goal achieved immediately."
            }
        }
    }
    ```
    """
    mock_llm_client.chat_completion.return_value = finish_call_json

    # Run the main function from run.py
    await run_main(
        goal_arg=test_goal,
        provider_arg=TEST_PROVIDER, # Specify provider to avoid interactive prompt
        agent_id=TEST_AGENT_ID,
        max_steps=max_steps,
        model_arg=TEST_MODEL # Specify model
    )

    # Assertions
    captured = capsys.readouterr()
    mock_llm_client.chat_completion.assert_called_once() # Called exactly once
    # Check if the initial message contained the goal
    called_messages = mock_llm_client.chat_completion.call_args.kwargs['messages']
    assert any(test_goal in msg.content for msg in called_messages if msg.role == 'user')

    mock_mcp_execution.assert_not_called() # finish_goal is handled by run.py loop, not executed via MCP call

    # Check output for agent thinking and finish message
    assert "Agent thinking..." in captured.out
    assert "Agent initiated 'finish_goal'" in captured.out
    assert "Final Summary from Agent: Goal achieved immediately." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once() # Ensure cleanup happened


@pytest.mark.asyncio
async def test_run_mcp_call_then_finish(mock_llm_client, mock_mcp_execution, capsys):
    """Test agent makes one MCP call, then finishes."""
    test_goal = "Read a file then finish"
    target_file = "/path/to/read.txt"
    max_steps = 5

    # --- Mock LLM Responses (Sequence) ---
    # 1. Call read_file
    read_call_json = f"""
    ```json
    {{
        "mcp_operation": {{
            "operation_name": "read_file",
            "arguments": {{"path": "{target_file}"}}
        }}
    }}
    ```
    """
    # 2. Call finish_goal after seeing read result
    finish_call_json = """
    ```json
    {
        "mcp_operation": {
            "operation_name": "finish_goal",
            "arguments": {"summary": "Read file successfully."}
        }
    }
    ```
    """
    mock_llm_client.chat_completion.side_effect = [read_call_json, finish_call_json]

    # --- Mock MCP Response ---
    mock_mcp_execution.return_value = MCPSuccessResponse(
        id="mcp-read-1",
        result={"content": "File content here."}
    )

    # --- Run Main ---
    await run_main(test_goal, TEST_PROVIDER, TEST_AGENT_ID, max_steps, TEST_MODEL)

    # --- Assertions ---
    captured = capsys.readouterr()
    assert mock_llm_client.chat_completion.call_count == 2

    # Check MCP call
    mock_mcp_execution.assert_called_once_with(
        operation_name="read_file",
        arguments={"path": target_file}
    )

    # Check history passed to second LLM call contains the system message with MCP result
    second_call_args = mock_llm_client.chat_completion.call_args_list[1]
    # Correct access: call_args is a tuple (args, kwargs) or use .kwargs directly if mocker >= 4.0.3
    messages_for_second_call = second_call_args.kwargs['messages'] # Use kwargs
    
    # Check for the MCP result in any message - the message role might vary by implementation
    success_pattern_found = False
    for msg in messages_for_second_call:
        if "MCP Operation Successful" in msg.content and "File content here" in msg.content:
            success_pattern_found = True
            break
    assert success_pattern_found, "Expected MCP result message not found in history"

    assert "Agent wants to execute: read_file" in captured.out
    assert "MCP Operation Result (read_file):" in captured.out
    assert "Agent initiated 'finish_goal'" in captured.out
    assert "Final Summary from Agent: Read file successfully." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_ask_user_then_finish(mock_llm_client, mock_mcp_execution, capsys, mocker):
    """Test agent asks user a question, gets input, then finishes."""
    test_goal = "Confirm action with user"
    max_steps = 5
    user_confirmation = "Yes, proceed."

    # --- Mock LLM Responses ---
    # 1. Ask the user
    ask_question_text = "Should I proceed with the important action?"
    # 2. Finish after getting user confirmation
    finish_call_json = """
    ```json
    {
        "mcp_operation": {
            "operation_name": "finish_goal",
            "arguments": {"summary": "User confirmed action."}
        }
    }
    ```
    """
    mock_llm_client.chat_completion.side_effect = [ask_question_text, finish_call_json]

    # --- Mock User Input ---
    # Directly mock the helper function in run.py that gets the input
    mock_prompt_input = mocker.patch('run.prompt_for_multiline_input', new_callable=AsyncMock)
    mock_prompt_input.return_value = user_confirmation

    # --- Run Main ---
    await run_main(test_goal, TEST_PROVIDER, TEST_AGENT_ID, max_steps, TEST_MODEL)

    # --- Assertions ---
    captured = capsys.readouterr()
    assert mock_llm_client.chat_completion.call_count == 2
    mock_mcp_execution.assert_not_called()

    # Check that our input mock was called
    mock_prompt_input.assert_called_once()

    # Check the output shows the agent asking and the prompt for user input
    assert "Agent Response:" in captured.out
    assert ask_question_text in captured.out
    assert "User Input Required." in captured.out
    # The prompt message itself comes from prompt_for_multiline_input, which we mocked,
    # so we might not see the exact "Your Response:" string unless we mock print within it.
    # Instead, check that the mock was called.

    # Check history passed to second LLM call includes user response
    second_call_args = mock_llm_client.chat_completion.call_args_list[1]
    messages_for_second_call = second_call_args.kwargs['messages'] # Use kwargs
    user_messages = [m for m in messages_for_second_call if m.role == 'user']
    # The test may only include the user confirmation message directly
    # The initial goal message might be part of the initial history setup
    assert len(user_messages) >= 1 # We just need at least one user message
    assert any(user_confirmation in m.content for m in user_messages)

    assert "Agent initiated 'finish_goal'" in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_reaches_max_steps(mock_llm_client, mock_mcp_execution, capsys):
    """Test that the loop stops correctly when max_steps is reached."""
    test_goal = "Loop indefinitely (test max_steps)"
    max_steps = 3 # Set a small limit

    # Configure mock LLM to always return a non-finishing text response
    mock_llm_client.chat_completion.return_value = "Thinking about the next step..."

    # --- Run Main ---
    await run_main(test_goal, TEST_PROVIDER, TEST_AGENT_ID, max_steps, TEST_MODEL)

    # --- Assertions ---
    captured = capsys.readouterr()
    # LLM should be called max_steps times
    assert mock_llm_client.chat_completion.call_count == max_steps
    mock_mcp_execution.assert_not_called()

    # Check output for max steps message
    assert f"--- Step {max_steps}/{max_steps} ---" in captured.out # Check the step counter line
    assert f"Reached maximum steps ({max_steps}). Stopping execution." in captured.out
    assert "Autonomous Run Finished" in captured.out
    mock_llm_client.close.assert_called_once()

# Add more scenarios:
# - Test MCP error handling (agent receives error, decides next step)
# - Test LLM call failure handling
# - Test KeyboardInterrupt during user input (might be tricky to simulate reliably in pytest)

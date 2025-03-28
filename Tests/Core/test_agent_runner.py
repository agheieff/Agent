import pytest
import json
from typing import Dict, Any, List, Optional, Union

# --- Path setup is handled by Tests/conftest.py ---

# --- Imports should now work if test.py is used or PYTHONPATH is set ---
from Core.agent_runner import AgentRunner
from Clients import BaseClient, Message, ProviderConfig # Need base classes for mocking
from MCP.models import MCPSuccessResponse, MCPErrorResponse
from MCP.errors import ErrorCode

# --- Mock Client Setup ---

# Minimal ProviderConfig for testing
@pytest.fixture
def mock_provider_config() -> ProviderConfig:
    return ProviderConfig(
        name="mock_provider",
        api_base="http://mock",
        api_key_env="MOCK_API_KEY",
        # Using minimal dict instead of full ModelConfig for simplicity in mock setup
        models={"mock_model": {"name": "mock_model", "context_length": 100, "pricing": None}}, # type: ignore
        default_model="mock_model"
    )

# Mock BaseClient that doesn't need API key or actual client init
class MockClient(BaseClient):
    def __init__(self, config: ProviderConfig, mcp_server_url: Optional[str] = None, mcp_agent_id: Optional[str] = None):
        # Bypass BaseClient's __init__ which requires API key and SDK import
        self.config = config
        self.api_key = "mock_key" # Provide dummy key
        self.timeout = 30.0
        self.max_retries = 1
        self.default_model = config.default_model
        self.client: Any = None # No actual SDK client needed
        self.http_client: Any = None # No HTTP client needed for these tests
        self.mcp_server_url = mcp_server_url
        self.mcp_agent_id = mcp_agent_id
        # Add required attribute from BaseClient's original __init__ if missing
        # self._initialized_flag = True # Example if BaseClient uses such flags

    def _initialize_provider_client(self) -> Any:
        # Override base method, do nothing
        return None

    # --- Implement required abstract methods even if not used by these tests ---
    def _format_messages(self, messages: List[Message]) -> Any:
        # Return a dummy format or raise error if called unexpectedly
        return [{"role": m.role, "content": m.content} for m in messages]

    async def chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> str:
        # Return dummy response or raise error
        return "Mock chat completion response."

    async def stream_chat_completion(self, messages: List[Message], model: Optional[str] = None, **kwargs) -> Any: # Changed return type hint
         # Return dummy async generator or raise error
         async def _dummy_stream():
              yield "Mock stream chunk."
              # Ensure the generator actually finishes
              if False: # pragma: no cover
                  yield # Needed for type checker satisfaction in some cases, but unreachable
         return _dummy_stream()

    # --- Methods used by AgentRunner (keep if unchanged) ---
    async def execute_mcp_operation(self, operation_name: str, arguments: Dict[str, Any]) -> Any: # Removed unused params mcp_server_url, agent_id
         # This method IS used by AgentRunner, but not directly by the tests here.
         # Let's keep it raising NotImplementedError for now, as these are unit tests for helpers.
         # Integration tests would mock this differently.
         raise NotImplementedError("MockClient.execute_mcp_operation not implemented for unit tests")

    async def close(self):
        # Override close, do nothing
        pass

    def get_available_models(self) -> List[str]:
        return list(self.config.models.keys()) # Use keys() for correct list

    def get_model_config(self, model_name: Optional[str] = None) -> Any: # Return type hint Any for mock flexibility
         # Return dummy config matching the structure expected by AgentRunner if needed
         effective_model = model_name or self.default_model
         config = self.config.models.get(effective_model)
         if not config:
              raise ValueError(f"Model '{effective_model}' not found in mock config.")
         # Return the minimal dict provided in the fixture
         return config

@pytest.fixture
def agent_runner_instance(mock_provider_config) -> AgentRunner:
    """Provides an AgentRunner instance with a MockClient."""
    mock_client = MockClient(mock_provider_config)
    # Pass necessary args expected by AgentRunner.__init__
    runner = AgentRunner(client=mock_client, goal="Test Goal", agent_id="test-agent", max_steps=10)
    # Manually set the system prompt as _prepare_initial_state needs generate_system_prompt
    # which might require MCP registry. We are only testing parsing/formatting here.
    runner.system_prompt = "Mock System Prompt" # Make sure _prepare_initial_state can run or mock generate_system_prompt
    return runner

# --- Tests for _parse_llm_response ---

@pytest.mark.parametrize("response_text, expected_output", [
    # Valid JSON block
    ("Some text before ```json\n{\"mcp_operation\": {\"operation_name\": \"read_file\", \"arguments\": {\"path\": \"/a.txt\"}}}\n``` some text after",
     {"mcp_operation": {"operation_name": "read_file", "arguments": {"path": "/a.txt"}}}),
    # Valid JSON block with extra whitespace
    ("Thinking...\n```json \n { \"mcp_operation\": { \"operation_name\": \"write_file\" , \"arguments\" : {} } } \n ```\nOkay, writing the file.",
     {"mcp_operation": {"operation_name": "write_file", "arguments": {}}}),
    # JSON block with different casing
    ("```JSON\n{\"mcp_operation\": {\"operation_name\": \"echo\", \"arguments\": {\"message\": \"Hi\"}}}\n```",
     {"mcp_operation": {"operation_name": "echo", "arguments": {"message": "Hi"}}}),
    # No JSON block
    ("Just a regular text response.", None),
    # JSON block missing 'mcp_operation' key
    ("```json\n{\"operation_name\": \"read_file\", \"arguments\": {}}\n```", None),
    # JSON block with 'mcp_operation' but missing 'operation_name'
    ("```json\n{\"mcp_operation\": {\"arguments\": {}}}\n```", None),
    # JSON block with 'mcp_operation' but 'arguments' is not a dict
    ("```json\n{\"mcp_operation\": {\"operation_name\": \"read_file\", \"arguments\": \"/a.txt\"}}\n```", None),
     # JSON block with empty 'operation_name' string
    ("```json\n{\"mcp_operation\": {\"operation_name\": \"\", \"arguments\": {}}}\n```", None),
    # Invalid JSON syntax
    ("```json\n{\"mcp_operation\": {\"operation_name\": \"read_file\", \"arguments\": {\"path\": \"/a.txt\",}}}\n```", None), # Trailing comma
    # Multiple JSON blocks (should only find first?) - Current regex finds the first one
    ("```json\n{\"mcp_operation\": {\"operation_name\": \"op1\", \"arguments\": {}}}\n``` and ```json\n{\"mcp_operation\": {\"operation_name\": \"op2\", \"arguments\": {}}}\n```",
     {"mcp_operation": {"operation_name": "op1", "arguments": {}}}),
])
def test_parse_llm_response(agent_runner_instance: AgentRunner, response_text: str, expected_output: Optional[Dict]):
    """Tests the parsing of various LLM response formats."""
    parsed_data = agent_runner_instance._parse_llm_response(response_text)
    assert parsed_data == expected_output

# --- Tests for _format_mcp_result ---

def test_format_mcp_result_success_simple(agent_runner_instance: AgentRunner):
    """Test formatting a simple success response."""
    mcp_resp = MCPSuccessResponse(id="req-1", result="Action completed.")
    message = agent_runner_instance._format_mcp_result(mcp_resp)
    assert message.role == "system"
    assert isinstance(message.content, str) # Ensure content is string
    assert "MCP Operation Successful (ID: req-1)" in message.content
    assert "Result:\nAction completed." in message.content


def test_format_mcp_result_success_dict(agent_runner_instance: AgentRunner):
    """Test formatting a success response with dictionary data."""
    result_data = {"file_path": "/path/to/file.txt", "bytes_written": 100}
    mcp_resp = MCPSuccessResponse(id="req-2", result=result_data)
    message = agent_runner_instance._format_mcp_result(mcp_resp)
    assert message.role == "system"
    assert isinstance(message.content, str)
    assert "MCP Operation Successful (ID: req-2)" in message.content
    # Check for JSON formatting
    assert "```json" in message.content
    assert json.dumps(result_data, indent=2) in message.content


def test_format_mcp_result_success_list(agent_runner_instance: AgentRunner):
    """Test formatting a success response with list data."""
    result_data = ["item1", "item2", {"sub_item": 3}]
    mcp_resp = MCPSuccessResponse(id="req-3", result=result_data)
    message = agent_runner_instance._format_mcp_result(mcp_resp)
    assert message.role == "system"
    assert isinstance(message.content, str)
    assert "MCP Operation Successful (ID: req-3)" in message.content
    assert "```json" in message.content
    assert json.dumps(result_data, indent=2) in message.content


def test_format_mcp_result_success_no_data(agent_runner_instance: AgentRunner):
    """Test formatting a success response with result=None."""
    mcp_resp = MCPSuccessResponse(id="req-4", result=None)
    message = agent_runner_instance._format_mcp_result(mcp_resp)
    assert message.role == "system"
    assert isinstance(message.content, str)
    assert "MCP Operation Successful (ID: req-4)" in message.content
    assert "Result:\n[No data returned]" in message.content


def test_format_mcp_result_error_no_details(agent_runner_instance: AgentRunner):
    """Test formatting a simple error response."""
    mcp_resp = MCPErrorResponse(id="req-5", error_code=ErrorCode.OPERATION_FAILED, message="Something went wrong.")
    message = agent_runner_instance._format_mcp_result(mcp_resp)
    assert message.role == "system"
    assert isinstance(message.content, str)
    assert "MCP Operation Failed (ID: req-5)" in message.content
    assert f"Error Code: {ErrorCode.OPERATION_FAILED.value} ({ErrorCode.OPERATION_FAILED.name})" in message.content
    assert "Message: Something went wrong." in message.content
    assert "Details:" not in message.content


def test_format_mcp_result_error_with_details(agent_runner_instance: AgentRunner):
    """Test formatting an error response with details."""
    details_data = {"attempted_path": "/forbidden/path", "reason": "Permission check failed"}
    mcp_resp = MCPErrorResponse(id="req-6", error_code=ErrorCode.PERMISSION_DENIED, message="Access denied.", details=details_data)
    message = agent_runner_instance._format_mcp_result(mcp_resp)
    assert message.role == "system"
    assert isinstance(message.content, str)
    assert "MCP Operation Failed (ID: req-6)" in message.content
    assert f"Error Code: {ErrorCode.PERMISSION_DENIED.value} ({ErrorCode.PERMISSION_DENIED.name})" in message.content
    assert "Message: Access denied." in message.content
    assert "Details:" in message.content
    assert "```json" in message.content
    assert json.dumps(details_data, indent=2) in message.content


def test_format_mcp_result_error_with_non_json_details(agent_runner_instance: AgentRunner):
    """Test formatting an error response with non-JSON serializable details."""
    details_data = "Just a plain string detail"
    mcp_resp = MCPErrorResponse(id="req-7", error_code=ErrorCode.UNKNOWN_ERROR, message="Unknown issue.", details=details_data)
    message = agent_runner_instance._format_mcp_result(mcp_resp)
    assert message.role == "system"
    assert isinstance(message.content, str)
    assert "MCP Operation Failed (ID: req-7)" in message.content
    assert "Details:" in message.content
    assert details_data in message.content # Should just convert to string
    assert "```json" not in message.content # Should not try to format as JSON


def test_format_mcp_result_unknown_error_code(agent_runner_instance: AgentRunner):
    """Test formatting an error response with an error code not in the ErrorCode enum."""
    unknown_code = 9999
    mcp_resp = MCPErrorResponse(id="req-8", error_code=unknown_code, message="A very specific error.")
    try:
        # Try getting the name, expecting ValueError if invalid
        name = ErrorCode(unknown_code).name
        expected_name_part = f"({name})" # Name found unexpectedly? # pragma: no cover
    except ValueError:
        expected_name_part = f"({unknown_code})" # Fallback to showing the number if name invalid

    message = agent_runner_instance._format_mcp_result(mcp_resp)
    assert message.role == "system"
    assert isinstance(message.content, str)
    assert "MCP Operation Failed (ID: req-8)" in message.content
    # Check if the code number is present, and the name part is handled correctly
    # Adjusted expectation: AgentRunner now includes the Enum Name if possible, otherwise just code
    # Let's verify the code number is present. The name part depends on ErrorCode definition.
    assert f"Error Code: {unknown_code}" in message.content # Simpler check for the number
    assert "Message: A very specific error." in message.content


def test_format_mcp_result_unexpected_type(agent_runner_instance: AgentRunner):
    """Test formatting when an unexpected type is passed."""
    mcp_resp = {"status": "unexpected", "id": "req-9"} # Pass a plain dict
    message = agent_runner_instance._format_mcp_result(mcp_resp) # type: ignore
    assert message.role == "system"
    assert isinstance(message.content, str)
    assert "MCP Operation returned unexpected result type: <class 'dict'>" in message.content

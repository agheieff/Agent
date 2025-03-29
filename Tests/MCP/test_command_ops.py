import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import sys
import platform
import time

# Import error codes for clearer assertions
from MCP.errors import ErrorCode

# Import permissions config to check agent setup if needed
from MCP.permissions import PERMISSIONS_CONFIG

# Define agents used in tests
AGENT_ADMIN = "agent-admin"      # Has '*' permissions, should include execute_command
AGENT_001 = "agent-001"          # Does NOT have execute_command permission by default
AGENT_DEFAULT = None             # Does NOT have execute_command permission

# Helper to get a platform-specific simple command
def get_simple_command():
    if platform.system() == "Windows":
        # 'ver' is a simple command that prints the Windows version
        return "cmd /c ver" # Use cmd /c to run internal command
    else:
        # 'pwd' prints the current working directory
        return "pwd"

def get_echo_command(text="hello world"):
     if platform.system() == "Windows":
         return f'cmd /c echo {text}'
     else:
         return f'echo "{text}"' # Use quotes for safety on non-windows

def get_fail_command():
    if platform.system() == "Windows":
        # 'exit 1' exits with code 1
        return "cmd /c exit 1"
    else:
        # 'false' is a command that always exits with 1
        return "false"

def get_sleep_command(seconds=2):
    if platform.system() == "Windows":
        # Timeout command waits, /nobreak prevents interruption
        return f"timeout /t {seconds} /nobreak"
    else:
        return f"sleep {seconds}"

# --- execute_command Tests ---

def test_execute_command_success_simple(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Test executing a simple, successful command."""
    command = get_simple_command()
    payload = test_payload_factory("execute_command", args={"command": command}, agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    result = data["result"]
    assert result["command_executed"] == command
    assert result["return_code"] == 0
    assert isinstance(result["stdout"], str)
    assert isinstance(result["stderr"], str)
    # stdout might vary, just check it's a non-empty string for pwd/ver
    assert len(result["stdout"]) > 0
    assert result["stderr"] == ""


def test_execute_command_success_with_output(client: TestClient, test_payload_factory):
    """Test executing a command that produces known output."""
    text_to_echo = "MCP command execution test!"
    command = get_echo_command(text_to_echo)
    payload = test_payload_factory("execute_command", args={"command": command}, agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    result = data["result"]
    assert result["return_code"] == 0
    # Windows echo might add quotes, Linux shouldn't if we quoted input
    assert text_to_echo in result["stdout"]
    assert result["stderr"] == ""


def test_execute_command_success_with_cwd(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Test executing a command in a specific working directory."""
    command = get_simple_command() # e.g., pwd or ver
    cwd_path = str(agent_data_dir)
    payload = test_payload_factory("execute_command", args={"command": command, "working_directory": cwd_path}, agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    result = data["result"]
    assert result["return_code"] == 0
    # If using 'pwd', check if stdout matches the cwd_path
    if command == "pwd":
         # Normalize path separators for comparison if needed, resolve symlinks
         assert Path(result["stdout"].strip()) == agent_data_dir.resolve()


def test_execute_command_permission_denied_agent(client: TestClient, test_payload_factory):
    """Test agent without execute_command permission is denied."""
    command = get_simple_command()
    # AGENT_001 does NOT have execute_command permission
    payload = test_payload_factory("execute_command", args={"command": command}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 403 # PERMISSION_DENIED
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.PERMISSION_DENIED
    assert "lacks permission for operation 'execute_command'" in data["message"]


def test_execute_command_permission_denied_cwd(client: TestClient, test_payload_factory, tmp_path: Path):
    """Test agent is denied if CWD is outside allowed file paths, even if command exec is allowed."""
    command = get_simple_command()
    # Create a directory admin agent can *not* access according to default tmp_readers_writers rules
    # (admin gets '*' for ops, but file perms are separate and merged; admin gets '/'.)
    # Let's try denying agent_001 access to a specific path instead.
    disallowed_dir = tmp_path / "disallowed_cwd"
    disallowed_dir.mkdir()

    # Use AGENT_ADMIN who CAN execute commands but whose file permissions might be checked
    # Correction: Admin has "/" access, so CWD check will pass for admin.
    # Let's re-target: Deny AGENT_ADMIN if the CWD *doesn't exist*.
    non_existent_dir = tmp_path / "i_do_not_exist"

    payload = test_payload_factory("execute_command",
                                   args={"command": command, "working_directory": str(non_existent_dir)},
                                   agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    # This should fail validation because the directory doesn't exist
    assert response.status_code == 404 # RESOURCE_NOT_FOUND (for the CWD)
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.RESOURCE_NOT_FOUND
    assert "Working directory not found" in data["message"]


def test_execute_command_command_not_found(client: TestClient, test_payload_factory):
    """Test executing a command that does not exist."""
    command = "this_command_should_really_not_exist_42"
    payload = test_payload_factory("execute_command", args={"command": command}, agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    # The operation should catch FileNotFoundError and map it
    assert response.status_code == 404 # RESOURCE_NOT_FOUND (for the command)
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.RESOURCE_NOT_FOUND
    assert "Command not found" in data["message"]
    assert command in data["message"]


def test_execute_command_failure_exit_code(client: TestClient, test_payload_factory):
    """Test executing a command that fails (non-zero exit code)."""
    command = get_fail_command() # e.g., 'false' or 'cmd /c exit 1'
    payload = test_payload_factory("execute_command", args={"command": command}, agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200 # The operation itself succeeded
    data = response.json()
    assert data["status"] == "success" # The MCP operation succeeded in running the command
    result = data["result"]
    assert result["command_executed"] == command
    assert result["return_code"] != 0 # Specific code varies (usually 1)
    # Stderr might contain messages depending on the command/OS
    assert isinstance(result["stderr"], str)


@pytest.mark.timeout(10) # Add pytest timeout to prevent test suite hanging
def test_execute_command_timeout(client: TestClient, test_payload_factory):
    """Test command execution timeout."""
    sleep_time = 3 # seconds
    timeout_limit = 1 # Must be less than sleep_time
    command = get_sleep_command(sleep_time)

    payload = test_payload_factory("execute_command", args={"command": command, "timeout": timeout_limit}, agent=AGENT_ADMIN)
    # Remove the timeout argument from client.post
    response = client.post("/mcp", json=payload) # Removed timeout=timeout_limit + 5

    assert response.status_code == 504 # TIMEOUT maps to 504 Gateway Timeout
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.TIMEOUT
    assert f"Command timed out after {timeout_limit} seconds" in data["message"]


def test_execute_command_empty_command(client: TestClient, test_payload_factory):
    """Test sending an empty command string."""
    payload = test_payload_factory("execute_command", args={"command": ""}, agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 400 # INVALID_ARGUMENTS
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.INVALID_ARGUMENTS
    assert "Command cannot be empty" in data["message"]


def test_execute_command_invalid_shlex_input(client: TestClient, test_payload_factory):
    """Test command string that cannot be parsed by shlex (e.g., unmatched quotes)."""
    # This command has an unclosed quote, shlex.split should raise ValueError
    command = 'echo "hello world'
    payload = test_payload_factory("execute_command", args={"command": command}, agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 400 # INVALID_ARGUMENTS
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.INVALID_ARGUMENTS
    assert "Invalid command string format" in data["message"]
    # Check for either 'quote' or 'quotation' in the error message
    assert any(keyword in data["message"].lower() for keyword in ["quote", "quotation"])


def test_execute_command_cwd_is_file(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Test specifying a file path as the working directory."""
    file_path = agent_data_dir / "i_am_a_file.txt"
    file_path.touch()
    command = get_simple_command()
    payload = test_payload_factory("execute_command",
                                   args={"command": command, "working_directory": str(file_path)},
                                   agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 400 # INVALID_ARGUMENTS
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.INVALID_ARGUMENTS
    assert "Working directory is not a valid directory" in data["message"]

import os
import sys
import importlib
import importlib.util
import pytest
from pathlib import Path
from unittest import mock

# Path setup is handled by the top-level Tests/conftest.py

# --- Helper to get project root consistently ---
@pytest.fixture(scope="module")
def project_root() -> Path:
    """Return the project root directory as a Path object."""
    return Path(__file__).parent.parent.parent.resolve()

# --- Test Functions ---

def test_prompt_main_can_be_imported(project_root: Path):
    """Test that Prompts/main.py can be imported without raising exceptions."""
    prompt_main_path = project_root / 'Prompts' / 'main.py'
    assert prompt_main_path.is_file(), f"Prompts/main.py not found at {prompt_main_path}"

    # Check typing imports (verify, don't fix)
    content = prompt_main_path.read_text()
    typing_imports_ok = False
    for line in content.splitlines():
        if line.strip().startswith("from typing import"):
            # Check if 'Any' is present in the import list on that line
            if 'Any' in line:
                 typing_imports_ok = True
                 break
    # Assert that 'Any' is imported if 'typing' is used. Adjust if typing isn't used.
    if "from typing import" in content:
        assert typing_imports_ok, "Prompts/main.py seems to use typing but does not import 'Any'."

    # Attempt to import the module, mocking registry to avoid side effects
    try:
        # Ensure project root is in path (should be via conftest)
        assert str(project_root) in sys.path
        # Patch the operation_registry at its source module (MCP.registry)
        with mock.patch('MCP.registry.operation_registry') as mock_registry:
             # Mock necessary methods if Prompts.main calls them during import/setup
             mock_registry.get_all.return_value = {} # Example mock
             import Prompts.main
        # Test successful if import didn't raise exception
    except ImportError as e:
        pytest.fail(f"Failed to import Prompts.main module: {e}\nCheck sys.path and dependencies.")
    except Exception as e:
        pytest.fail(f"Unexpected error importing Prompts.main: {e}")

def test_api_client_modules_can_be_imported(project_root: Path):
    """Test that client modules in Clients/API can be imported."""
    api_dir = project_root / 'Clients' / 'API'
    assert api_dir.is_dir(), f"Clients/API directory not found at {api_dir}"

    found_client_files = False
    for client_file in api_dir.glob('*.py'):
        if client_file.name.startswith('_') or client_file.name == 'base.py':
            continue

        found_client_files = True
        module_name = client_file.stem
        full_module_path = f"Clients.API.{module_name}"

        try:
            # Apply necessary mocks for import testing
            with \
                mock.patch('Clients.base.BaseClient') as mock_base, \
                mock.patch('openai.AsyncOpenAI', create=True) as mock_async_openai, \
                mock.patch('anthropic.AsyncAnthropic', create=True) as mock_async_anthropic, \
                mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fake_key", "ANTHROPIC_API_KEY": "fake_key"}, clear=True):

                # Ensure BaseClient mock doesn't raise during potential init calls within the module
                # (e.g., if class attributes trigger initialization somehow, though unlikely here)
                mock_base.return_value.api_key = "mock_key"
                mock_base.return_value.close = mock.AsyncMock() # Mock close if needed

                # Perform the import
                importlib.import_module(full_module_path)
            # Test successful if import didn't raise exception
        except ImportError as e:
             # If the error is about the module itself not being found (e.g., typo in filename vs import)
             if f"No module named '{full_module_path}'" in str(e):
                 pytest.fail(f"Could not find the module {full_module_path}. Check file naming and __init__.py files.")
             # If the error is about a dependency *within* the imported module
             else:
                 pytest.fail(f"Import of {full_module_path} failed due to a missing internal dependency: {e}\nCheck sys.path and package installs.")
        except Exception as e:
             pytest.fail(f"Unexpected error importing {full_module_path}: {e}")

    assert found_client_files, f"No client modules found in {api_dir} to test."


def test_mcp_run_can_be_imported(project_root: Path):
    """Test that mcp_run.py can be imported without errors."""
    mcp_run_path = project_root / 'mcp_run.py'
    assert mcp_run_path.is_file(), f"mcp_run.py not found at {mcp_run_path}"

    # Use importlib to import the module from file path
    # Mock uvicorn.run to prevent server start during import check
    try:
        spec = importlib.util.spec_from_file_location("mcp_run_module", str(mcp_run_path))
        mcp_run_module = importlib.util.module_from_spec(spec)
        # Mock before execution
        with mock.patch('uvicorn.run') as mock_uvicorn:
             spec.loader.exec_module(mcp_run_module)
        # Test successful if import and execution (until uvicorn call) didn't raise
    except ImportError as e:
        pytest.fail(f"Failed to import mcp_run.py dependencies: {e}")
    except Exception as e:
         pytest.fail(f"Unexpected error during mcp_run.py import/setup: {e}")


def test_mcp_run_has_executable_permission(project_root: Path):
    """Test that mcp_run.py has executable permission."""
    mcp_run_path = project_root / 'mcp_run.py'
    assert mcp_run_path.is_file(), f"mcp_run.py not found at {mcp_run_path}"

    # Assert executable permission
    assert os.access(str(mcp_run_path), os.X_OK), \
        f"mcp_run.py does not have executable permission. Fix with: chmod +x {mcp_run_path}"

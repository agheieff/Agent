import sys
import os
import importlib
import pytest
from pathlib import Path

# This test file assumes Tests/conftest.py has added the project root to sys.path

print(f"\nDEBUG [test_z_basic_import.py]: Running tests in {__file__}")
print(f"DEBUG [test_z_basic_import.py]: Current sys.path: {sys.path}")

# Define project root relative to this test file for checking
project_root_from_test = Path(__file__).parent.parent.parent.resolve()
print(f"DEBUG [test_z_basic_import.py]: Calculated project root: {project_root_from_test}")
core_dir = project_root_from_test / "Core"
agent_runner_file = core_dir / "agent_runner.py"
core_init_file = core_dir / "__init__.py"

def test_project_root_in_syspath():
    """Verify the project root is indeed in sys.path at execution time."""
    assert str(project_root_from_test) in sys.path, \
        f"Project root {project_root_from_test} not found in sys.path: {sys.path}"

def test_core_directory_exists():
    """Check if the Core directory exists."""
    assert core_dir.exists(), f"Core directory not found at {core_dir}"
    assert core_dir.is_dir(), f"Core path exists but is not a directory: {core_dir}"

def test_core_init_exists():
    """Check if Core/__init__.py exists."""
    assert core_init_file.exists(), f"Core/__init__.py not found at {core_init_file}"
    assert core_init_file.is_file(), f"Core/__init__.py exists but is not a file: {core_init_file}"

def test_agent_runner_file_exists():
    """Check if Core/agent_runner.py exists."""
    assert agent_runner_file.exists(), f"Core/agent_runner.py not found at {agent_runner_file}"
    assert agent_runner_file.is_file(), f"Core/agent_runner.py exists but is not a file: {agent_runner_file}"

def test_import_core_package_directly():
    """Tests if 'import Core' works."""
    try:
        import Core
        # If successful, check the path where it was found from
        print(f"DEBUG [test_z_basic_import.py]: Imported Core from: {Core.__file__}")
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import 'Core' package directly: {e}\nsys.path was: {sys.path}")
    except Exception as e:
        pytest.fail(f"Unexpected error importing 'Core' package directly: {e}")

def test_import_core_agent_runner_module():
    """Tests if 'from Core import agent_runner' works."""
    try:
        # Deliberately import the module first
        from Core import agent_runner
        print(f"DEBUG [test_z_basic_import.py]: Imported Core.agent_runner from: {agent_runner.__file__}")
        assert True
    except ModuleNotFoundError as e:
         # Check if the error is specifically about agent_runner or something it imports
         if 'agent_runner' in str(e):
              pytest.fail(f"Failed specifically importing 'Core.agent_runner' module: {e}\nsys.path was: {sys.path}")
         else:
              pytest.fail(f"'Core.agent_runner' import failed due to an issue within its own imports: {e}\nsys.path was: {sys.path}")
    except ImportError as e:
         pytest.fail(f"Generic ImportError importing 'Core.agent_runner' module: {e}\nsys.path was: {sys.path}")
    except Exception as e:
        pytest.fail(f"Unexpected error importing 'Core.agent_runner' module: {e}")

# This test depends on the previous one passing conceptually
@pytest.mark.depends(on=['test_import_core_agent_runner_module'])
def test_import_agent_runner_class_from_module():
    """Tests if 'from Core.agent_runner import AgentRunner' works."""
    try:
        from Core.agent_runner import AgentRunner
        assert True
    except ImportError as e:
         # Check if the error is specifically about AgentRunner or something else
         if 'AgentRunner' in str(e):
            pytest.fail(f"Failed specifically importing 'AgentRunner' class from Core.agent_runner: {e}")
         else:
            pytest.fail(f"Importing 'AgentRunner' class failed due to an issue within Core.agent_runner: {e}")
    except Exception as e:
        pytest.fail(f"Unexpected error importing 'AgentRunner' class: {e}")

# Note: Requires pytest-depends plugin (`pip install pytest-depends`)
# If you don't have it, remove the @pytest.mark.depends line

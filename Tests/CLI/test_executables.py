import os
import sys
import pytest
from pathlib import Path

# Path setup is handled by the top-level Tests/conftest.py

@pytest.fixture(scope="module")
def project_root() -> Path:
    """Return the project root directory as a Path object."""
    return Path(__file__).parent.parent.parent.resolve()


@pytest.fixture
def expected_executable_scripts(project_root: Path) -> list[Path]:
    """Returns paths to the expected executable script files in the project root."""
    # Define scripts expected to be executable
    # Exclude mcp_run.py if its permissions are tested elsewhere or not strictly required
    return [
        project_root / 'test.py',
        # project_root / 'api_test.py', # Moved to scripts/
        # project_root / 'prompt_test.py', # Moved to scripts/
        project_root / 'run.py',
        project_root / 'mcp_run.py', # Include if it should be directly executable
    ]

def test_executables_exist(expected_executable_scripts: list[Path]):
    """Verify that expected executable script files exist."""
    missing = [path for path in expected_executable_scripts if not path.is_file()]
    assert not missing, f"Expected executable script(s) not found: {missing}"

# Parameterize tests over the expected scripts
@pytest.mark.parametrize("script_path", [
    pytest.param(p, id=p.name) for p in (Path(__file__).parent.parent.parent.resolve() / s for s in ['test.py', 'run.py', 'mcp_run.py'])
    # Add other scripts from expected_executable_scripts here if needed
])
def test_script_has_executable_permission(script_path: Path):
    """Verify that specific scripts have executable permissions."""
    if not script_path.is_file(): # Skip if file doesn't exist (covered by other test)
        pytest.skip(f"Script {script_path.name} not found, skipping permission check.")
    assert os.access(str(script_path), os.X_OK), \
        f"{script_path.name} should have executable permission. Fix with: chmod +x {script_path}"

@pytest.mark.parametrize("script_path", [
    pytest.param(p, id=p.name) for p in (Path(__file__).parent.parent.parent.resolve() / s for s in ['test.py', 'run.py', 'mcp_run.py'])
    # Add other scripts here
])
def test_script_has_shebang(script_path: Path):
    """Verify that specific executable scripts have a proper shebang line."""
    if not script_path.is_file():
        pytest.skip(f"Script {script_path.name} not found, skipping shebang check.")

    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
        # Check for common Python shebangs
        assert first_line.startswith('#!') and 'python' in first_line, \
            f"{script_path.name} should start with a valid Python shebang (e.g., '#!/usr/bin/env python3')"
    except Exception as e:
        pytest.fail(f"Error reading or checking shebang for {script_path.name}: {e}")

# Remove tests that modify files (test_prompt_main_imports, test_client_api_imports, test_mcp_run_executable)
# Import checks are better handled in test_cli_modules.py

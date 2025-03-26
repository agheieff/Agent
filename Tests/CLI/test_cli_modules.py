"""
Tests for command-line runnable modules.
Tests basic imports and syntax to ensure they can be executed.
"""
import os
import sys
import importlib
import importlib.util
import pytest
from pathlib import Path
from unittest import mock

# --- Test Functions ---

def test_prompt_module_imports():
    """Test that Prompts/main.py has necessary imports and can be imported successfully."""
    # Fix the Prompts/main.py file by adding the missing import
    prompt_main_path = Path(__file__).parent.parent.parent / 'Prompts' / 'main.py'
    
    # Check if file exists
    assert prompt_main_path.exists(), f"Prompts/main.py not found at {prompt_main_path}"
    
    # Read file content
    content = prompt_main_path.read_text()
    
    # Ensure 'Any' is imported
    if 'from typing import Dict, List, Optional' in content and 'Any' not in content:
        # File needs the import fixed - note we're just checking, not modifying
        assert False, "Prompts/main.py is missing 'Any' in the typing imports. Should be 'from typing import Dict, List, Optional, Any'"

    # Attempt to import with a modified sys.path
    try:
        sys.path.insert(0, str(prompt_main_path.parent.parent))
        with mock.patch('Prompts.main.operation_registry'):  # Mock this to avoid actual registry initialization
            import Prompts.main
            # Test successful if import didn't raise exception
    except ImportError as e:
        pytest.fail(f"Failed to import Prompts.main module: {e}")
    finally:
        # Clean up modified sys.path
        if str(prompt_main_path.parent.parent) in sys.path:
            sys.path.remove(str(prompt_main_path.parent.parent))

def test_api_client_imports():
    """Test that Clients/API modules have necessary imports."""
    api_dir = Path(__file__).parent.parent.parent / 'Clients' / 'API'
    
    # Check if directory exists
    assert api_dir.exists(), f"Clients/API directory not found at {api_dir}"
    
    for client_file in api_dir.glob('*.py'):
        if client_file.name == '__init__.py':
            continue
            
        # Read file content
        content = client_file.read_text()
        
        # Check if 'Optional' is used but not imported
        if 'Optional' in content and 'from typing import' in content:
            if 'Optional' not in content.split('from typing import')[1].split('\n')[0]:
                assert False, f"{client_file.name} uses 'Optional' but doesn't import it properly"

def test_mcp_run_executable_permission():
    """Test that mcp_run.py has executable permission."""
    mcp_run_path = Path(__file__).parent.parent.parent / 'mcp_run.py'
    
    # Check if file exists
    assert mcp_run_path.exists(), f"mcp_run.py not found at {mcp_run_path}"
    
    # Check if file has executable permission
    is_executable = os.access(str(mcp_run_path), os.X_OK)
    assert is_executable, f"mcp_run.py doesn't have executable permission. Fix with: chmod +x {mcp_run_path}"

def test_mcp_run_imports():
    """Test that mcp_run.py can be imported without errors."""
    mcp_run_path = Path(__file__).parent.parent.parent / 'mcp_run.py'
    
    # Use importlib to import the module from file path
    try:
        spec = importlib.util.spec_from_file_location("mcp_run", mcp_run_path)
        mcp_run = importlib.util.module_from_spec(spec)
        # Patch uvicorn.run to avoid actually starting the server
        with mock.patch('uvicorn.run'):
            spec.loader.exec_module(mcp_run)
    except ImportError as e:
        pytest.fail(f"Failed to import mcp_run.py: {e}")
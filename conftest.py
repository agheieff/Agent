import pytest
import asyncio
import sys
import warnings
import os
from pathlib import Path

# Set environment variable to suppress the asyncio warnings
# This works well in most environments
os.environ["PYTHONWARNINGS"] = "ignore::RuntimeWarning"

# Add project root to the path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop.
    
    This is a better approach than the default function-scoped event loop
    that pytest-asyncio creates. This ensures proper cleanup at the end.
    """
    # Explicitly create a new loop instead of using get_event_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Yield the loop for use in tests
    yield loop
    
    # Clean it up
    if not loop.is_closed():
        loop.call_soon(loop.stop)
        loop.run_forever()
        loop.close()

    # Set the loop to None to avoid any lingering references
    asyncio.set_event_loop(None)

@pytest.fixture
def tool_parser():
    """Create a ToolParser instance with all format handlers registered."""
    from Core.parser import ToolParser
    from Core.formats import XMLFormatParser, AnthropicToolsParser, DeepseekToolsParser
    
    parser = ToolParser()
    
    # Register all format parsers if not already registered
    parser.register_parser(AnthropicToolsParser())
    parser.register_parser(DeepseekToolsParser())
    parser.register_parser(XMLFormatParser())
    
    return parser

@pytest.fixture
def tool_composer():
    """Create a ToolResponseComposer instance with all format composers registered."""
    from Core.composer import ToolResponseComposer
    from Core.formats import XMLFormatComposer
    
    composer = ToolResponseComposer()
    
    # Register XML format composer if not already registered
    composer.register_composer("xml", XMLFormatComposer())
    
    return composer
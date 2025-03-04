import pytest
import asyncio
import sys
import os
from pathlib import Path

os.environ["PYTHONWARNINGS"]="ignore::RuntimeWarning"
project_root=Path(__file__).parent
sys.path.insert(0,str(project_root))

@pytest.fixture(scope="session")
def event_loop():
    loop=asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    if not loop.is_closed():
        loop.call_soon(loop.stop)
        loop.run_forever()
        loop.close()
    asyncio.set_event_loop(None)

@pytest.fixture
def tool_parser():
    from Core.parser import ToolParser
    return ToolParser()

@pytest.fixture
def tool_composer():
    from Core.composer import ToolResponseComposer
    return ToolResponseComposer()

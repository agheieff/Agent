import asyncio
from typing import AsyncGenerator

class StreamManager:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def process_stream(self, stream) -> AsyncGenerator:
        try:
            async for chunk in stream:
                yield chunk
                await asyncio.sleep(0)
        except asyncio.TimeoutError:
            await self.close_stream(stream)
            raise
        except Exception as e:
            await self.close_stream(stream)
            raise RuntimeError(f"Stream processing error: {str(e)}") from e

    async def close_stream(self, stream) -> None:
        try:
            if hasattr(stream, 'aclose'):
                await stream.aclose()
        except Exception:
            pass

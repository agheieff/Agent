import asyncio
from typing import AsyncGenerator

class StreamManager:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def process_stream(self, stream: AsyncGenerator) -> AsyncGenerator:
        try:
            async for chunk in asyncio.wait_for(self._stream_generator(stream), self.timeout):
                yield chunk
        except asyncio.TimeoutError:
            await self.close_stream(stream)
            raise

    async def close_stream(self, stream: AsyncGenerator) -> None:
        try:
            await stream.aclose()
        except Exception:
            pass

    @staticmethod
    async def _stream_generator(stream: AsyncGenerator):
        async for chunk in stream:
            yield chunk

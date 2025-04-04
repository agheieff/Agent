import asyncio
from typing import AsyncGenerator, Any

class StreamManager:
    @staticmethod
    async def gather_chunks(stream: AsyncGenerator, max_chunks: int = None) -> str:
        content = ""
        count = 0
        async for chunk in stream:
            content += chunk
            count += 1
            if max_chunks and count >= max_chunks:
                break
        return content

    @staticmethod
    async def cancel_stream(stream: AsyncGenerator):
        try:
            await stream.aclose()
        except:
            pass

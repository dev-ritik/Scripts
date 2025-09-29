import asyncio
from typing import List, Coroutine, Any

import httpx


async def post_with_retries(url, payload, headers, retries=3) -> httpx.Response or None:
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)  # in seconds
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
                response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response
        except httpx.ConnectTimeout:
            print(f"[Attempt {attempt}] Connection timeout for url {url}.")
        except httpx.RequestError as e:
            print(f"[Attempt {attempt}] Request error for url {url}: {e}")
        await asyncio.sleep(2 ** attempt)  # Backoff: 2s, 4s, 8s

    return None


class AsyncDownloadManager:
    def __init__(self, max_concurrent: int = 10):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.tasks: List[asyncio.Task] = []

    async def _wrap(self, coro: Coroutine) -> Any:
        """Wrap coroutine with semaphore for concurrency control"""
        async with self.semaphore:
            return await coro

    def add(self, coro: Coroutine) -> None:
        """Add coroutine task to the manager"""
        task = asyncio.create_task(self._wrap(coro))
        self.tasks.append(task)

    async def run(self) -> List[Any]:
        """Run all scheduled tasks and wait for completion"""
        results = await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()  # reset after run
        return results

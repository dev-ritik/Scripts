import asyncio
from typing import List, Coroutine, Any

import httpx
from flask import Response, make_response

import init


async def post_with_retries(url, payload, headers, retries: int = 3, timeout: int = 30.0) -> httpx.Response or None:
    timeout = httpx.Timeout(timeout)  # in seconds
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
        await asyncio.sleep(1)

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


def add_caching_to_response(response: Any, ttl_prod: int = 3600, ttl_debug: int = 5) -> Response:
    """Add caching headers to the response"""
    response = make_response(response)
    if init.DEBUG:
        response.headers["Cache-Control"] = f"public, max-age={ttl_debug}"
    else:
        response.headers["Cache-Control"] = f"public, max-age={ttl_prod}"
    return response

def human_duration(seconds: int | float = None, minutes: int | float = None) -> str:
    if seconds is None and minutes is None:
        return ""

    total_seconds = int(seconds if seconds is not None else minutes * 60)

    units = [
        ("day", 86400),
        ("hour", 3600),
        ("min", 60),
        ("s", 1),
    ]

    parts = []
    for name, unit_seconds in units:
        value, total_seconds = divmod(total_seconds, unit_seconds)
        if value:
            parts.append(f"{value} {name}")

    return " ".join(parts) if parts else "0 s"

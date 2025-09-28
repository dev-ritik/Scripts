import asyncio
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

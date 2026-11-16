import asyncio
import inspect
import os
import string
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, List, Coroutine

import httpx
import pandas as pd
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


def strip_accents(text: str) -> str:
    # Decomposes characters (e.g., 'é' -> 'e' + '´') and drops non-spacing marks
    return ''.join(
        char for char in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(char)
    )


def load_dictionary() -> set[str]:
    file_path = '/usr/share/dict/words'
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dictionary file not found at {file_path}")

    words = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            word = line.strip().lower()
            words.add(word)
            words.add(strip_accents(word))  # Adds 'cafe' alongside 'café'

    return words


def is_valid_word(dictionary=None, word: str = None) -> bool:
    if not word:
        return False

    dictionary = dictionary or load_dictionary()

    return word.strip().lower() in dictionary


def str_to_bool(value: str) -> bool:
    if not value:
        return False
    return value.lower() in ("true", "1", "yes", "on")


def json_safe(value):
    """Convert YAML date/datetime values to JSON-friendly strings."""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def parse_utc(value):
    value = value.strip()

    if value.endswith(" UTC"):
        value = value[:-4] + "+00:00"

    dt = datetime.fromisoformat(value.replace(" ", "T"))

    if dt.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")

    return dt.astimezone(timezone.utc)


async def run_function(func, **kwargs) -> Any:
    response = func(**kwargs)

    if inspect.isawaitable(response):
        response = await response

    return response


def get_aggregate_message_by_user(messages_by_sender: dict, max_people: int = 15):
    message_count_by_sender = {}
    sender_weekly_counts = {}

    for sender, messages in messages_by_sender.items():
        message_count_by_sender[sender] = len(messages)
        words_counter = defaultdict(int)

        # bucket messages by ISO week
        weekly_counts = defaultdict(int)
        for message in messages:
            if message.message:
                words = message.message.split()
                for word in words:
                    if len(word) == 1 and (word.isdigit() or word in string.punctuation):
                        continue
                    words_counter[word] += 1

                if message.datetime:
                    year_week = message.datetime.strftime("%Y-%W")
                    weekly_counts[year_week] += 1

        sender_weekly_counts[sender] = dict(weekly_counts)

    # Get the top 15 most active people
    top_people = sorted(message_count_by_sender.items(), key=lambda x: x[1], reverse=True)[:max_people]

    people = []
    for name, chat_count in top_people:
        weekly_series = (
            pd.Series(sender_weekly_counts.get(name, {}))
            .sort_index()
            .astype(int)
        )
        moving_avg_series = (
            weekly_series.rolling(window=3, min_periods=1).mean().round(2)
        )

        weekly_counts_dict = {k: int(v) for k, v in weekly_series.to_dict().items()}
        moving_avg_dict = {k: float(v) for k, v in moving_avg_series.to_dict().items()}

        people.append({
            "name": name,
            "dp": f"/user/dp/{name}",
            "chats": chat_count,
            "chat_times": {
                "weekly_counts": weekly_counts_dict,
                "weekly_moving_avg": moving_avg_dict
            }
        })

    return people

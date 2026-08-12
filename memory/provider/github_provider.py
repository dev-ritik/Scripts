import os
import time
from datetime import datetime, date, timezone
from typing import List, Optional

import requests

from provider.base_provider import MemoryProvider, Message, MessageType, MediaType


class GitHubProvider(MemoryProvider):
    NAME = "GitHub"
    GITHUB_USERNAME = "dev-ritik"
    GITHUB_SEARCH_COMMITS_URL = "https://api.github.com/search/commits"

    def __init__(self):
        super().__init__()
        if not os.getenv("GITHUB_TOKEN"):
            self.WORKING = False
            print("GitHub token not found")
            return
        self.token = os.getenv("GITHUB_TOKEN")

    async def fetch(self,
                    on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    ignore_groups: bool = False,
                    exclude_system_messages: bool = False,
                    senders: List[str] = None,
                    search_regex: str = None) -> List[Message]:
        print(f"Starting to fetch from GitHub {on_date=} {start_date=} {end_date=}")

        """
        Fetches all individual commit messages and timestamps from 1 year ago today
        up to the present moment, handling API pagination.
        """
        memories = []
        start_date_str = start_date.strftime("%Y-%m-%d") if start_date else None
        end_date_str = end_date.strftime("%Y-%m-%d") if end_date else None

        query_string = f"author:{self.GITHUB_USERNAME} author-date:{start_date_str}..{end_date_str}"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json"
        }

        all_items = []
        page = 1

        while True:
            params = {
                "q": query_string,
                "per_page": 100,
                "sort": "author-date",  # Sort by commit date
                "order": "asc",  # Chronological order (oldest to newest)
                "page": page
            }

            try:
                response = requests.get(
                    self.GITHUB_SEARCH_COMMITS_URL,
                    headers=headers,
                    params=params
                )
                response.raise_for_status()

                search_results = response.json()

                items = search_results.get("items", [])
                if not items:
                    break

                all_items.extend(items)

                # if len(all_items) >= 1000:
                #     print("[Note] Reached GitHub's Search API limit of 1,000 maximum results.")
                # break

                page += 1
                time.sleep(0.2)  # Short pause to be mindful of rate limits

            except requests.exceptions.RequestException as e:
                print(f"\nNetwork error or invalid request on page {page}: {e}")
                if response := getattr(e, 'response', None):
                    print(f"Response error details: {response.text}")
                break

        if not all_items:
            print(f"No individual commits found from {start_date_str=} to {end_date_str=} for this user profile.")
            return memories

        for item in all_items:
            if not item:
                continue

            repo_data = item.get("repository", {})
            repo_name = repo_data.get("full_name", "Unknown Repo")

            commit_data = item.get("commit", {})
            message = commit_data.get("message", "").strip().split("\n")[0]

            author_data = commit_data.get("author", {})
            commit_time = author_data.get("date", "")

            message = f"Made a commit in {repo_name} with message {message}"

            try:
                dt = datetime.fromisoformat(commit_time)
            except ValueError:
                raise ValueError(f"Invalid date format for commit {commit_time}")

            memories.append(
                Message(
                    _datetime=dt.astimezone(timezone.utc).replace(tzinfo=None),
                    message_type=MessageType.SENT,
                    media_type=MediaType.TEXT,
                    message=message.strip(),
                    provider=GitHubProvider.NAME,
                    context={},
                )
            )

        memories.sort(key=lambda memory: memory.datetime)

        print("Done fetching from GitHub")
        return memories

    async def get_start_end_date(self):
        base_url = self.GITHUB_SEARCH_COMMITS_URL
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json"
        }

        # Query for the absolute first commit (oldest)
        first_params = {
            "q": f"author:{self.GITHUB_USERNAME}",
            "sort": "author-date",
            "order": "asc",
            "per_page": 1
        }

        # Query for the absolute latest commit (newest)
        latest_params = {
            "q": f"author:{self.GITHUB_USERNAME}",
            "sort": "author-date",
            "order": "desc",
            "per_page": 1
        }

        # Fetch oldest
        first_response = requests.get(base_url, headers=headers, params=first_params)
        first_response.raise_for_status()
        first_items = first_response.json().get("items", [])

        # Fetch newest
        latest_response = requests.get(base_url, headers=headers, params=latest_params)
        latest_response.raise_for_status()
        latest_items = latest_response.json().get("items", [])

        if first_items:
            first_commit = first_items[0]
            try:
                first_dt = datetime.fromisoformat(first_commit['commit']['author']['date'])
            except ValueError:
                raise ValueError(f"Invalid date format for commit {first_commit}")
        else:
            raise Exception("No first commit found.")

        if latest_items:
            latest_commit = latest_items[0]
            try:
                latest_dt = datetime.fromisoformat(latest_commit['commit']['author']['date'])
            except ValueError:
                raise ValueError(f"Invalid date format for commit {latest_commit}")
        else:
            raise Exception("No latest commit found.")

        return first_dt.date(), latest_dt.date()

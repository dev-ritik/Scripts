import asyncio
import os
import re
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import List, Optional, Dict

import aiofiles
from black.trans import defaultdict

import configs
from provider.base_provider import MemoryProvider, MessageType, Message


class DiaryProvider(MemoryProvider):
    NAME = "Diary"
    WORKING = True
    HIDE_PERSONAL_ENTRY = True

    def __init__(self):
        super().__init__()
        if not self.WORKING:
            return

        if not (diary_folder := os.getenv("DIARY_PATH")):
            self.WORKING = False
            print("Diary folder not found")
            return
        self.diary_folder = Path(diary_folder)
        if not self.diary_folder.exists():
            self.WORKING = False
            print("Diary folder not found")
            return

    def is_working(self):
        return self.WORKING

    def _get_diary_filepath_for_year(self, year: int):
        for filename in os.listdir(self.diary_folder):
            if f"{year}" in filename:
                return os.path.join(self.diary_folder, filename)
        return None

    @staticmethod
    def capitalize_after_newline(text: str) -> str:
        # Capitalize the first character of the string and after each newline
        return re.sub(r'(^|\n)(\s*)(\w)',
                      lambda m: m.group(1) + m.group(2) + m.group(3).upper(),
                      text)

    @staticmethod
    def _get_date_and_memory_from_text(text: str):
        """
        OVERWRITE THIS METHOD: To get a date and memory from a text based on how the diary is written.
        TODO: Parse formats like 22/1/2022-24/1/2022
        Currently
        - it removes any line starting with ~
        - Assumes the first value of CSV is the date or ~
        - Replace >> with a newline character
        - Capitalizes the first letter of each new line
        - returns the rest of the text as the memory.
        :param text: Raw line from diary
        :return: date, diary message for the day
        """

        split = text.split(',')
        if len(split) <= 1:
            return None, None
        date_str = split[0]
        if DiaryProvider.HIDE_PERSONAL_ENTRY and date_str in ['~', '-']:
            return None, None
        memory = ','.join(split[1:])
        memory = memory.strip('"')
        if memory.startswith("~"):
            return None, None
        memory = memory.replace('>>', '\n')
        memory = DiaryProvider.capitalize_after_newline(memory)

        try:
            date_str = datetime.strptime(date_str, "%d/%m/%Y")
            return date_str + timedelta(hours=23, minutes=59), memory
        except Exception as e:
            print(f"Error parsing date in {text}: {e}")
            return None, None

    async def fetch_on_date(self,
                            on_date: Optional[date],
                            ignore_groups: bool = False,
                            senders: List[str] = None,
                            search_regex: str = None) -> List[Message]:
        results = []
        if not self.WORKING:
            return results

        if senders:
            if len(senders) != 1:
                return results
            if senders[0].lower() != configs.USER.lower():
                return results

        print("Starting to fetch from Diary")

        if not on_date:
            raise ValueError("Diary provider requires a date")

        if senders:
            return []

        year = on_date.year
        diary_filepath = self._get_diary_filepath_for_year(year)

        if diary_filepath is None:
            print("Diary folder not found")
            return results

        pattern = re.compile(search_regex) if search_regex else None

        async with aiofiles.open(diary_filepath, "r", encoding="utf-8") as f:
            async for line in f:
                _dt, text = DiaryProvider._get_date_and_memory_from_text(line.strip())
                if not _dt:
                    continue

                if pattern and pattern.search(text) is None:
                    continue

                if _dt.date() == on_date:
                    results.append(Message(_datetime=_dt,
                                           message=text,
                                           message_type=MessageType.SENT,
                                           provider=self.NAME,
                                           sender=configs.USER
                                           ))

        print("Done fetching from Diary")
        return results

    async def fetch_dates(self,
                          start_date: date,
                          end_date: date,
                          ignore_groups: bool = False,
                          senders: List[str] = None,
                          search_regex: str = None
                          ) -> Dict[date, List[Message]]:
        results: Dict[date, List[Message]] = defaultdict(list)
        if not self.WORKING:
            return results

        print(f"Fetching diary entries from {start_date} to {end_date}")

        if senders:
            if len(senders) != 1:
                return results
            if senders[0].lower() != configs.USER.lower():
                return results

        for year in range(start_date.year, end_date.year + 1):
            diary_filepath = self._get_diary_filepath_for_year(year)

            if diary_filepath is None:
                print(f"No diary file found for {year}")
                continue

            pattern = re.compile(search_regex) if search_regex else None

            async with aiofiles.open(diary_filepath, "r", encoding="utf-8") as f:
                async for line in f:
                    _dt, text = DiaryProvider._get_date_and_memory_from_text(line.strip())
                    if not _dt:
                        continue

                    # Assuming lines are sorted ascending, we can stop reading
                    curr_date = _dt.date()
                    if curr_date < start_date:
                        continue
                    if curr_date > end_date:
                        break

                    if pattern and pattern.search(text) is None:
                        continue

                    results[curr_date].append(
                        Message(
                            _datetime=_dt.astimezone(timezone.utc).replace(tzinfo=None),
                            message=text,
                            message_type=MessageType.SENT,
                            provider=self.NAME,
                            sender=configs.USER
                        )
                    )

        print(f"Done fetching diary entries from {start_date} to {end_date}")
        return results

    @staticmethod
    async def _get_start_end_dates_for_file(filepath) -> tuple[date, date]:
        """Read one diary file asynchronously and return (start_date, end_date)."""
        start_date, end_date = None, None
        async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
            async for line in f:
                _dt, _ = DiaryProvider._get_date_and_memory_from_text(line.strip())
                if not _dt:
                    continue
                start_date = min(start_date, _dt) if start_date else _dt
                end_date = max(end_date, _dt) if end_date else _dt
        return start_date, end_date

    async def get_start_end_date(self):
        start_date = None
        end_date = None

        if not self.WORKING:
            return start_date, end_date

        print("Starting to fetch from Diary")

        if not (diary_folder := os.getenv("DIARY_PATH")):
            self.WORKING = False
            print("Diary folder not found")
            return start_date, end_date

        diary_folder = Path(diary_folder)
        if not diary_folder.exists():
            self.WORKING = False
            print("Diary folder not found")
            return start_date, end_date

        tasks = []
        for filename in os.listdir(diary_folder):
            diary_filepath = os.path.join(diary_folder, filename)
            if os.path.isfile(diary_filepath):
                tasks.append(DiaryProvider._get_start_end_dates_for_file(diary_filepath))

        results = await asyncio.gather(*tasks)

        # combine all start/end dates
        all_starts = [s for s, _ in results if s]
        all_ends = [e for _, e in results if e]
        start_date = min(all_starts) if all_starts else None
        end_date = max(all_ends) if all_ends else None

        return start_date.date(), end_date.date()

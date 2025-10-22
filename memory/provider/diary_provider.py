import asyncio
import os
import re
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Optional

import aiofiles

from provider.base_provider import MemoryProvider, MessageType, Message


class DiaryProvider(MemoryProvider):
    NAME = "Diary"
    WORKING = True

    def is_working(self):
        return self.WORKING

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
        if date_str in ['~', '-']:
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

    async def fetch(self, on_date: Optional[date], ignore_groups: bool = False) -> List[Message]:
        results = []
        if not self.WORKING:
            return results

        if not on_date:
            raise ValueError("Diary provider requires a date")

        print("Starting to fetch from Diary")

        year = on_date.year
        if not (diary_folder := os.getenv("DIARY_PATH")):
            self.WORKING = False
            print("Diary folder not found")
            return results
        diary_folder = Path(diary_folder)
        if not diary_folder.exists():
            self.WORKING = False
            print("Diary folder not found")
            return results

        diary_filepath = None
        for filename in os.listdir(diary_folder):
            if f'{year}' in filename:
                diary_filepath = os.path.join(diary_folder, filename)

        if diary_filepath is None:
            self.WORKING = False
            print("Diary folder not found")
            return results

        async with aiofiles.open(diary_filepath, "r", encoding="utf-8") as f:
            async for line in f:
                _dt, text = DiaryProvider._get_date_and_memory_from_text(line.strip())
                if not _dt:
                    continue

                if _dt.date() == on_date:
                    results.append(Message(_datetime=_dt,
                                           message=text,
                                           message_type=MessageType.SENT,
                                           provider=self.NAME,
                                           sender="Ritik"))

        print("Done fetching from Diary")
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

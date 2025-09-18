import os
import re
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Dict

import aiofiles

from provider.base_provider import MemoryProvider, MessageType


class DiaryProvider(MemoryProvider):
    NAME = "Diary"
    WORKING = True

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

    async def fetch(self, on_date: date, ignore_groups: bool = False) -> List[Dict]:
        results = []
        if not self.WORKING:
            return results

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
                    results.append(self.get_data_template(_datetime=_dt,
                                                           message=text,
                                                           message_type=MessageType.SENT,
                                                           provider=self.NAME,
                                                           sender="Ritik"))

        print("Done fetching from Diary")
        return results

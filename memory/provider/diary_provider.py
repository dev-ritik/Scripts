import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from provider.base_provider import MemoryProvider


class DiaryProvider(MemoryProvider):
    NAME = "Diary"

    @staticmethod
    def _get_date_and_memory_from_text(text: str):
        """
        Overwrite this method to get a date and memory from text based on how the diary is written.
        :param text: Raw line from diary
        :return: date, diary message for the day
        """

        date_str = text.split(',')[0]
        if date_str in ['~', '-']:
            return None, None
        try:
            date_str = datetime.strptime(date_str, "%d/%m/%Y")
        except Exception as e:
            print(f"Error parsing date in {text}: {e}")
            return None, None
        return date_str, ','.join(text.split(',')[1:])

    def fetch(self, on_date: datetime, ignore_groups: bool = False) -> List[Dict]:
        year = on_date.year
        if not (diary_folder := os.getenv("DIARY_PATH")):
            print("Diary folder not found")
            return []
        diary_folder = Path(diary_folder)
        if not diary_folder.exists():
            print("Diary folder not found")
            return []

        diary_filepath = None
        for filename in os.listdir(diary_folder):
            if f'{year}' in filename:
                diary_filepath = os.path.join(diary_folder, filename)

        if diary_filepath is None:
            print("Diary folder not found")
            return []

        memories = []
        with open(diary_filepath, "r", encoding="utf-8") as f:
            for line in f:
                _dt, text = DiaryProvider._get_date_and_memory_from_text(line.strip())
                if not _dt:
                    continue

                if _dt == on_date:
                    memories.append(self.get_data_template(_datetime=_dt, message=text, provider=self.NAME))

        return memories

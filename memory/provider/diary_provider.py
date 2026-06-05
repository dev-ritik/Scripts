import asyncio
import os
import re
import string
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import List, Optional, Dict

import aiofiles
from black.trans import defaultdict

import configs
from provider.base_provider import MemoryProvider, MessageType, Message
from utils import load_dictionary, is_valid_word, str_to_bool


class DiaryProvider(MemoryProvider):
    NAME = "Diary"
    WORKING = True

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

    def get_allowed_exposed_functions(self) -> List[str]:
        return ['get_most_word_written']

    def supports_home(self) -> bool:
        return self.is_working()

    async def _get_all_diary_words(self, pre_transform_fn, filter_fn, hide_personal_entry: bool = True):
        all_memories = self.fetch_dates(date(1900, 1, 1), date(2100, 1, 1), hide_personal_entry=hide_personal_entry)
        word_count = defaultdict(int)
        for memories in (await all_memories).values():
            for memory in memories:
                try:
                    for word in memory.message.split():
                        word = pre_transform_fn(word)
                        if filter_fn(word):
                            word_count[word] += 1
                except Exception as e:
                    print(f"Error processing memory: {e}")
        return word_count

    async def get_most_word_written(self, min_word_length=1,
                                    only_dict=False,
                                    only_non_dict=False,
                                    ignore_case=True,
                                    include_hidden=False,
                                    **kwargs):
        if isinstance(min_word_length, str):
            min_word_length = int(min_word_length)
        if isinstance(only_dict, str):
            only_dict = str_to_bool(only_dict)
        if isinstance(only_non_dict, str):
            only_non_dict = str_to_bool(only_non_dict)
        if isinstance(ignore_case, str):
            ignore_case = str_to_bool(ignore_case)
        if isinstance(include_hidden, str):
            include_hidden = str_to_bool(include_hidden)

        dictionary = load_dictionary()

        def filter_fn(word):
            if len(word) < min_word_length:
                return False
            if word.isdigit():
                return False
            if only_dict and not is_valid_word(dictionary, word.lower()):
                return False
            if only_non_dict and is_valid_word(dictionary, word.lower()):
                return False
            return True

        punc = string.punctuation + '“”‘’'

        def pre_transform_fn(word):
            if ignore_case:
                word = word.lower()
            if word.lower().endswith("'s"):
                word = word.removesuffix("'s")
            elif word.lower().endswith("s'"):
                word = word.removesuffix("'")
            word = word.strip(punc)
            return word

        word_count = await self._get_all_diary_words(pre_transform_fn, filter_fn,
                                                     hide_personal_entry=not include_hidden)
        most_common = sorted(word_count.items(), key=lambda x: x[1], reverse=True)[:40]
        return most_common

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
    def _get_date_and_memory_from_text(text: str, hide_personal_entry=True):
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

        memory = ','.join(split[1:])
        memory = memory.strip('"')
        memory = memory.replace('>>', '\n')
        memory = DiaryProvider.capitalize_after_newline(memory)

        if date_str in ['~', '-']:
            if hide_personal_entry:
                return None, None
            else:
                return None, memory

        if memory.startswith("~"):
            # TODO: The date is not available. This would just be a guess
            if hide_personal_entry:
                return None, None
            else:
                return None, memory[1:]

        try:
            date_str = datetime.strptime(date_str, "%d/%m/%Y")
            return date_str + timedelta(hours=23, minutes=59), memory
        except Exception as e:
            print(f"Error parsing date in {text}: {e}")
            # TODO: The date is not available. This would just be a guess
            return None, memory

    async def fetch_on_date(self,
                            on_date: Optional[date],
                            exclude_system_messages: bool = True,
                            senders: List[str] = None,
                            search_regex: str = None,
                            **kwargs) -> List[Message]:
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
                          senders: List[str] = None,
                          search_regex: str = None,
                          hide_personal_entry: bool = False,
                          **kwargs
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
            dt = None

            async with aiofiles.open(diary_filepath, "r", encoding="utf-8") as f:
                async for line in f:
                    _dt, text = DiaryProvider._get_date_and_memory_from_text(line.strip(),
                                                                             hide_personal_entry=hide_personal_entry)

                    # If the date is not available, use the previous date (approximate)
                    # TODO: improve this logic
                    dt = _dt or dt

                    if not dt:
                        continue

                    # Assuming lines are sorted ascending, we can stop reading
                    curr_date = dt.date()
                    if curr_date < start_date:
                        continue
                    if curr_date > end_date:
                        break

                    if pattern and pattern.search(text) is None:
                        continue

                    results[curr_date].append(
                        Message(
                            _datetime=dt.astimezone(timezone.utc).replace(tzinfo=None),
                            message=text,
                            message_type=MessageType.SENT,
                            provider=self.NAME,
                            sender=configs.USER
                        )
                    )

        print(f"Done fetching diary entries from {start_date=} to {end_date=}")
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

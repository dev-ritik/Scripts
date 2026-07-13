import asyncio
import os
import re
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from enum import Enum
from typing import List, Dict, Tuple, Optional

import aiofiles

from privacy import is_hidden


class MessageType(Enum):
    SENT = 'sent'
    RECEIVED = 'received'


class MediaType(Enum):
    # IMAGE = 'image'
    # VIDEO = 'video'
    TEXT = 'text'
    MIXED = 'mixed'
    NON_TEXT = 'non_text'


class FormattingType(Enum):
    BOLD = 'bold'
    ITALIC = 'italic'
    UNDERLINE = 'mention'
    STRIKETHROUGH = 'strikethrough'
    CODE = 'code'
    MENTION = 'mention'

class Compressions(Enum):
    NO_VIDEO = "NO_VIDEO"


class Message:
    def __init__(self, _datetime: datetime, message_type: MessageType = None, message: str = '', sender='',
                 provider=None, context: dict = None, chat_name=None, is_group: bool = False,
                 media_type: MediaType = MediaType.TEXT, formatting: List[dict] = None
                 ):

        self.datetime = _datetime
        self.message_type = message_type
        self.message = message
        self.sender = sender
        self.provider = provider
        self.context = context
        self.chat_name = chat_name
        self.is_group = is_group
        self.media_type = media_type
        self.formatting = formatting or []

    def to_dict(self):
        return {
            'datetime': self.datetime,
            'type': self.message_type.value if self.message_type else None,
            'message': self.message,
            'provider': self.provider,
            'sender': self.sender,
            'context': self.context,
            'chat_name': self.chat_name,
            'is_group': self.is_group,
            'media_type': self.media_type.value,
            'formatting': self.formatting
        }

    def is_hidden(self):
        return is_hidden(self)

    def update_display_name_in_formatted_message(self, name_regexes: Dict[str, str]):
        for formatting in self.formatting:
            if formatting['type'] == FormattingType.MENTION.value:
                raw_text = self.message[formatting['offset']:formatting['offset'] + formatting['length']]
                if display_name := MemoryProvider.get_display_name_from_text(raw_text, name_regexes):
                    formatting['display_name'] = display_name

    def __str__(self):
        return f"{self.datetime} - {self.sender}: {self.message}"

class MemoryProvider(ABC):
    NAME = None
    SYSTEM = 'system'
    UNKNOWN = 'unknown'
    MINIMUM_DATE = datetime(2000, 1, 1)
    MAXIMUM_DATE = datetime(2050, 1, 1)

    @staticmethod
    def _sender_matched(sender, allowed_senders: List[str]):
        for pattern in allowed_senders:
            if re.search(pattern, sender, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def get_display_name_from_text(text: str, name_regexes: Dict[str, str]):
        for display_name, regex in name_regexes.items():
            match = re.search(regex, text)
            if match:
                return display_name
        return None

    async def setup(self, compressions: List[Compressions] = None):
        """
        Method to set up any provider-specific tasks.
        :return:
        """
        return NotImplementedError

    async def fetch_on_date(self, on_date: Optional[date],
                            ignore_groups: bool = False,
                            exclude_system_messages: bool = True,
                            senders: List[str] = None,
                            search_regex: str = None) -> List[Message]:
        """
        Get all messages on the on_date. This is deprecated. Use fetch() instead.
        :param on_date: Larger date (inclusive)
        :param ignore_groups: Ignore group chats
        :param exclude_system_messages: Exclude system messages
        :param senders: Only fetch messages from these senders
        :param search_regex: Search for this string in message content
        :return: List of messages on the date
        """
        return await self.fetch(on_date=on_date, ignore_groups=ignore_groups, senders=senders, search_regex=search_regex)

    # @abstractmethod
    async def fetch(self, on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    ignore_groups: bool = False,
                    exclude_system_messages: bool = True,
                    senders: List[str] = None,
                    search_regex: str = None) -> List[Message]:
        """
        Get all messages from the date filter, time sorted.
        :param start_date: Smaller date (inclusive)
        :param end_date: Larger date (inclusive)
        :param on_date: Larger date (inclusive)
        :param ignore_groups: Ignore group chats
        :param exclude_system_messages: Exclude system messages
        :param senders: Only fetch messages from these senders
        :param search_regex: Search for this string in message content
        :return: List of messages on the date
        """
        if on_date:
            return await self.fetch_on_date(on_date, ignore_groups=ignore_groups,
                                            exclude_system_messages=exclude_system_messages,
                                            senders=senders, search_regex=search_regex)
        else:
            all_messages = await self.fetch_dates(
                start_date=start_date,
                end_date=end_date,
                ignore_groups=ignore_groups,
                exclude_system_messages=exclude_system_messages,
                senders=senders,
                search_regex=search_regex,
            )

            merged_list = []
            for value_list in all_messages.values():
                merged_list.extend(value_list)

            return sorted(merged_list, key=lambda m: m.datetime)

    async def fetch_dates(self, start_date: date,
                          end_date: date,
                          ignore_groups: bool = False,
                          exclude_system_messages: bool = True,
                          senders: List[str] = None,
                          search_regex: str = None) -> Dict[datetime.date, List[Message]]:
        """
        Get all messages for each day between start_date and end_date. This is deprecated. Use fetch() instead.
        :param start_date: Smaller date (inclusive)
        :param end_date: Larger date (inclusive)
        :param ignore_groups: Ignore group chats
        :param exclude_system_messages: Exclude system messages
        :param senders: Only fetch messages from these senders
        :param search_regex: search_regex for this string in message content
        :return: Dict of dates and messages for each date
        """
        tasks = []
        dates = []

        current = start_date
        while current <= end_date:
            tasks.append(self.fetch(current, ignore_groups=ignore_groups,
                                    exclude_system_messages=exclude_system_messages,
                                    senders=senders, search_regex=search_regex))
            dates.append(current)
            current += timedelta(days=1)

        results = await asyncio.gather(*tasks)
        return dict(zip(dates, results))

    async def get_asset(self, image_id: str) -> Tuple[bytes, str]:
        pass

    @abstractmethod
    def is_working(self) -> bool:
        return True

    def supports_home(self) -> bool:
        return False

    def get_allowed_exposed_functions(self) -> List[str]:
        # Override this method to allow specific functions to be exposed to the user. By default, no functions are exposed.
        return []

    async def get_start_end_date(self) -> Tuple[date | None, date | None]:
        # This is not the most efficient way to do this, but it's the easiest for now.
        all_memories = await self.fetch(on_date=None, ignore_groups=False)
        start_date = min(all_memories, key=lambda m: m.datetime).datetime.date()
        end_date = max(all_memories, key=lambda m: m.datetime).datetime.date()
        return start_date, end_date

    def get_logo(self):
        return f'/asset/{self.NAME}/logo.png'

    @staticmethod
    async def _convert_heic_to_jpeg(input_path: str):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            output_path = tmp.name

        try:
            # Heic files might not be supported. Hence, use this
            # sudo apt install libheif-examples
            proc = await asyncio.create_subprocess_exec(
                "heif-convert",
                input_path,
                output_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

            if proc.returncode != 0:
                raise RuntimeError("heif-convert failed")

            async with aiofiles.open(output_path, "rb") as f:
                return await f.read(), "image/jpeg"

        finally:
            if os.path.exists(output_path):
                os.remove(output_path)

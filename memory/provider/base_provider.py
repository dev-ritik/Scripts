import asyncio
import os
import re
import tempfile
from abc import ABC
from datetime import datetime, date, time
from enum import Enum
from typing import List, Dict, Tuple, Optional

import aiofiles

from configs import MAXIMUM_DATE, MINIMUM_DATE
from privacy import get_current_privacy_rules


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
    # TODO: Support links
    BOLD = 'bold'
    ITALIC = 'italic'
    UNDERLINE = 'underline'
    STRIKETHROUGH = 'strikethrough'
    CODE = 'code'
    MENTION = 'mention'

class Compressions(Enum):
    NO_VIDEO = "NO_VIDEO"


class Message:
    def __init__(self,
                 _datetime: datetime,
                 message_type: MessageType = None,
                 message: Optional[str] = '',
                 sender='',
                 provider=None,
                 context: dict = None,
                 chat_name=None,
                 is_group: bool = False,
                 media_type: MediaType = MediaType.TEXT,
                 formatting: List[dict] = None
                 ):

        self.datetime = _datetime
        self.message_type = message_type
        self.message = message or ''
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

    def is_hidden(self) -> bool:
        for rule in get_current_privacy_rules():
            if rule["providers"] != 'all' and self.provider not in rule["providers"]:
                continue

            start = rule["from"]
            if isinstance(start, date):
                start = datetime.combine(start, time(0, 0, 0))
            else:
                start = datetime.strptime(
                    start,
                    '%Y-%m-%d %H:%M:%S UTC'
                ).replace(tzinfo=None)
            end = rule["to"]
            if isinstance(end, date):
                end = datetime.combine(end, time(23, 59, 59))
            else:
                end = datetime.strptime(
                    end,
                    '%Y-%m-%d %H:%M:%S UTC'
                ).replace(tzinfo=None)

            if start <= self.datetime <= end:
                return True

        return False

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
    PLATFORM_USERNAME = None
    SYSTEM = 'system'
    UNKNOWN = 'unknown'
    DATA_PATH = None
    WORKING = True

    def __init__(self):
        self._start_end_date_cache = None

    def is_working(self):
        return self.WORKING

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

    async def fetch(self,
                    on_date: Optional[date] = None,
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
        :param on_date: the date (inclusive)
        :param ignore_groups: Ignore group chats
        :param exclude_system_messages: Exclude system messages
        :param senders: Only fetch messages from these senders
        :param search_regex: Search for this string in message content
        :return: List of messages on the date
        """
        print(f"Starting to fetch from {self.NAME} {on_date=} {start_date=} {end_date=}")
        memories: List[Message] = []
        if not self.is_working():
            return memories
        if not on_date and not (start_date or end_date):
            raise ValueError(f"{self.NAME} Either {on_date=} or {start_date=} and {end_date=} must be provided")
        if on_date and start_date and end_date:
            raise ValueError(f"{self.NAME} Either {on_date=} or {start_date=} and {end_date=} must be provided")
        if on_date:
            start_date = on_date
            end_date = on_date
        if not start_date or not end_date:
            raise ValueError(f"{self.NAME} Both {start_date=} and {end_date=} must be provided")

        _provider_start_date, _provider_end_date = await self.get_start_end_date()
        if not self.is_working():
            return memories
        if on_date and (on_date < _provider_start_date or on_date > _provider_end_date):
            return memories
        if start_date and end_date and (end_date < _provider_start_date or start_date > _provider_end_date):
            return memories
        memories = await self._fetch(start_date=start_date,
                                    end_date=end_date,
                                    ignore_groups=ignore_groups,
                                    exclude_system_messages=exclude_system_messages,
                                    senders=senders,
                                    search_regex=search_regex)
        print(f"Done fetching from {self.NAME}")
        memories.sort(key=lambda memory: memory.datetime)

        return memories

    async def _fetch(self,
                     start_date: date,
                     end_date: date,
                     ignore_groups: bool = False,
                     exclude_system_messages: bool = True,
                     senders: List[str] = None,
                     search_regex: str = None) -> List[Message]:
        """
        This method should be overridden by subclasses.
        :param start_date:
        :param end_date:
        :param ignore_groups:
        :param exclude_system_messages:
        :param senders:
        :param search_regex:
        :return:
        """
        raise NotImplementedError


    async def get_asset(self, image_id: str) -> Tuple[bytes, str]:
        pass

    def supports_home(self) -> bool:
        return False

    def get_allowed_exposed_functions(self) -> List[str]:
        # Override this method to allow specific functions to be exposed to the user. By default, no functions are exposed.
        return []

    async def get_start_end_date(self) -> Tuple[date | None, date | None]:
        # This is not the most efficient way to do this, but it's the easiest for now.
        if hasattr(self, "_start_end_date_cache") and self._start_end_date_cache:
            return self._start_end_date_cache

        if not self.is_working():
            return None, None

        _result = await self._get_start_end_date()
        self._start_end_date_cache = _result
        return _result

    async def _get_start_end_date(self) -> Tuple[date | None, date | None]:
        # This is not the most efficient way to do this, but it's the easiest for now.
        all_memories = await self._fetch(start_date=MINIMUM_DATE, end_date=MAXIMUM_DATE, ignore_groups=False)
        start_date = min(all_memories, key=lambda m: m.datetime).datetime.date()
        end_date = max(all_memories, key=lambda m: m.datetime).datetime.date()
        return start_date, end_date

    def get_logo(self) -> str:
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

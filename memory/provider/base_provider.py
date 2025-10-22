import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from enum import Enum
from typing import List, Dict, Tuple, Optional


class MessageType(Enum):
    SENT = 'sent'
    RECEIVED = 'received'


class MediaType(Enum):
    # IMAGE = 'image'
    # VIDEO = 'video'
    TEXT = 'text'
    MIXED = 'mixed'
    NON_TEXT = 'non_text'


class Compressions(Enum):
    NO_VIDEO = "NO_VIDEO"


class Message:
    def __init__(self, _datetime: datetime, message_type: MessageType = None, message: str = '', sender='',
                 provider=None, context: dict = None, chat_name=None, is_group: bool = False,
                 media_type: MediaType = MediaType.TEXT,
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
        }

class MemoryProvider(ABC):
    NAME = None

    async def setup(self, compressions: List[Compressions] = None):
        """
        Method to set up any provider-specific tasks.
        :return:
        """
        return NotImplementedError

    @abstractmethod
    async def fetch(self, on_date: Optional[date], ignore_groups: bool = False) -> List[Message]:
        pass

    async def fetch_dates(self, start_date: date, end_date: date, ignore_groups: bool = False) -> Dict[
        datetime.date, List[Message]]:
        tasks = []
        dates = []

        current = start_date
        while current <= end_date:
            tasks.append(self.fetch(current, ignore_groups=ignore_groups))
            dates.append(current)
            current += timedelta(days=1)

        results = await asyncio.gather(*tasks)
        return dict(zip(dates, results))

    async def get_asset(self, image_id: str) -> Tuple[bytes, str]:
        pass

    @abstractmethod
    def is_working(self):
        return True

    async def get_start_end_date(self) -> Tuple[date | None, date | None]:
        # This is not the most efficient way to do this, but it's the easiest for now.
        all_memories = await self.fetch(on_date=None, ignore_groups=False)
        start_date = min(all_memories, key=lambda m: m.datetime).datetime.date()
        end_date = max(all_memories, key=lambda m: m.datetime).datetime.date()
        return start_date, end_date

    def get_logo(self):
        return f'/asset/{self.NAME}/logo.png'

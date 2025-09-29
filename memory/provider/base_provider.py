from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from enum import Enum
from typing import List, Dict, Tuple

import asyncio


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

class MemoryProvider(ABC):
    NAME = None

    @staticmethod
    def get_data_template(_datetime: datetime, message_type: MessageType = None, message: str = '', sender='',
                          provider=None, context: dict = None, chat_name=None, is_group: bool = False,
                          media_type: MediaType = MediaType.TEXT,
                          ):
        return {
            'datetime': _datetime,
            'type': message_type.value if message_type else None,
            'message': message,
            'provider': provider,
            'sender': sender,
            'context': context,
            'chat_name': chat_name,
            'is_group': is_group,
            'media_type': media_type.value,
        }

    async def setup(self, compressions: List[Compressions] = None):
        """
        Method to set up any provider-specific tasks.
        :return:
        """
        return NotImplementedError

    @abstractmethod
    async def fetch(self, on_date: date, ignore_groups: bool = False) -> List[Dict]:
        pass

    async def fetch_dates(self, start_date: date, end_date: date, ignore_groups: bool = False) -> Dict[
        datetime.date, List[Dict]]:
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

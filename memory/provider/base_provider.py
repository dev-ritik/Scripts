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
    SYSTEM = 'system'


    async def setup(self, compressions: List[Compressions] = None):
        """
        Method to set up any provider-specific tasks.
        :return:
        """
        return NotImplementedError

    async def fetch_on_date(self, on_date: Optional[date], ignore_groups: bool = False, senders: List[str] = None) -> \
            List[Message]:
        """
        Get all messages on the on_date. This is deprecated. Use fetch() instead.
        :param on_date: Larger date (inclusive)
        :param ignore_groups: Ignore group chats
        :param senders: Only fetch messages from these senders (in regex)
        :return: List of messages on the date
        """
        return await self.fetch(on_date=on_date, ignore_groups=ignore_groups, senders=senders)

    # @abstractmethod
    async def fetch(self, on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    ignore_groups: bool = False, senders: List[str] = None) -> List[Message]:
        """
        Get all messages from the date filter, time sorted.
        :param start_date: Smaller date (inclusive)
        :param end_date: Larger date (inclusive)
        :param on_date: Larger date (inclusive)
        :param ignore_groups: Ignore group chats
        :param senders: Only fetch messages from these senders (in regex)
        :return: List of messages on the date
        """
        if on_date:
            return await self.fetch_on_date(on_date, ignore_groups=ignore_groups, senders=senders)
        else:
            all_messages = await self.fetch_dates(start_date=start_date, end_date=end_date, ignore_groups=ignore_groups,
                                          senders=senders)

            merged_list = []
            for value_list in all_messages.values():
                merged_list.extend(value_list)

            return sorted(merged_list, key=lambda m: m.datetime)

    async def fetch_dates(self, start_date: date, end_date: date, ignore_groups: bool = False,
                          senders: List[str] = None) -> Dict[datetime.date, List[Message]]:
        """
        Get all messages for each day between start_date and end_date. This is deprecated. Use fetch() instead.
        :param start_date: Smaller date (inclusive)
        :param end_date: Larger date (inclusive)
        :param ignore_groups: Ignore group chats
        :param senders: Only fetch messages from these senders (in regex)
        :return: Dict of dates and messages for each date
        """
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

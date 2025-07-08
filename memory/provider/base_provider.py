from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict


class MessageType(Enum):
    SENT = 'sent'
    RECEIVED = 'received'


class MediaType(Enum):
    IMAGE = 'image'
    VIDEO = 'video'
    TEXT = 'text'
    MIXED = 'mixed'
    NON_TEXT = 'non_text'


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

    @abstractmethod
    def fetch(self, on_date: datetime, ignore_groups: bool = False) -> List[Dict]:
        pass

    def fetch_dates(self, start_date: datetime, end_date: datetime, ignore_groups: bool = False) -> Dict[
        datetime, List[Dict]]:
        memory = {}
        current = start_date
        while current <= end_date:
            memory[current] = self.fetch(current, ignore_groups=ignore_groups)
            current += timedelta(days=1)
        return memory

    def get_asset(self, image_id: str) -> List[str] or None:
        pass

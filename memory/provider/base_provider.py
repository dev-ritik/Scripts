from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import List, Dict


class MemoryProvider(ABC):
    NAME = None

    @staticmethod
    def get_data_template(_datetime, message_type=None, message='', sender='', provider=None, context: dict = None, group_name=False):
        return {
            'datetime': _datetime,
            'type': message_type,
            'message': message,
            'provider': provider,
            'sender': sender,
            'context': context,
            'group_name': group_name
        }

    @abstractmethod
    def fetch(self, on_date: datetime, ignore_groups: bool = False) -> List[Dict]:
        pass


class MessageType(Enum):
    SENT = 'sent'
    RECEIVED = 'received'

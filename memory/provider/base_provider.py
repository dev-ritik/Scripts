from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import List, Dict


class MessageType(Enum):
    SENT = 'sent'
    RECEIVED = 'received'


class MemoryProvider(ABC):
    NAME = None

    @staticmethod
    def get_data_template(_datetime, message_type: MessageType = None, message='', sender='', provider=None,
                          context: dict = None, chat_name=None, is_group=False):
        return {
            'datetime': _datetime,
            'type': message_type.value if message_type else None,
            'message': message,
            'provider': provider,
            'sender': sender,
            'context': context,
            'chat_name': chat_name,
            'is_group': is_group,
        }

    @abstractmethod
    def fetch(self, on_date: datetime, ignore_groups: bool = False) -> List[Dict]:
        pass

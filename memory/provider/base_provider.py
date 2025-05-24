from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import List, Dict


class MemoryProvider(ABC):
    NAME = None

    @staticmethod
    def get_data_template(_datetime, message_type=None, message='', sender='', provider=None, context: dict = None):
        return {
            'datetime': _datetime,
            'type': message_type,
            'message': message,
            'provider': provider,
            'sender': sender,
            'context': context,
        }

    @abstractmethod
    def fetch(self, on_date: datetime) -> List[Dict]:
        pass


class MessageType(Enum):
    SENT = 'sent'
    RECEIVED = 'received'

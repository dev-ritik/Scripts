import json
import os
from datetime import datetime
from typing import List, Dict

from provider.base_provider import MemoryProvider, MessageType


class InstagramProvider(MemoryProvider):
    NAME = "Instagram"

    USER = 'Ritik Kumar'
    SYSTEM = 'system'
    DELETED_USER = 'deleted_user'

    @staticmethod
    def fix_mojibake(text: str) -> str:
        # Get the emojis
        try:
            return text.encode("latin1").decode("utf-8")
        except UnicodeDecodeError:
            return text  # fallback if it fails

    @staticmethod
    def clean_message(message):
        # message = message.replace('\n', ' ').lower()
        # Deal with some weird tokens
        message = InstagramProvider.fix_mojibake(message)
        # cleaned_message = message.encode('ascii', 'ignore').decode('ascii')

        # Remove multiple spaces in message
        # message = re.sub(' +', ' ', message)
        return message.strip()

    DATA = []
    from datetime import datetime

    @staticmethod
    def parse_json(data, friend, on_date):
        messages = []
        _friend = ''

        _friend = next(
            (key.get('name') for key in data['participants'] if key.get('name') != InstagramProvider.USER),
            friend
        )

        for message in data['messages']:
            text = None

            # print(message)
            if message.get('type') == 'Generic':
                text = message.get('content')
                if not text:
                    continue
                if text.startswith('Say hi to') or text.endswith('Say hi to'):
                    continue
            elif message.get('type') == 'Share':
                text = f"{message.get('content')}{": " if message.get('content') else ""}{message.get('share', {}).get('link')}"
            elif message.get('type') == 'Call':
                text = message.get('content')
            else:
                print(f'Unknown message {message}')

            if not text:
                continue

            text = InstagramProvider.clean_message(text)
            _dt = datetime.fromtimestamp(message.get('timestamp_ms') / 1000.0)

            if message.get('sender_name') == InstagramProvider.USER:
                message_type = MessageType.SENT
            else:
                message_type = MessageType.RECEIVED

            if _dt.date() == on_date.date():
                output = MemoryProvider.get_data_template(_dt, message_type, text, sender=message.get('sender_name'),
                                                          provider=InstagramProvider.NAME)
                messages.append(output)

            messages.reverse()
        return messages

    def fetch(self, on_date: datetime) -> List[Dict]:
        chat_path = 'data/instagram'

        memories = []
        for found in os.listdir(chat_path):
            friend = '_'.join(found.split('_')[:-1])
            friend_path = os.path.join(chat_path, found)
            if friend == found:
                friend = self.DELETED_USER
            try:
                with open(os.path.join(friend_path, 'message_1.json'), 'r') as f:
                    data = json.load(f)

                memories.extend(self.parse_json(data, friend, on_date))
            except FileNotFoundError as e:
                pass
        memories.sort(key=lambda memory: memory['datetime'])
        return memories

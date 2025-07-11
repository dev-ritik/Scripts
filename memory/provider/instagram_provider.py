import json
import os
from datetime import datetime, date
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
        return InstagramProvider.fix_mojibake(message).strip()

    @staticmethod
    def parse_json(data, name_from_file, on_date, ignore_groups: bool = False):
        messages = []
        chat_name = name_from_file

        is_group = len(data['participants']) > 2
        if not is_group:
            chat_name = next(
                (key.get('name') for key in data['participants'] if key.get('name') != InstagramProvider.USER),
                name_from_file
            )
            chat_name = InstagramProvider.clean_message(chat_name)

        if ignore_groups and is_group:
            return []

        for message in data['messages']:
            text = message.get('content')
            if text and 'sent an attachment' in text:
                text = ''
            if text and (text.startswith('Say hi to') or text.endswith('Say hi to')):
                continue
            share_link = f"{message.get('share', {}).get('link', '')}"
            share_caption = f"{message.get('share', {}).get('share_text', '')}"
            share_text = f"{share_caption}{" " if share_link else ""}{share_link}"
            text = f"{text if text else ""}{" " if text and share_text else ""}{"Shared: " if share_text else ""}{share_text}"
            if not text:
                continue

            text = InstagramProvider.clean_message(text)
            _dt = datetime.fromtimestamp(message.get('timestamp_ms') / 1000.0)

            sender_name = InstagramProvider.clean_message(message.get('sender_name'))
            message_type = MessageType.SENT if sender_name == InstagramProvider.USER else MessageType.RECEIVED

            if _dt.date() == on_date:
                output = MemoryProvider.get_data_template(_dt, message_type, text,
                                                          sender=sender_name,
                                                          provider=InstagramProvider.NAME,
                                                          chat_name=chat_name,
                                                          is_group=is_group)
                messages.append(output)

        messages.reverse()
        return messages

    def fetch(self, on_date: date, ignore_groups: bool = False) -> List[Dict]:
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

                memories.extend(self.parse_json(data, friend, on_date, ignore_groups))
            except FileNotFoundError as e:
                pass
        memories.sort(key=lambda memory: memory['datetime'])
        return memories

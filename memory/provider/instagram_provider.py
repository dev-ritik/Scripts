import asyncio
import json
import mimetypes
import os
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Tuple

import aiofiles

from provider.base_provider import MemoryProvider, MessageType, MediaType


class InstagramProvider(MemoryProvider):
    NAME = "Instagram"

    USER = 'Ritik Kumar'
    SYSTEM = 'system'
    DELETED_USER = 'deleted_user'
    INSTAGRAM_PATH = 'data/instagram'

    def is_working(self):
        return True

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
            _dt = datetime.fromtimestamp(message.get('timestamp_ms') / 1000.0)
            if _dt.date() != on_date:
                continue

            text = message.get('content')
            if text and 'sent an attachment' in text:
                text = ''
            if text and (text.startswith('Say hi to') or text.endswith('Say hi to')):
                continue
            share_link = f"{message.get('share', {}).get('link', '')}"
            share_caption = f"{message.get('share', {}).get('share_text', '')}"
            share_text = f"{share_caption}{" " if share_link else ""}{share_link}"
            assets = message.get('photos', []) + message.get('videos', [])
            contexts = []
            if assets:
                for asset in assets:
                    asset = asset.get('uri', '')
                    if not asset.startswith('your_instagram_activity/messages/inbox/'):
                        print("Invalid photo path")
                        continue
                    else:
                        photo_id = asset[len('your_instagram_activity/messages/inbox/'):]
                        asset_id = InstagramProvider.generate_asset_id(photo_id)
                        photo_path = InstagramProvider.get_file_path(file_id=photo_id)
                        contexts.append({
                            "asset_id": asset_id,
                            "mime_type": mimetypes.guess_type(photo_path)[0],
                            "new_tab_url": f'/asset/{InstagramProvider.NAME}/{asset_id}'
                        })
            text = f"{text if text else ""}{" " if text and share_text else ""}{share_text}"
            if not text and not contexts:
                continue

            text = InstagramProvider.clean_message(text) if text else ''
            media_type = MediaType.NON_TEXT if contexts else MediaType.TEXT

            sender_name = InstagramProvider.clean_message(message.get('sender_name'))
            message_type = MessageType.SENT if sender_name == InstagramProvider.USER else MessageType.RECEIVED

            contexts = contexts if contexts else [None]
            for context in contexts:
                messages.append(MemoryProvider.get_data_template(_dt, message_type, text,
                                                          sender=sender_name,
                                                          provider=InstagramProvider.NAME,
                                                          chat_name=chat_name,
                                                                 media_type=media_type,
                                                                 context=context,
                                                                 is_group=is_group))

        messages.reverse()
        return messages

    async def fetch(self, on_date: date, ignore_groups: bool = False) -> List[Dict]:
        print("Starting to fetch from Instagram")

        chat_path = 'data/instagram'

        tasks = []
        for found in os.listdir(chat_path):
            friend = '_'.join(found.split('_')[:-1])
            friend_path = Path(os.path.join(os.path.join(chat_path, found), 'message_1.json'))

            if not friend_path.exists():
                continue

            if friend == found:
                friend = self.DELETED_USER

            tasks.append(self._read_and_parse(friend_path, friend, on_date, ignore_groups))

        memories_nested = await asyncio.gather(*tasks)
        memories = [item for sublist in memories_nested for item in sublist]
        memories.sort(key=lambda m: m['datetime'])
        print("Done fetching from Instagram")
        return memories

    async def _read_and_parse(self, filepath: Path, friend: str, on_date: date, ignore_groups: bool):
        try:
            async with aiofiles.open(filepath, mode='r', encoding='utf-8') as f:
                raw = await f.read()
                data = json.loads(raw)
                return self.parse_json(data, friend, on_date, ignore_groups)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    @staticmethod
    def generate_asset_id(file_id) -> str:
        return file_id.replace('/', '___')

    @staticmethod
    def get_file_id_from_asset_id(asset_id: str) -> str:
        return asset_id.replace('___', '/')

    @staticmethod
    def get_file_path(asset_id: str = None, file_id=None):
        if not asset_id and not file_id:
            raise ValueError("Either asset_id or file_id must be provided")

        file_id = InstagramProvider.get_file_id_from_asset_id(asset_id) if asset_id else file_id
        media_file_path = os.path.join(InstagramProvider.INSTAGRAM_PATH, file_id)
        return media_file_path

    async def get_asset(self, asset_id: str) -> Tuple[bytes, str]:
        media_file_path = InstagramProvider.get_file_path(asset_id=asset_id)
        if not os.path.exists(media_file_path):
            raise FileNotFoundError(f"{media_file_path} does not exist")

        mime_type, _ = mimetypes.guess_type(media_file_path)
        if mime_type is None:
            raise ValueError("Could not determine MIME type")

        async with aiofiles.open(media_file_path, "rb") as media_file:
            media_data = await media_file.read()
        return media_data, mime_type

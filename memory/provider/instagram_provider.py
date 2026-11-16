import asyncio
import json
import mimetypes
import os
import re
from collections import defaultdict
from datetime import datetime, date, timezone
from pathlib import Path
from typing import List, Tuple, Optional

import aiofiles
from dateutil import parser
from flask import jsonify

from configs import MINIMUM_DATE, MAXIMUM_DATE, USER
from init import DATA_DIR
from profile import get_regex_from_name
from provider.base_provider import MemoryProvider, MessageType, MediaType, Message
from utils import get_aggregate_message_by_user


class InstagramProvider(MemoryProvider):
    NAME = "Instagram"

    PLATFORM_USERNAME = 'Ritik Kumar'
    DELETED_USER = 'deleted_user'
    DATA_PATH = os.path.join(DATA_DIR, 'instagram')
    INSTAGRAM_MESSAGE_PATH = os.path.join(DATA_PATH, 'messages')
    INSTAGRAM_FOLLOWER_FOLLOWING_PATH = os.path.join(DATA_PATH, 'followers_and_following')

    # Instagram adds these in regional language sometimes
    REGIONAL_LANGUAGE_LIKED_MESSAGE = [
        'ಸಂದೇಶವನ್ನು ಇಷ್ಟಪಟ್ಟಿದ್ದಾರೆ'
    ]

    def __init__(self):
        super().__init__()
        chat_path = Path(self.INSTAGRAM_MESSAGE_PATH)
        if not chat_path.exists():
            print("Instagram data folder not found")
            self.WORKING = False
            return

    def get_allowed_exposed_functions(self) -> List[str]:
        return ['get_followers', 'get_following', 'get_close_friends', 'get_share_data']

    def supports_home(self) -> bool:
        return self.is_working() and self.supports_followers() and self.supports_following() and self.supports_close_friends()

    def supports_followers(self) -> bool:
        if not self.is_working():
            return False

        return Path(f'{self.INSTAGRAM_FOLLOWER_FOLLOWING_PATH}/followers_1.json').exists()

    def supports_following(self) -> bool:
        if not self.is_working():
            return False

        return Path(f'{self.INSTAGRAM_FOLLOWER_FOLLOWING_PATH}/following.json').exists()

    def supports_close_friends(self) -> bool:
        if not self.is_working():
            return False
        return Path(f'{self.INSTAGRAM_FOLLOWER_FOLLOWING_PATH}/close_friends.json').exists()

    async def get_followers(self, **kwargs):
        if not self.supports_followers():
            return {}
        follower_path = Path(f'{self.INSTAGRAM_FOLLOWER_FOLLOWING_PATH}/followers_1.json')
        with open(follower_path, 'r', encoding='utf-8') as f:
            return [follower['string_list_data'] for follower in
                    json.load(f, object_hook=InstagramProvider.fix_meta_encoding)]

    async def get_following(self, **kwargs):
        if not self.supports_following():
            return {}
        following_path = Path(f'{self.INSTAGRAM_FOLLOWER_FOLLOWING_PATH}/following.json')
        with open(following_path, 'r', encoding='utf-8') as f:
            return json.load(f, object_hook=InstagramProvider.fix_meta_encoding)['relationships_following']

    async def get_close_friends(self, **kwargs):
        if not self.supports_close_friends():
            return {}

        close_friends_path = Path(f'{self.INSTAGRAM_FOLLOWER_FOLLOWING_PATH}/close_friends.json')
        with open(close_friends_path, 'r', encoding='utf-8') as f:
            return json.load(f, object_hook=InstagramProvider.fix_meta_encoding)

    async def get_share_data(self, start_date=None, end_date=None, **kwargs):
        if isinstance(start_date, str):
            start_date = parser.parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parser.parse(end_date).date()
        if not start_date:
            start_date = MINIMUM_DATE
        if not end_date:
            end_date = MAXIMUM_DATE
        all_messages = await self.fetch(start_date=start_date, end_date=end_date)
        all_messages = [message for message in all_messages if
                        message.context and message.context.get(
                            'content_type') == 'share' and message.sender != MemoryProvider.UNKNOWN]
        # sent = [message for message in all_messages if message.sender == USER]
        received = [message for message in all_messages if message.sender != USER]
        messages_by_people = defaultdict(list)
        for message in received:
            messages_by_people[message.sender].append(message)
        _people_data = get_aggregate_message_by_user(messages_by_people, max_people=7)
        return jsonify({"people": _people_data})


    @staticmethod
    def fix_mojibake(text: str) -> str:
        # Get the emojis
        try:
            return text.encode("latin1").decode("utf-8")
        except UnicodeDecodeError:
            return text  # fallback if it fails

    @staticmethod
    def fix_meta_encoding(obj):
        if isinstance(obj, str):
            try:
                return obj.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return obj
        if isinstance(obj, list):
            return [InstagramProvider.fix_meta_encoding(item) for item in obj]
        if isinstance(obj, dict):
            return {k: InstagramProvider.fix_meta_encoding(v) for k, v in obj.items()}
        return obj

    @staticmethod
    def _add_to_contexts(existing_contexts: Optional[list], new_context: dict):
        if len(existing_contexts) == 0:
            existing_contexts.append({})
        for context in existing_contexts:
            context.update(new_context)

    @staticmethod
    def parse_json(data,
                   name_from_file,
                   start_date: date = None,
                   end_date: date = None,
                   ignore_groups: bool = False,
                   sender_regexes: List[str] = None,
                   pattern=None) -> List[Message]:
        messages = []
        chat_name = name_from_file

        is_group = len(data['participants']) > 2
        if not is_group:
            chat_name = next(
                (key.get('name') for key in data['participants'] if
                 key.get('name') != InstagramProvider.PLATFORM_USERNAME),
                name_from_file
            )

        if ignore_groups and is_group:
            return []

        # Skip chat if none of the participants match the provided sender regex patterns
        if sender_regexes:
            participants = [p.get('name', '') for p in data['participants']]
            matched = False
            for participant in participants:
                if MemoryProvider._sender_matched(participant, sender_regexes):
                    matched = True
                    break
            if not matched:
                return []

        for message in data['messages']:
            _dt = datetime.fromtimestamp(message.get('timestamp_ms') / 1000.0)

            # Messages are sorted by time descending in Instagram export
            if start_date and _dt.date() < start_date:
                break
            elif end_date and _dt.date() > end_date:
                continue

            sender_name = message.get('sender_name')
            sender_name = USER if sender_name == InstagramProvider.PLATFORM_USERNAME else sender_name
            sender_name = MemoryProvider.UNKNOWN if not sender_name or sender_name.lower() == 'instagram user' else sender_name

            if sender_regexes and not InstagramProvider._sender_matched(sender_name, sender_regexes):
                continue

            text = message.get('content')
            if text and 'sent an attachment' in text:
                text = ''
            if text and (text.startswith('Say hi to') or text.endswith('Say hi to')):
                continue
            share_link = f"{message.get('share', {}).get('link', '')}"
            # share_caption = f"{message.get('share', {}).get('share_text', '')}"
            # share_text = f"{share_caption}{" " if share_link else ""}{share_link}"
            assets = message.get('photos', []) + message.get('videos', []) + message.get('audio_files', [])
            contexts = []
            for asset in assets:
                asset = asset.get('uri', '')
                if not asset.startswith('your_instagram_activity/messages/inbox/'):
                    print("Invalid asset path")
                    continue
                dump_asset_id = asset[len('your_instagram_activity/messages/inbox/'):]
                parsable_asset_id = InstagramProvider.generate_asset_id(dump_asset_id)
                asset_path = InstagramProvider.get_file_path(file_id=dump_asset_id)
                contexts.append({
                    "asset_id": parsable_asset_id,
                    "mime_type": mimetypes.guess_type(asset_path)[0],
                    "new_tab_url": f'/asset/{InstagramProvider.NAME}/{parsable_asset_id}'
                })

            media_type = MediaType.NON_TEXT if contexts else MediaType.TEXT
            text = f"{text if text else ""}{" " if text and share_link else ""}{share_link}"
            if not text and not contexts:
                continue

            if text in InstagramProvider.REGIONAL_LANGUAGE_LIKED_MESSAGE:
                text = 'Liked the message'
            if text.endswith('(edited)'):
                # TODO: Find a way to handle the original message currently both will show up in the UI
                text = text.replace('(edited)', '').strip()
                InstagramProvider._add_to_contexts(contexts, {'edited': True})

            elif text.endswith(' started an audio call'):
                InstagramProvider._add_to_contexts(contexts, {'voice_call': True})
                text = ''
            elif text == 'You missed an audio call':
                text = ''
                InstagramProvider._add_to_contexts(contexts, {
                    'voice_call': True,
                    'voice_call_status': 'Missed'
                })

            message_type = MessageType.SENT if sender_name == InstagramProvider.PLATFORM_USERNAME else MessageType.RECEIVED

            if pattern and pattern.search(text) is None:
                continue

            contexts = contexts if contexts else [None]
            for context in contexts:
                if share_link:
                    if not context:
                        context = {}
                    context['content_type'] = 'share'
                messages.append(Message(_dt.astimezone(timezone.utc).replace(tzinfo=None),
                                        message_type,
                                        text,
                                        sender=sender_name,
                                        provider=InstagramProvider.NAME,
                                        chat_name=chat_name,
                                        media_type=media_type,
                                        context=context,
                                        is_group=is_group))

        messages.reverse()
        return messages

    async def _fetch(self,
                     start_date: date,
                     end_date: date,
                     ignore_groups: bool = False,
                     exclude_system_messages: bool = True,
                     senders: List[str] = None,
                     search_regex: str = None) -> List[Message]:

        sender_regexes = [await get_regex_from_name(sender) for sender in senders] if senders else None

        pattern = re.compile(search_regex) if search_regex else None

        tasks = []
        for found in os.listdir(self.INSTAGRAM_MESSAGE_PATH):
            friend = '_'.join(found.split('_')[:-1])
            friend_path = Path(os.path.join(os.path.join(self.INSTAGRAM_MESSAGE_PATH, found), 'message_1.json'))

            if not friend_path.exists():
                continue

            if friend == found:
                friend = self.DELETED_USER

            tasks.append(
                self._read_and_parse(filepath=friend_path,
                                     name_from_file=friend,
                                     start_date=start_date,
                                     end_date=end_date,
                                     ignore_groups=ignore_groups,
                                     sender_regexes=sender_regexes,
                                     pattern=pattern))

        memories_nested = await asyncio.gather(*tasks)
        memories = [item for sublist in memories_nested for item in sublist]
        return memories

    async def _read_and_parse(self, filepath: Path, **kwargs):
        try:
            async with aiofiles.open(filepath, mode='r', encoding='utf-8') as f:
                raw = await f.read()
                data = json.loads(raw, object_hook=InstagramProvider.fix_meta_encoding)
                return self.parse_json(data, **kwargs)
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
        media_file_path = os.path.join(InstagramProvider.INSTAGRAM_MESSAGE_PATH, file_id)
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

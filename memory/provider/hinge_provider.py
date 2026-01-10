import json
import re
from datetime import datetime, date
from typing import List, Optional

import aiofiles

import configs
from profile import get_all_hinge_match_times
from provider.base_provider import MemoryProvider, Message, MediaType, MessageType


class HingeProvider(MemoryProvider):
    NAME = "Hinge"

    HINGE_PATH = 'data/hinge'
    WORKING = True

    def __init__(self):
        if not self.WORKING:
            return

    def is_working(self):
        return self.WORKING

    async def fetch(self, on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    ignore_groups: bool = False,
                    senders: List[str] = None,
                    search_regex: str = None) -> List[Message]:
        print("Starting to fetch from Hinge")
        messages = []

        if senders:
            if len(senders) != 1:
                return messages
            if senders[0].lower() != configs.USER.lower():
                return messages

        pattern = re.compile(search_regex) if search_regex else None

        matches_data = await HingeProvider._read_matches_file()

        chat_name_match_time = await get_all_hinge_match_times()
        match_time_chat_name = {v: k for k, v in chat_name_match_time.items()}
        match_count = 0
        for match in matches_data:
            match_messages = []
            match_count += 1
            chat_name = None

            for like_data in match.get('like', []):
                _dt = datetime.strptime(like_data.get('timestamp'), "%Y-%m-%d %H:%M:%S")
                likes = like_data.get('like', [])
                message = None
                if likes:
                    message = likes[0].get('comment') if len(likes) >= 1 else None
                message = message if message else 'Liked'
                match_messages.append((_dt, message))

            for match_data in match.get('match', []):
                match_time = match_data.get('timestamp')
                if match_time in match_time_chat_name:
                    chat_name = match_time_chat_name[match_time]
                _dt = datetime.strptime(match_time, "%Y-%m-%d %H:%M:%S")
                match_messages.append((_dt, 'Matched'))

            for chat_data in match.get('chats', []):
                _dt = datetime.strptime(chat_data.get('timestamp'), "%Y-%m-%d %H:%M:%S")
                match_messages.append((_dt, chat_data.get('body')))

            for row in match_messages:
                _dt, text = row

                if on_date and _dt.date() != on_date:
                    continue

                # Messages are sorted by time descending in Instagram export
                if start_date and _dt.date() < start_date:
                    continue
                elif end_date and _dt.date() > end_date:
                    continue

                if not text:
                    continue

                if pattern and pattern.search(text) is None:
                    continue

                # Hinge just provides just user's own messages
                messages.append(
                    Message(
                        _dt,
                        MessageType.SENT,
                        text,
                        sender=configs.USER,
                        provider=HingeProvider.NAME,
                        chat_name=chat_name or f'Match {match_count}',
                        media_type=MediaType.TEXT,
                        context={},
                        is_group=False  # TODO: Fix
                    )
                )

        messages.sort(key=lambda memory: memory.datetime)
        print("Done fetching from Hinge")
        return messages

    @staticmethod
    async def _read_matches_file() -> List[dict]:
        try:
            async with aiofiles.open(f'{HingeProvider.HINGE_PATH}/matches.json', 'r') as f:
                return json.loads(await f.read())
        except FileNotFoundError:
            print("Error reading matches file.")
            return []

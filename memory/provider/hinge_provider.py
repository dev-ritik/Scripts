import json
import re
import statistics
from datetime import date, timezone
from typing import List, Optional

import aiofiles
from dateutil import parser

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

    def get_allowed_exposed_functions(self) -> List[str]:
        return ['get_stats']

    def supports_home(self) -> bool:
        return self.is_working()

    async def get_stats(self, **kwargs) -> dict:
        all_data = await HingeProvider._read_matches_file()

        match_count = 0
        likes_with_message_sent_count = 0
        likes_without_message_sent_count = 0
        match_without_like_count = 0
        likes_that_matched = 0
        total_chats = 0
        match_times = []
        match_messages = []
        highest_conversation_length = 0
        likes_by_weekday_hour = [[0 for _ in range(24)] for _ in range(7)]

        for data in all_data:
            like_dts = []
            for like_data in data.get('like', []):
                _dt = parser.parse(like_data.get('timestamp'))
                if _dt:
                    like_dts.append(_dt)
                    _dt_local = _dt.replace(tzinfo=timezone.utc).astimezone()
                    weekday = _dt_local.weekday()  # Monday = 0
                    hour = _dt_local.hour  # 0-23
                    likes_by_weekday_hour[weekday][hour] += 1

                likes = like_data.get('like', [])
                for like in likes:
                    if like.get('comment', ''):
                        likes_with_message_sent_count += 1
                    else:
                        likes_without_message_sent_count += 1

            match_dt = None
            for match_data in data.get('match', []):
                match_time = match_data.get('timestamp')
                match_dt = parser.parse(match_time) if match_dt is None else match_dt
                match_count += len(match_data)

            if match_dt and like_dts:
                # Calculate all positive differences in seconds
                pos_diffs = [(match_dt - l_dt).total_seconds() for l_dt in like_dts if match_dt > l_dt]

                if pos_diffs:
                    match_times.append(min(pos_diffs))
                first_comment = next(
                    (like.get('comment') for ld in data.get('like', []) for like in ld.get('like', []) if
                     like.get('comment')), None)
                if first_comment:
                    match_messages.append(first_comment)  # Get the first comment if exists

            if data.get('match', []):
                if len(data.get('like', [])) > 0:
                    likes_that_matched += 1
                else:
                    match_without_like_count += 1

            for chat_data in data.get('chats', []):
                _dt = parser.parse(chat_data.get('timestamp'))
            total_chats += len(data.get('chats', []))
            highest_conversation_length = max(highest_conversation_length, len(data.get('chats', [])))

        # print(sorted(match_times))
        return {
            "total_likes_sent": likes_with_message_sent_count + likes_without_message_sent_count,
            "likes_with_message_sent": likes_with_message_sent_count,
            "likes_that_matched": likes_that_matched,
            "match_without_like": match_without_like_count,
            "median_match_time": int(statistics.median(match_times) if match_times else 0),
            "fastest_match_time": int(min(match_times) if match_times else 0),
            "average_chat_message_sent": 0 if match_count == 0 else total_chats / match_count,
            "total_matches": match_count,
            "like_message_that_matched": match_messages,
            "highest_conversation_length": highest_conversation_length,
            "likes_by_weekday_hour": likes_by_weekday_hour
        }


    async def fetch(self, on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    senders: List[str] = None,
                    search_regex: str = None,
                    **kwargs) -> List[Message]:
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
        like_count = 0

        for match in matches_data:
            match_messages = []
            chat_name = None
            liked = False
            matched = False

            for like_data in match.get('like', []):
                _dt = parser.parse(like_data.get('timestamp'))
                likes = like_data.get('like', [])
                message = None
                if likes:
                    message = likes[0].get('comment') if len(likes) >= 1 else None
                message = message if message else 'Liked'
                match_messages.append((_dt, message))
                liked = True

            if liked:
                like_count += 1

            for match_data in match.get('match', []):
                match_time = match_data.get('timestamp')
                if match_time in match_time_chat_name:
                    chat_name = match_time_chat_name[match_time]
                _dt = parser.parse(match_time)
                match_messages.append((_dt, 'Matched'))
                matched = True

            if matched:
                match_count += 1

            for chat_data in match.get('chats', []):
                _dt = parser.parse(chat_data.get('timestamp'))
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
                        chat_name=chat_name or f'Match #{match_count}' if matched else f'Like #{like_count}',
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

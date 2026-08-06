import re
import statistics
from datetime import date, timezone
from typing import List, Optional

from dateutil import parser

import configs
from profile import get_all_hinge_match_times
from provider.base_provider import MemoryProvider, Message, MediaType, MessageType
from provider.hinge_merge_helper import HingeParser, Conversation


class HingeProvider(MemoryProvider):
    NAME = "Hinge"

    def __init__(self):
        pass

    def get_allowed_exposed_functions(self) -> List[str]:
        return ['get_stats']

    def supports_home(self) -> bool:
        return self.is_working()

    async def get_stats(self, **kwargs) -> dict:
        old_data_parser = HingeParser()
        older_data: List[Conversation] = await old_data_parser.load(validate_raw_data=False)

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

        # Generally, if like exists before match, it means I initiated the match. If that also has a message, it means I added a like prompt.
        # If the match is at the top (possibly without any like, it means she initiated the match)
        for data in older_data:
            for like_data in data.likes:
                _dt = parser.parse(like_data.timestamp)
                if _dt:
                    _dt_local = _dt.replace(tzinfo=timezone.utc).astimezone()
                    weekday = _dt_local.weekday()  # Monday = 0
                    hour = _dt_local.hour  # 0-23
                    likes_by_weekday_hour[weekday][hour] += 1

                if like_data.comment:
                    likes_with_message_sent_count += 1
                else:
                    likes_without_message_sent_count += 1

            match_count += len(data.matches)

            if data.has_messages() and data.has_likes():
                match_dt = min([parser.parse(match_time) for match_time in data.matches])
                like_dt = max([parser.parse(like_time.timestamp) for like_time in data.likes])

                # Calculate all positive differences in seconds
                diff = (match_dt - like_dt).total_seconds()
                if diff < 0:
                    raise ValueError("Match time is before like time")

                match_times.append(diff)
                first_comment = next((like.comment for like in data.likes), None)
                if first_comment:
                    match_messages.append(first_comment)  # Get the like which got a match if exists

            if data.has_matches():
                if data.has_likes():
                    likes_that_matched += 1
                else:
                    match_without_like_count += 1

            total_chats += len(data.messages)
            highest_conversation_length = max(highest_conversation_length, len(data.messages))

        return {
            "total_likes_sent": likes_with_message_sent_count + likes_without_message_sent_count,
            "likes_with_message_sent": likes_with_message_sent_count,
            "likes_that_matched": likes_that_matched,
            "match_without_like": match_without_like_count,
            "median_match_time": int(statistics.median(match_times) if match_times else 0),
            "fastest_match_time": int(min(match_times) if match_times else 0),
            "average_chat_message_sent": 0 if match_count == 0 else int(total_chats / match_count),
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

        old_data_parser = HingeParser()
        older_data: List[Conversation] = await old_data_parser.load(validate_raw_data=False)

        chat_name_match_time = await get_all_hinge_match_times()
        match_time_chat_name = {v: k for k, v in chat_name_match_time.items()}
        match_count = 0
        like_count = 0

        for conversation in older_data:
            match_messages = []
            chat_name = None

            for like_data in conversation.likes:
                _dt = parser.parse(like_data.timestamp)
                match_messages.append((_dt, like_data.comment or 'Liked'))

            if conversation.has_likes():
                like_count += 1

            for match_time in conversation.matches:
                if match_time in match_time_chat_name:
                    chat_name = match_time_chat_name[match_time]
                _dt = parser.parse(match_time)
                match_messages.append((_dt, 'Matched'))

            if conversation.has_messages():
                match_count += 1

            for chat_data in conversation.messages:
                _dt = parser.parse(chat_data.timestamp)
                match_messages.append((_dt, chat_data.body))

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

                # Hinge just provides user's own messages
                messages.append(
                    Message(
                        _dt,
                        MessageType.SENT,
                        text,
                        sender=configs.USER,
                        provider=HingeProvider.NAME,
                        chat_name=chat_name or f'Match #{match_count}' if conversation.has_matches() else f'Like #{like_count}',
                        media_type=MediaType.TEXT,
                        context={},
                        is_group=False  # TODO: Fix
                    )
                )

        messages.sort(key=lambda memory: memory.datetime)
        print("Done fetching from Hinge")
        return messages

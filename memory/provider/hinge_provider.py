import re
from datetime import date, timezone
from typing import List

from dateutil import parser

import configs
from profile import get_all_hinge_like_times, get_all_hinge_match_ids
from provider.base_provider import MemoryProvider, Message, MediaType, MessageType
from provider.hinge_merge_helper import HingeParser, Conversation, LikeItem


class HingeProvider(MemoryProvider):
    NAME = "Hinge"

    def get_allowed_exposed_functions(self) -> List[str]:
        return ['get_stats']

    def supports_home(self) -> bool:
        return self.is_working()

    async def get_stats(self, **kwargs) -> dict:
        old_data_parser = HingeParser()
        conversations: List[Conversation] = []
        likes: List[LikeItem] = []
        conversations, likes = await old_data_parser.get_data(validate_raw_data=False)

        match_count = len(conversations)
        likes_with_message_sent_count = sum(1 for like in likes if like.comment)
        likes_without_message_sent_count = len(likes) - likes_with_message_sent_count
        total_chats = sum(len(conversation.messages) for conversation in conversations)
        highest_conversation_length = max(len(conversation.messages) for conversation in conversations)
        likes_by_weekday_hour = [[0 for _ in range(24)] for _ in range(7)]
        matched_like_times = [[0 for _ in range(24)] for _ in range(7)]
        year_today = date.today().year
        likes_by_month_year = [[0 for _ in range(12)] for _ in range(year_today + 1 - 2013)]

        for like_data in likes:
            _dt = parser.parse(like_data.timestamp)
            if _dt:
                _dt_local = _dt.replace(tzinfo=timezone.utc).astimezone()
                weekday = _dt_local.weekday()  # Monday = 0
                hour = _dt_local.hour  # 0-23
                likes_by_weekday_hour[weekday][hour] += 1
                month = _dt_local.month - 1  # 0-11
                year_index = _dt_local.year - 2013
                if 0 <= year_index < len(likes_by_month_year):
                    likes_by_month_year[year_index][month] += 1
                else:
                    raise ValueError(
                        f"Year {year_index} is out of range for likes_by_month_year {len(likes_by_month_year)}")

        return {
            "total_likes_sent": likes_with_message_sent_count + likes_without_message_sent_count,
            "likes_with_message_sent": likes_with_message_sent_count,
            "average_chat_message_sent": 0 if match_count == 0 else int(total_chats / match_count),
            "total_matches": match_count,
            "highest_conversation_length": highest_conversation_length,
            "likes_by_weekday_hour": likes_by_weekday_hour,
            "likes_by_month_year": likes_by_month_year,
            "matched_like_times": matched_like_times, # This is local to show correctly on the UI
        }

    async def _fetch(self,
                     start_date: date,
                     end_date: date,
                     ignore_groups: bool = False,
                     exclude_system_messages: bool = True,
                     senders: List[str] = None,
                     search_regex: str = None) -> List[Message]:
        messages = []

        if senders:
            if len(senders) != 1:
                return messages
            if senders[0].lower() != configs.USER.lower():
                return messages

        pattern = re.compile(search_regex) if search_regex else None

        old_data_parser = HingeParser()
        conversations, likes = await old_data_parser.get_data(validate_raw_data=False)

        chat_name_like_time = await get_all_hinge_like_times()
        like_time_chat_name = {v: k for k, v in chat_name_like_time.items()}

        chat_name_match_ids = await get_all_hinge_match_ids()
        match_id_chat_name = {v: k for k, v in chat_name_match_ids.items()}

        for conversation in conversations:
            chat_name = match_id_chat_name.get(conversation.match_id, conversation.match_id)

            for chat_data in conversation.messages:
                text = chat_data.body
                if not text:
                    continue

                _dt = parser.parse(chat_data.timestamp)
                if start_date and _dt.date() < start_date:
                    continue
                elif end_date and _dt.date() > end_date:
                    continue

                if pattern and pattern.search(text) is None:
                    continue

                messages.append(
                    Message(
                        _dt,
                        chat_data.message_type,
                        text,
                        sender=configs.USER if chat_data.message_type == MessageType.SENT else chat_name,
                        provider=HingeProvider.NAME,
                        chat_name=chat_name,
                        media_type=MediaType.TEXT,
                        context={},
                        is_group=False
                    )
                )

        for like_data in likes:
            chat_name = ''
            like_time = like_data.timestamp
            if like_time in like_time_chat_name:
                chat_name = like_time_chat_name[like_time]
            _dt = parser.parse(like_time)
            if start_date and _dt.date() < start_date:
                continue
            elif end_date and _dt.date() > end_date:
                continue

            text = 'Liked a profile'
            if like_data.is_rose or like_data.comment:
                text += ' with'
            if like_data.is_rose:
                text += ' rose'
                if like_data.comment:
                    text += ' and'
            if like_data.comment:
                text += f' comment: {like_data.comment}'
            text += '.'

            messages.append(
                Message(
                    _dt,
                    MessageType.SENT,
                    text,
                    sender=configs.USER,  # Hinge just gives own likes
                    provider=HingeProvider.NAME,
                    chat_name=chat_name,
                    media_type=MediaType.TEXT,
                    context={},
                    is_group=False
                )
            )

        return messages

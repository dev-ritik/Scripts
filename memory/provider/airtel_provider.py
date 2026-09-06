from datetime import date, timezone
from typing import List, Optional

from dateutil import parser

import configs
from profile import get_name_from_phone_number
from provider.airtel_merge_helper import AirtelParser, CallLog
from provider.base_provider import MemoryProvider, Message, MessageType, MediaType


class AirtelProvider(MemoryProvider):
    NAME = "Airtel"

    def get_allowed_exposed_functions(self) -> List[str]:
        return ['get_stats']

    def supports_home(self) -> bool:
        return self.is_working()

    async def get_stats(self, start_date, end_date) -> dict:
        if isinstance(start_date, str):
            start_date = parser.parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parser.parse(end_date).date()

        old_data_parser = AirtelParser()
        older_data: List[CallLog] = await old_data_parser.get_old_data(validate=False)

        relevant_data = [call_log for call_log in older_data if start_date <= parser.parse(call_log.datetime).date() <= end_date]

        user_calls_stats = {}
        for call_log in relevant_data:
            chat_name = await get_name_from_phone_number(call_log.number) or call_log.number
            if chat_name not in user_calls_stats:
                user_calls_stats[chat_name] = {"calls": 0, "duration": 0}
            user_calls_stats[chat_name]["calls"] += 1
            user_calls_stats[chat_name]["duration"] += call_log.duration_seconds

        return user_calls_stats

    async def fetch(self,
                    on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    ignore_groups: bool = False,
                    exclude_system_messages: bool = False,
                    senders: List[str] = None,
                    search_regex: str = None) -> List[Message]:
        print(f"Starting to fetch from Airtel {on_date=} {start_date=} {end_date=}")

        """
        Fetches all individual commit messages and timestamps from 1 year ago today
        up to the present moment, handling API pagination.
        """
        memories = []

        if senders:
            if len(senders) != 1:
                return memories
            if senders[0].lower() != configs.USER.lower():
                return memories

        if search_regex:
            return memories

        data_parser = AirtelParser()
        data: List[CallLog] = await data_parser.get_old_data(validate=False)

        for call_log in data:
            _dt = parser.parse(call_log.datetime)

            # Messages are sorted by time descending in Instagram export
            if start_date and _dt.date() < start_date:
                continue
            elif end_date and _dt.date() > end_date:
                continue

            chat_name = await get_name_from_phone_number(call_log.number) or call_log.number

            memories.append(
                Message(
                    _datetime=_dt.astimezone(timezone.utc).replace(tzinfo=None),
                    message_type=MessageType.SENT,
                    media_type=MediaType.TEXT,
                    sender=configs.USER,
                    provider=AirtelProvider.NAME,
                    chat_name=chat_name,
                    context={
                        'voice_call': True,
                        'voice_call_duration': call_log.duration_repr()
                    },
                )
            )

        memories.sort(key=lambda memory: memory.datetime)

        print("Done fetching from Airtel")
        return memories

    async def get_start_end_date(self):
        data_parser = AirtelParser()
        data: List[CallLog] = await data_parser.get_old_data(validate=False)
        dates = []
        for call_log in data:
            if _dt:= parser.parse(call_log.datetime):
                dates.append(_dt)

        if not dates:
            return None, None

        return min(dates).date(), max(dates).date()


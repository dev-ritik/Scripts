import asyncio
from collections import defaultdict
from datetime import date
from threading import Lock
from typing import List, Dict, Optional

from configs import get_available_providers
from profile import get_display_name_from_name
from provider.base_provider import MemoryProvider, Message, MediaType


class MemoryAggregator:
    _instance = None
    _lock = Lock()

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self.providers: Dict[str, MemoryProvider] = {}

        for provider in get_available_providers():
            self.providers[provider.NAME] = provider()
        self._initialized = True

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    async def aggregate(self, on_date: date, ignore_groups: bool = False) -> List[Message]:
        tasks = [
            provider.fetch(on_date=on_date, ignore_groups=ignore_groups)
            for provider in self.providers.values()
        ]
        results = await asyncio.gather(*tasks)

        events = [event for sublist in results for event in sublist if not event.is_hidden()]
        events.sort(key=lambda x: x.datetime)
        return events

    async def aggregate_dates(self, start_date: date, end_date: date, ignore_groups: bool = False,
                              providers: List[str] = None, senders=None, search=None) -> List[Message]:
        available_providers = providers or self.providers.keys()
        senders = [senders] if senders and isinstance(senders, str) else senders
        tasks = [
            self.providers.get(provider).fetch(start_date=start_date, end_date=end_date, ignore_groups=ignore_groups,
                                               senders=senders, search_regex=search) for provider in available_providers
        ]
        providers_events_list = await asyncio.gather(*tasks)

        all_events: List[Message] = []
        for events_by_provider in providers_events_list:
            all_events.extend(events_by_provider)

        all_events = [event for event in all_events if not event.is_hidden()]

        all_events.sort(key=lambda x: x.datetime)
        return all_events

    @staticmethod
    async def get_events_for_date(_date: date, ignore_groups: bool = False) -> List[Message]:
        # Initialize all providers
        aggregator = MemoryAggregator.get_instance()
        events = await aggregator.aggregate(_date, ignore_groups)
        # TODO: Remove traditional name with display name if it is in profile.json
        for event in events:
            if display_name := await get_display_name_from_name(event.sender):
                event.sender = display_name
        return events

    @staticmethod
    async def get_events_for_dates(start_date: date, end_date: date, ignore_groups: bool = False,
                                   providers: List[str] = None, senders=None, search=None) -> List[Message]:
        aggregator = MemoryAggregator.get_instance()
        events = await aggregator.aggregate_dates(start_date, end_date, ignore_groups, providers, senders, search=search)
        # TODO: Remove traditional name with display name if it is in profile.json
        for event in events:
            if display_name := await get_display_name_from_name(event.sender, use_regex=True):
                event.sender = display_name
        return events

    @staticmethod
    async def get_messages_by_sender(start_date: date,
                                     end_date: date,
                                     include_media_type: MediaType = None,
                                     ignore_media_type: MediaType = None,
                                     ignore_groups: bool = False,
                                     providers: List[str] = None,
                                     senders=None) -> Dict[str, List[Message]]:
        messages_by_sender = defaultdict(list)
        messages = await MemoryAggregator.get_events_for_dates(start_date, end_date, ignore_groups, providers, senders)
        for message in messages:
            if not message.sender:
                continue
            if message.sender == MemoryProvider.SYSTEM:
                continue
            if include_media_type and message.media_type != include_media_type:
                continue
            if ignore_media_type and message.media_type == ignore_media_type:
                continue
            messages_by_sender[message.sender].append(message)
        return messages_by_sender

    async def get_asset(self, provider: str, asset_id: str) -> Optional[List[str]]:
        if provider not in self.providers:
            return None
        return await self.providers[provider].get_asset(asset_id)

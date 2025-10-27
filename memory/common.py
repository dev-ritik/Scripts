import asyncio
import json
import re
from collections import defaultdict
from datetime import date
from threading import Lock
from typing import List, Dict, Optional

import aiofiles

import init
from provider.base_provider import MemoryProvider, Message, MediaType
from provider.diary_provider import DiaryProvider
from provider.google_photos_provider import GooglePhotosProvider
from provider.immich_provider import ImmichProvider
from provider.instagram_provider import InstagramProvider
from provider.whatsapp_provider import WhatsAppProvider

AVAILABLE_PROVIDERS = [
    WhatsAppProvider,
    InstagramProvider,
    DiaryProvider,
    ImmichProvider,
    GooglePhotosProvider
]


class MemoryAggregator:
    _instance = None
    _lock = Lock()

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self.providers: Dict[str, MemoryProvider] = {}

        for provider in AVAILABLE_PROVIDERS:
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

        events = [event for sublist in results for event in sublist]
        events.sort(key=lambda x: x.datetime)
        return events

    async def aggregate_dates(self, start_date: date, end_date: date, ignore_groups: bool = False,
                              providers: List[str] = None, sender_regex=None) -> List[Message]:
        available_providers = providers or self.providers.keys()
        senders = [sender_regex] if sender_regex else None
        tasks = [
            self.providers.get(provider).fetch(start_date=start_date, end_date=end_date, ignore_groups=ignore_groups,
                                               senders=senders) for provider in available_providers
        ]
        providers_events_list = await asyncio.gather(*tasks)

        all_events = []
        for events_by_provider in providers_events_list:
            all_events.extend(events_by_provider)

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
                                   providers: List[str] = None, sender_regex=None) -> List[Message]:
        aggregator = MemoryAggregator.get_instance()
        events = await aggregator.aggregate_dates(start_date, end_date, ignore_groups, providers, sender_regex)
        # TODO: Remove traditional name with display name if it is in profile.json
        for event in events:
            if display_name := await get_display_name_from_name(event.sender):
                event.sender = display_name
        return events

    @staticmethod
    async def get_messages_by_sender(start_date: date, end_date: date, ignore_groups: bool = False, exclude_self=True,
                                     providers: List[str] = None) -> Dict[str, List[Message]]:
        messages_by_sender = defaultdict(list)
        messages = await MemoryAggregator.get_events_for_dates(start_date, end_date, ignore_groups, providers)
        for message in messages:
            if not message.sender:
                continue
            if message.sender == MemoryProvider.SYSTEM:
                continue
            if exclude_self and message.sender == init.USER:
                continue
            if message.media_type == MediaType.NON_TEXT:
                continue
            messages_by_sender[message.sender].append(message)
        return messages_by_sender

    async def get_asset(self, provider: str, asset_id: str) -> Optional[List[str]]:
        if provider not in self.providers:
            return None
        return await self.providers[provider].get_asset(asset_id)

PROFILE_DATA = {}
NAME_TO_DISPLAY_NAME = {}
NON_IDENTIFIED_NAMES = set()


async def get_profile_json():
    global PROFILE_DATA
    if PROFILE_DATA:
        return PROFILE_DATA

    try:
        async with aiofiles.open('data/profile.json', 'r') as f:
            profile_data_list = json.loads(await f.read())
            for profile_data in profile_data_list:
                PROFILE_DATA[profile_data['display_name']] = profile_data
    except FileNotFoundError:
        pass
    return PROFILE_DATA


def is_sender_profile(profile_data, name):
    if not profile_data:
        return False
    # Return true if name regex matches name
    if not (pattern := profile_data.get('name_regex')):
        return False
    # Compile the regex pattern if it's a string, then match
    if isinstance(pattern, str):
        return bool(re.match(pattern, name))
    # If it's already a compiled pattern, use it directly
    return bool(pattern.match(name))


async def get_user_profile_from_name(name):
    return next(
        (profile_data for profile_data in (await get_profile_json()).values() if is_sender_profile(profile_data, name)),
        None)


async def get_user_dp(name):
    global NAME_TO_DISPLAY_NAME
    global NON_IDENTIFIED_NAMES

    display_name = await get_display_name_from_name(name)
    if not display_name:
        return None

    user_profile = (await get_profile_json()).get(display_name)
    return f'data/dp/{user_profile["dp"]}' if user_profile else None


async def get_display_name_from_name(name):
    global NAME_TO_DISPLAY_NAME
    global NON_IDENTIFIED_NAMES

    if name in NON_IDENTIFIED_NAMES:
        return None

    if name in NAME_TO_DISPLAY_NAME:
        return NAME_TO_DISPLAY_NAME[name]

    user_profile = await get_user_profile_from_name(name)
    if user_profile:
        NAME_TO_DISPLAY_NAME[name] = user_profile['display_name']

    return NAME_TO_DISPLAY_NAME.get(name)

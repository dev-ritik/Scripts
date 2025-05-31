import json
import re
from datetime import datetime
from typing import List, Dict

from provider.diary_provider import DiaryProvider
from provider.instagram_provider import InstagramProvider
from provider.whatsapp_provider import WhatsAppProvider


class MemoryAggregator:
    def __init__(self, providers: list):
        self.providers = {}
        for provider in providers:
            self.providers[provider.NAME] = provider()

    def aggregate(self, on_date: datetime, ignore_groups: bool = False) -> List[Dict]:
        events = []
        for provider in self.providers.values():
            events.extend(provider.fetch(on_date, ignore_groups=ignore_groups))

        events.sort(key=lambda x: x['datetime'])
        return events


AVAILABLE_PROVIDERS = [
    WhatsAppProvider,
    InstagramProvider,
    DiaryProvider,
]

def get_events_for_date(date: datetime, ignored_providers: List[str] = [], ignore_groups: bool = False) -> List[Dict]:
    # Initialize all providers
    aggregator = MemoryAggregator([allowed_provider for allowed_provider in AVAILABLE_PROVIDERS if allowed_provider.NAME not in ignored_providers])
    events = aggregator.aggregate(date, ignore_groups)
    # TODO: Remove traditional name with display name if it is in profile.json
    for event in events:
        if display_name := get_display_name_from_name(event['sender']):
            event['sender'] = display_name
    return events


PROFILE_DATA = {}
NAME_TO_DISPLAY_NAME = {}
NON_IDENTIFIED_NAMES = set()


def get_profile_json():
    global PROFILE_DATA
    if PROFILE_DATA:
        return PROFILE_DATA

    try:
        with open('data/profile.json', 'r') as f:
            profile_data_list = json.load(f)
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


def get_user_profile_from_name(name):
    return next(
        (profile_data for profile_data in get_profile_json().values() if is_sender_profile(profile_data, name)), None)


def get_user_dp(name):
    global NAME_TO_DISPLAY_NAME
    global NON_IDENTIFIED_NAMES

    display_name = get_display_name_from_name(name)
    if not display_name:
        return None

    user_profile = get_profile_json().get(display_name)
    return f'data/dp/{user_profile["dp"]}' if user_profile else None


def get_display_name_from_name(name):
    global NAME_TO_DISPLAY_NAME
    global NON_IDENTIFIED_NAMES

    if name in NON_IDENTIFIED_NAMES:
        return None

    if name in NAME_TO_DISPLAY_NAME:
        return NAME_TO_DISPLAY_NAME[name]

    user_profile = get_user_profile_from_name(name)
    if user_profile:
        NAME_TO_DISPLAY_NAME[name] = user_profile['display_name']

    return NAME_TO_DISPLAY_NAME.get(name)

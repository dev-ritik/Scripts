from datetime import datetime
from typing import List, Dict

from provider.diary_provider import DiaryProvider
from provider.instagram_provider import InstagramProvider
from provider.whatsapp_provider import WhatsAppProvider


# --- Aggregator ---

class MemoryAggregator:
    def __init__(self, providers: list):
        self.providers = {}
        for provider in providers:
            self.providers[provider.NAME] = provider()

    def aggregate(self, on_date: datetime) -> List[Dict]:
        events = []
        for provider in self.providers.values():
            events.extend(provider.fetch(on_date))

        events.sort(key=lambda x: x['datetime'])
        return events


AVAILABLE_PROVIDERS = [
    WhatsAppProvider,
    InstagramProvider,
    DiaryProvider,
]

def get_events_for_date(date: datetime, ignored_providers: List[str] = []):
    # Initialize all providers
    aggregator = MemoryAggregator([allowed_provider for allowed_provider in AVAILABLE_PROVIDERS if allowed_provider.NAME not in ignored_providers])
    return aggregator.aggregate(date)

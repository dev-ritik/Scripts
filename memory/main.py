import argparse
from datetime import datetime, timedelta
from typing import List, Dict

import dotenv

from provider.base_provider import MemoryProvider
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

# --- Main Program ---

def main(on_str: str, seek_days: int):
    try:
        on_date = datetime.strptime(on_str, "%d-%m-%Y")
    except ValueError:
        print("Date format invalid. Use dd-mm-yyyy.")
        return

    # Initialize all providers
    aggregator = MemoryAggregator(AVAILABLE_PROVIDERS)

    date_list = [on_date + timedelta(days=delta) for delta in range(-seek_days, seek_days + 1)]

    for date in date_list:
        print(f"\n=== Memories for {date.strftime('%d-%m-%Y')} ===")
        events = aggregator.aggregate(date)
        if not events:
            print("No memories found.")
        else:
            print(f"=== {events[0]['provider']} ===")
            for event in events:
                print(f"[{event['datetime']}]: {event['sender']}: {event['message']}")

    # TODO: Open a web page on local host to show the results



if __name__ == "__main__":
    dotenv.load_dotenv()

    arg_parser = argparse.ArgumentParser(description="Memory Aggregator")
    arg_parser.add_argument("--on", required=True, help="The date in dd-mm-yyyy format")
    arg_parser.add_argument("--seek-days", type=int, default=0, help="Number of days before/after to look")

    args = arg_parser.parse_args()
    main(args.on, args.seek_days)

import argparse
from datetime import datetime, timedelta
from typing import List, Dict
import dotenv
from abc import ABC, abstractmethod


# --- Base Provider ---
class MemoryProvider(ABC):
    @abstractmethod
    def fetch(self, on_date: datetime) -> List[Dict]:
        pass


# --- Providers ---

class WhatsAppProvider(MemoryProvider):
    def fetch(self, on_date: datetime) -> List[Dict]:
        # TODO: Add real WhatsApp fetching logic
        return [{"source": "WhatsApp", "time": "10:30", "content": "Hey, how are you?"}]


class InstagramProvider(MemoryProvider):
    def fetch(self, on_date: datetime) -> List[Dict]:
        # TODO: Add real Instagram fetching logic
        return [{"source": "Instagram", "time": "15:00", "content": "Loved your story!"}]


class DiaryProvider(MemoryProvider):
    def fetch(self, on_date: datetime) -> List[Dict]:
        # TODO: Add real diary fetching logic
        return [{"source": "Diary", "time": "20:00", "content": "Wrote about today's adventure."}]


class GooglePhotosProvider(MemoryProvider):
    def fetch(self, on_date: datetime) -> List[Dict]:
        # TODO: Add real Google Photos fetching logic
        return [{"source": "Google Photos", "time": "18:00", "content": "IMG_20240426.jpg"}]


# --- Aggregator ---

class MemoryAggregator:
    def __init__(self, providers: List[MemoryProvider]):
        self.providers = providers

    def aggregate(self, on_date: datetime) -> List[Dict]:
        events = []
        for provider in self.providers:
            events.extend(provider.fetch(on_date))

        # Sort chronologically
        def time_key(event):
            return datetime.strptime(event['time'], "%H:%M")

        events.sort(key=time_key)
        return events


# --- Main Program ---

def main(on_str: str, seek_days: int):
    try:
        on_date = datetime.strptime(on_str, "%d-%m-%Y")
    except ValueError:
        print("Date format invalid. Use dd-mm-yyyy.")
        return

    # Initialize all providers
    providers = [
        WhatsAppProvider(),
        InstagramProvider(),
        DiaryProvider(),
        GooglePhotosProvider()
    ]

    aggregator = MemoryAggregator(providers)

    date_list = [on_date + timedelta(days=delta) for delta in range(-seek_days, seek_days + 1)]

    for date in date_list:
        print(f"\n=== Memories for {date.strftime('%d-%m-%Y')} ===")
        events = aggregator.aggregate(date)
        if not events:
            print("No memories found.")
        else:
            for event in events:
                print(f"[{event['time']}] {event['source']}: {event['content']}")


if __name__ == "__main__":
    dotenv.load_dotenv()

    arg_parser = argparse.ArgumentParser(description="Memory Aggregator")
    arg_parser.add_argument("--on", required=True, help="The date in dd-mm-yyyy format")
    arg_parser.add_argument("--seek-days", type=int, default=0, help="Number of days before/after to look")

    args = arg_parser.parse_args()
    main(args.on, args.seek_days)

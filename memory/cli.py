import argparse
import asyncio

import init

# This should be the first line in the file. It initializes the app.
init.init()

from datetime import datetime, timedelta
from common import MemoryAggregator


async def main(on_str: str, seek_days: int):
    try:
        on_date = datetime.strptime(on_str, "%d-%m-%Y")
    except ValueError:
        print("Date format invalid. Use dd-mm-yyyy.")
        return

    events = await MemoryAggregator.get_events_for_dates(on_date - timedelta(seek_days),
                                                   on_date + timedelta(seek_days))
    if not events:
        print("No memories found.")
    else:
        events.sort(key=lambda x: x['datetime'])
        for event in events:
            print(f"[{event['datetime']}]: {event['sender']}: {event['message']}")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Memory Aggregator")
    arg_parser.add_argument("--on", required=True, help="The date in dd-mm-yyyy format")
    arg_parser.add_argument("--seek-days", type=int, default=0, help="Number of days before/after to look")

    args = arg_parser.parse_args()
    asyncio.run(main(args.on, args.seek_days))

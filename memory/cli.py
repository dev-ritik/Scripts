import argparse
from datetime import datetime, timedelta

import dotenv

from common import get_events_for_date


# --- Main Program ---

def main(on_str: str, seek_days: int):
    try:
        on_date = datetime.strptime(on_str, "%d-%m-%Y")
    except ValueError:
        print("Date format invalid. Use dd-mm-yyyy.")
        return

    date_list = [on_date + timedelta(days=delta) for delta in range(-seek_days, seek_days + 1)]

    for date in date_list:
        print(f"\n=== Memories for {date.strftime('%d-%m-%Y')} ===")
        events = get_events_for_date(date)
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

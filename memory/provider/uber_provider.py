import csv
import os
from datetime import date, datetime, timezone
from typing import List, Optional, Iterable

from provider.base_provider import MemoryProvider, MessageType, Message, MediaType
from utils import human_duration


class UberProvider(MemoryProvider):
    NAME = "Uber"
    WORKING = True
    UBER_PATH = 'data/uber'
    TRIPS_HISTORY_PATH = f'{UBER_PATH}/trips_data-0.csv'

    def __init__(self):
        super().__init__()

        if not os.path.exists(self.TRIPS_HISTORY_PATH):
            self.WORKING = False
            print("Uber folder not found")
            return

    def is_working(self):
        return self.WORKING

    @staticmethod
    def parse_ts(ts: str | None):
        if not ts:
            return None
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    @staticmethod
    def lat_lng_to_dms(lat: float, lng: float):
        lat_d, lat_m, lat_s = UberProvider.decimal_to_dms(abs(lat))
        lng_d, lng_m, lng_s = UberProvider.decimal_to_dms(abs(lng))

        lat_dir = "N" if lat >= 0 else "S"
        lng_dir = "E" if lng >= 0 else "W"

        return (
            f"{lat_d}°{lat_m}′{lat_s:.2f}″ {lat_dir}",
            f"{lng_d}°{lng_m}′{lng_s:.2f}″ {lng_dir}",
        )

    @staticmethod
    def decimal_to_dms(value: float):
        """
        Convert decimal degrees to (degrees, minutes, seconds)
        """
        degrees = int(value)
        minutes_float = abs(value - degrees) * 60
        minutes = int(minutes_float)
        seconds = (minutes_float - minutes) * 60
        return degrees, minutes, seconds

    @staticmethod
    def _parse_ts(ts: str) -> datetime:
        # Handles Z and +05:30
        return datetime.fromisoformat(ts.replace("Z", "")).astimezone(None)

    @classmethod
    def iter_csv(cls, path: str) -> Iterable[dict]:
        """
        Lazily iterate normalized Uber trip entries
        """
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                yield {
                    # identity
                    "status": row.get("status"),
                    "completed": row.get("is_completed") == "true",
                    "product": row.get("product_type_name"),
                    "airport_trip": row.get("is_airport_trip") == "true",

                    # time
                    "requested_at": cls._parse_ts(row.get("request_timestamp_local")),
                    "started_at": cls._parse_ts(row.get("begintrip_timestamp_local")) if row.get(
                        "begintrip_timestamp_local") else None,
                    "ended_at": cls._parse_ts(row.get("dropoff_timestamp_local")) if row.get(
                        "dropoff_timestamp_local") else None,

                    # location
                    "pickup_address": row.get("begintrip_address"),
                    "dropoff_address": row.get("dropoff_address"),
                    "pickup_lat": float(row["begintrip_lat"]) if row.get("begintrip_lat") else None,
                    "pickup_lng": float(row["begintrip_lng"]) if row.get("begintrip_lng") else None,
                    "drop_lat": float(row["dropoff_lat"]) if row.get("dropoff_lat") else None,
                    "drop_lng": float(row["dropoff_lng"]) if row.get("dropoff_lng") else None,
                    "city": row.get("city_name"),

                    "distance": float(row.get("trip_distance_miles")) * 1.60934,  # Convert to km
                    "duration": row.get("trip_duration_seconds"),
                    "fare": row.get("fare_amount"),
                }

    @staticmethod
    def parse_timeline_entry(entry: dict):
        """
        Returns:
            (datetime, text, coords) or (None, None, None)
        """
        # TODO: Add Cancelled trips
        if not entry.get("completed"):
            return None, None, None

        # TODO: May be add details about requesting details like a separate or running message
        dt = entry.get("started_at") or entry.get("requested_at")
        if not dt:
            return None, None, None

        # pickup = entry.get("pickup_address") or "Unknown pickup"
        # drop = entry.get("dropoff_address") or "Unknown drop"

        text = f"Uber ride from in {entry.get('product')} in {entry.get('city')} for {round(entry.get('distance'), 1)}km in {human_duration(seconds=entry.get('duration'))} for Rs {int(float(entry.get('fare')))}"

        if entry.get("airport_trip"):
            text += " (Airport trip)"

        coords = [
            (entry.get("pickup_lat"), entry.get("pickup_lng")),
            (entry.get("drop_lat"), entry.get("drop_lng")),
        ]

        return dt, text, coords

    async def fetch(
            self,
            on_date: Optional[date] = None,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            ignore_groups: bool = False,
            senders: List[str] = None,
            search_regex: str = None,
    ):
        messages = []
        if not self.WORKING:
            return messages

        if senders or search_regex:
            return messages

        print("Starting to fetch from Uber")

        for entry in self.iter_csv(self.TRIPS_HISTORY_PATH):
            parsed = UberProvider.parse_timeline_entry(entry)
            if not parsed or not parsed[0]:
                continue

            dt, text, coords = parsed
            curr_date = dt.date()

            if on_date and curr_date != on_date:
                continue
            if start_date and curr_date < start_date:
                continue
            if end_date and curr_date > end_date:
                continue

            messages.append(
                Message(
                    _datetime=dt.astimezone(timezone.utc).replace(tzinfo=None),
                    message=text,
                    message_type=MessageType.SENT,
                    provider=self.NAME,
                    media_type=MediaType.MIXED,
                    context={
                        "coordinates": coords,
                    },
                )
            )

        messages.sort(key=lambda memory: memory.datetime)
        print("Done fetching from Uber")
        return messages

    async def get_start_end_date(self):
        if not self.WORKING:
            return None, None

        start_dt = None
        end_dt = None

        for entry in self.iter_csv(self.TRIPS_HISTORY_PATH):
            parsed = UberProvider.parse_timeline_entry(entry)
            if not parsed or not parsed[0]:
                continue

            dt = parsed[0]

            if start_dt is None:
                start_dt = dt  # first valid entry

            # Assuming the csv in in increasing order of timestamp
            end_dt = dt  # last valid entry (keeps updating)

        if not start_dt or not end_dt:
            return None, None

        return start_dt.date(), end_dt.date()

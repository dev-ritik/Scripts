import json
import os
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

import aiofiles

from provider.base_provider import MemoryProvider, MessageType, Message


class GoogleMapsProvider(MemoryProvider):
    NAME = "Google Maps"
    WORKING = True
    GOOGLE_MAPS_PATH = 'data/google_maps'
    LOCATIONS_PATH = f'{GOOGLE_MAPS_PATH}/location-history.json'

    def __init__(self):
        super().__init__()

        if not os.path.exists(self.GOOGLE_MAPS_PATH):
            self.WORKING = False
            print("Google Maps folder not found")
            return

    def is_working(self):
        return self.WORKING

    @staticmethod
    def lat_lng_to_dms(lat: float, lng: float):
        lat_d, lat_m, lat_s = GoogleMapsProvider.decimal_to_dms(abs(lat))
        lng_d, lng_m, lng_s = GoogleMapsProvider.decimal_to_dms(abs(lng))

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
    def parse_iso_time(ts: str) -> datetime:
        # Handles Z and +05:30
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    @staticmethod
    def parse_geo(geo: str) -> Tuple[float, float]:
        # "geo:11.111,11.1111"
        lat, lng = geo.replace("geo:", "").split(",")
        return float(lat), float(lng)

    @staticmethod
    def parse_timeline_entry(entry) -> Optional[tuple]:
        """
        Returns (datetime, text) or None
        """

        start = GoogleMapsProvider.parse_iso_time(entry["startTime"])
        end = GoogleMapsProvider.parse_iso_time(entry["endTime"])
        duration_min = int((end - start).total_seconds() / 60)

        # -----------------------
        # VISIT
        # -----------------------
        if "visit" in entry:
            visit = entry["visit"]
            top = visit.get("topCandidate", {})
            hierarchy_level = entry.get("hierarchyLevel", 1)  # GPT: 0 is precise and 4+ is very imprecise
            lat, lng = GoogleMapsProvider.parse_geo(top["placeLocation"])
            degree_lat, degree_lng = GoogleMapsProvider.lat_lng_to_dms(lat, lng)
            place_type = top.get("semanticType", "Unknown")

            text = (
                f"{'Visited place' if hierarchy_level <= 1 else 'Was in'}\n"
                f"{place_type + ',\n' if place_type != 'Unknown' else ''}"
                f"{degree_lat}, {degree_lng}\n"
                f"for {int(duration_min)} minutes\n"
            )

            # TODO: Add running messages in UI
            return start, text

        # -----------------------
        # ACTIVITY
        # -----------------------
        if "activity" in entry:
            act = entry["activity"]
            top = act.get("topCandidate", {})

            activity_type = top.get("type", "Unknown")
            distance = act.get("distanceMeters")

            start_lat, start_lng = GoogleMapsProvider.parse_geo(act["start"])
            start_degree_lat, start_degree_lng = GoogleMapsProvider.lat_lng_to_dms(start_lat, start_lng)
            end_lat, end_lng = GoogleMapsProvider.parse_geo(act["end"])
            end_degree_lat, end_degree_lng = GoogleMapsProvider.lat_lng_to_dms(end_lat, end_lng)

            text = (
                f"Was {activity_type}\n"
                f"from {start_degree_lat},{start_degree_lng}\n"
                f"to {end_degree_lat},{end_degree_lng}\n"
                f"for {int(float(distance))} meters\n"
                f"in {int(duration_min)} minutes\n"
            )

            return start, text

        # -----------------------
        # TIMELINE PATH (RAW GPS)
        # -----------------------
        if "timelinePath" in entry:
            points = entry["timelinePath"]

            first = GoogleMapsProvider.parse_geo(points[0]["point"])
            first_degree_lat, first_degree_lng = GoogleMapsProvider.lat_lng_to_dms(first[0], first[1])
            last = GoogleMapsProvider.parse_geo(points[-1]["point"])
            last_degree_lat, last_degree_lng = GoogleMapsProvider.lat_lng_to_dms(last[0], last[1])
            # There can be 1 or more points. They probably represent a path. StartTime and EndTime may be irrelevant.
            start = start + timedelta(minutes=int(points[0]["durationMinutesOffsetFromStartTime"]))

            # TODO: Return all points and may be form a path

            text = (
                f"Movement\n"
                f"started at {first_degree_lat},{first_degree_lng}\n"
                f"ended at {last_degree_lat},{last_degree_lng}\n"
                f"in {int(points[-1]['durationMinutesOffsetFromStartTime']) - int(points[0]['durationMinutesOffsetFromStartTime'])} min"
            )

            return start, text

        if 'timelineMemory' in entry:
            # There are no coordinates here
            return None, None

        return None

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

        print("Starting to fetch from Google Maps")
        async with aiofiles.open(self.LOCATIONS_PATH, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())

        for entry in data:
            parsed = GoogleMapsProvider.parse_timeline_entry(entry)
            if not parsed or not parsed[0]:
                continue

            dt, text = parsed
            curr_date = dt.date()

            if on_date and curr_date != on_date:
                continue
            if start_date and curr_date < start_date:
                continue
            if end_date and curr_date > end_date:
                continue

            messages.append(
                Message(
                    _datetime=dt,
                    message=text,
                    message_type=MessageType.SENT,
                    provider=self.NAME,
                )
            )

        messages.sort(key=lambda memory: memory.datetime)
        print("Done fetching from Google Maps")
        return messages

    async def get_start_end_date(self):
        if not self.WORKING:
            return None, None

        async with aiofiles.open(self.LOCATIONS_PATH, "r", encoding="utf-8") as f:
            data = json.loads(await f.read())

        dates = []
        for entry in data:
            parsed = GoogleMapsProvider.parse_timeline_entry(entry)
            if parsed and parsed[0]:
                dates.append(parsed[0])

        if not dates:
            return None, None

        return min(dates).date(), max(dates).date()

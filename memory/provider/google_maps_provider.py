import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

import aiofiles

from provider.base_provider import MemoryProvider, MessageType, Message, MediaType
from utils import human_duration


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

    def get_allowed_exposed_functions(self) -> List[str]:
        return ['get_location_clustering']

    def supports_home(self) -> bool:
        return self.is_working()

    async def get_location_clustering(self, **kwargs):
        all_memories = await self.fetch(start_date=MemoryProvider.MINIMUM_DATE.date(),
                                        end_date=MemoryProvider.MAXIMUM_DATE.date(),
                                        )

        import numpy as np
        from sklearn.cluster import DBSCAN

        # 1. Sample Data: List of (latitude, longitude) coordinates
        coordinates = [
        ]

        for memory in all_memories:
            if memory.context and memory.context.get('coordinates') and len(memory.context['coordinates']) == 1:
                coordinates.extend(memory.context['coordinates'])

        # 2. Parameters
        distance_meters = 100
        EARTH_RADIUS_METERS = 6371008

        # Convert distance to radians for the Haversine formula
        eps_in_radians = distance_meters / EARTH_RADIUS_METERS
        coords_radians = np.radians(coordinates)

        # 3. Configure and Run DBSCAN
        db = DBSCAN(eps=eps_in_radians, min_samples=1, metric='haversine').fit(coords_radians)
        labels = db.labels_

        # 4. Group the original coordinates into their respective buckets
        buckets = {}
        for idx, label in enumerate(labels):
            if label not in buckets:
                buckets[label] = []
            buckets[label].append(coordinates[idx])

        # 5. Sort buckets by the number of coordinates inside them (descending order)
        sorted_buckets = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)

        # 6. Map the sorted buckets to the desired format
        output_data = []
        for index, (bucket_id, coords) in enumerate(sorted_buckets):
            # Determine the representative coordinate for this bucket (using the first point here)
            rep_lat, rep_lng = coords[0]

            # Or alternatively, you could calculate the average/mean center:
            # rep_lat = sum(c[0] for c in coords) / len(coords)
            # rep_lng = sum(c[1] for c in coords) / len(coords)

            output_data.append({
                "name": f"Location {index + 1}",
                "visits": len(coords),
                "latitude": round(rep_lat, 4),
                "longitude": round(rep_lng, 4)
            })

        # 7. Return or print the formatted list
        return output_data[:20]


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
            place_type = top.get("semanticType", "Unknown")

            text = (
                f"{'Visited place' if hierarchy_level <= 1 else 'Was in'}{' ' + place_type if place_type != 'Unknown' else ''} for {human_duration(minutes=duration_min)}"
            )

            # TODO: Add running messages in UI
            return start, text, [(lat, lng)]

        # -----------------------
        # ACTIVITY
        # -----------------------
        if "activity" in entry:
            act = entry["activity"]
            top = act.get("topCandidate", {})

            activity_type = top.get("type", "Unknown")
            distance = act.get("distanceMeters")

            start_lat, start_lng = GoogleMapsProvider.parse_geo(act["start"])
            end_lat, end_lng = GoogleMapsProvider.parse_geo(act["end"])

            text = f"Was {activity_type} for {int(float(distance))} meters in {human_duration(minutes=duration_min)}"

            return start, text, [(start_lat, start_lng), (end_lat, end_lng)]

        # -----------------------
        # TIMELINE PATH (RAW GPS)
        # -----------------------
        if "timelinePath" in entry:
            points = entry["timelinePath"]

            # StartTime and EndTime may be irrelevant.
            start = start + timedelta(minutes=int(points[0]["durationMinutesOffsetFromStartTime"]))

            text = f"Movement in {human_duration(minutes=int(points[-1]['durationMinutesOffsetFromStartTime']) - int(points[0]['durationMinutesOffsetFromStartTime']))}"

            return start, text, [GoogleMapsProvider.parse_geo(p['point']) for p in points]

        if 'timelineMemory' in entry:
            # There are no coordinates here
            return None, None, None

        return None

    async def fetch(
            self,
            on_date: Optional[date] = None,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
            senders: List[str] = None,
            search_regex: str = None,
            **kwargs
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
                        "coordinates": coords
                    }
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

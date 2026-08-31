from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from provider.base_provider import MemoryProvider, MessageType, Message, MediaType
from provider.google_maps_merge_helper import GoogleMapsParser, LocationItem
from utils import human_duration


class GoogleMapsProvider(MemoryProvider):
    NAME = "Google Maps"

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
        coordinates = []

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
    def parse_timeline_entry(entry: LocationItem) -> Optional[tuple]:
        """
        Returns (datetime, text) or None
        """

        start = GoogleMapsProvider.parse_iso_time(entry.start_time)
        end = GoogleMapsProvider.parse_iso_time(entry.end_time)
        duration_min = int((end - start).total_seconds() / 60)

        if entry.visit:
            text = f"{entry.visit} for {human_duration(minutes=duration_min)}"

            # TODO: Add running messages in UI
            return start, text, entry.get_coords_list()

        elif entry.activity:
            text = f"{entry.activity} in {human_duration(minutes=duration_min)}"
            return start, text, entry.get_coords_list()

        else:
            if not entry.timelinePath:
                raise Exception(f"No timelinePath for {entry}")
            # StartTime and EndTime may be irrelevant.
            start = start + timedelta(minutes=entry.timelinePath[0].duration_minutes_offset_from_start_time)

            text = f"Movement in {human_duration(minutes=int(entry.timelinePath[-1].duration_minutes_offset_from_start_time) - int(entry.timelinePath[0].duration_minutes_offset_from_start_time))}"

            return start, text, entry.get_coords_list()

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
        if not self.is_working():
            return messages

        if senders or search_regex:
            return messages

        print("Starting to fetch from Google Maps")
        data_parser = GoogleMapsParser()
        data: List[LocationItem] = await data_parser.get_old_data(validate=False)
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
        if not self.is_working():
            return None, None

        data_parser = GoogleMapsParser()
        data: List[LocationItem] = await data_parser.get_old_data(validate=False)

        dates = []
        for entry in data:
            parsed = GoogleMapsProvider.parse_timeline_entry(entry)
            if parsed and parsed[0]:
                dates.append(parsed[0])

        if not dates:
            return None, None

        return min(dates).date(), max(dates).date()

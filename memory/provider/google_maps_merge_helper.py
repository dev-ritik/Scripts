import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import aiofiles
from pydantic import BaseModel, ConfigDict, field_validator, model_validator, RootModel, Field

from init import DATA_DIR
from provider.merger import MergeItem
from provider.merger import Parser, Merge, MergeStrategy


@dataclass
class TimelinePathItem(MergeItem):
    lat: float
    lng: float
    duration_minutes_offset_from_start_time: int


@dataclass
class ActivityItem(MergeItem):
    distance_meters: float
    end_lat: float
    end_lng: float
    start_lat: float
    start_lng: float
    activity_type: str

    def __str__(self):
        text = f"Was {self.activity_type} for {int(float(self.distance_meters))} meters"
        return text


@dataclass
class VisitItem(MergeItem):
    hierarchy_level: int
    lat: float
    lng: float
    place_type: str

    def __str__(self):
        return f"{'Visited place' if self.hierarchy_level <= 1 else 'Was in'}{' ' + self.place_type if self.place_type != 'Unknown' else ''}"


@dataclass
class LocationItem(MergeItem):
    start_time: str
    end_time: str

    visit: Optional[VisitItem] = None
    activity: Optional[ActivityItem] = None
    timelinePath: Optional[List[TimelinePathItem]] = None

    @staticmethod
    def parse_geo(geo: str) -> Tuple[float, float]:
        # "geo:11.111,11.1111"
        lat, lng = geo.replace("geo:", "").split(",")
        return float(lat), float(lng)

    def get_unique_key(self) -> str:
        # Assuming start_time and end_time are unique enough for a location item, but if visit is present, we can use its hierarchy_level to further differentiate.
        return f"{self.start_time}_{self.end_time}_{self.visit.hierarchy_level if self.visit else 'unique'}"

    def get_coords_list(self):
        coords = []
        if self.visit:
            coords.append((self.visit.lat, self.visit.lng))
        if self.activity:
            coords.append((self.activity.start_lat, self.activity.start_lng))
            coords.append((self.activity.end_lat, self.activity.end_lng))
        if self.timelinePath:
            for path_item in self.timelinePath:
                coords.append((path_item.lat, path_item.lng))
        return coords

    def __str__(self):
        pass

    def merge(self, other: 'LocationItem') -> 'LocationItem':
        # We don't merge locations, assuming them to be complete within themselves
        if self.get_unique_key() != other.get_unique_key():
            raise ValueError("Cannot merge locations with different unique keys")
        return self


class GoogleMapsParser(Parser):
    DATA_PATH = os.path.join(DATA_DIR, 'google_maps')

    def __init__(self, path: str = None):
        if not path:
            path = self.DATA_PATH
        super().__init__(path)

    async def load_data(self):
        data = {}

        if not os.path.exists(os.path.join(self.path, 'location-history.json')):
            print("No location-history.json file found in the specified path.")
            return data

        async with aiofiles.open(os.path.join(self.path, 'location-history.json'), "r", encoding="utf-8") as f:
            data = json.loads(await f.read())
            return data

    def validate_old_data(self, old_data):
        # TODO
        pass

    def validate_incoming_data(self, raw_data):
        LocationsModel.model_validate(raw_data)

    def parse_incoming_data(self, raw_data) -> List[LocationItem]:
        location_items: List[LocationItem] = []
        for raw_location_data in raw_data:
            location_item = LocationItem(
                start_time=raw_location_data['startTime'],
                end_time=raw_location_data['endTime']
            )
            if "visit" in raw_location_data:
                visit = raw_location_data["visit"]
                top = visit["topCandidate"]
                hierarchy_level = visit["hierarchyLevel"]
                lat, lng = LocationItem.parse_geo(top["placeLocation"])
                place_type = top.get("semanticType", "Unknown")
                visit_obj: VisitItem = VisitItem(
                    hierarchy_level=hierarchy_level,
                    lat=lat,
                    lng=lng,
                    place_type=place_type,
                )
                location_item.visit = visit_obj

            elif "activity" in raw_location_data:
                act = raw_location_data["activity"]
                top = act["topCandidate"]

                activity_type = top.get("type", "Unknown")
                distance = act.get("distanceMeters")

                start_lat, start_lng = LocationItem.parse_geo(act["start"])
                end_lat, end_lng = LocationItem.parse_geo(act["end"])
                act_obj: ActivityItem = ActivityItem(
                    start_lat=start_lat,
                    start_lng=start_lng,
                    end_lat=end_lat,
                    end_lng=end_lng,
                    activity_type=activity_type,
                    distance_meters=distance
                )
                location_item.activity = act_obj


            elif "timelinePath" in raw_location_data:
                points = raw_location_data["timelinePath"]
                location_item.timelinePath = []

                for point_obj in points:
                    lat, lng = LocationItem.parse_geo(point_obj["point"])
                    location_item.timelinePath.append(TimelinePathItem(
                        lat=lat,
                        lng=lng,
                        duration_minutes_offset_from_start_time=point_obj['durationMinutesOffsetFromStartTime']
                    ))
            elif 'timelineMemory' in raw_location_data:
                # There are no coordinates here
                continue

            location_items.append(location_item)

        return location_items

    def parse_old_data(self, raw_data) -> List[MergeItem]:
        location_items: List[LocationItem] = []
        for raw_location_data in raw_data:
            location_item = LocationItem(
                start_time=raw_location_data['start_time'],
                end_time=raw_location_data['end_time']
            )

            if raw_location_data["visit"]:
                visit = VisitItem(
                    hierarchy_level=int(raw_location_data["visit"]["hierarchy_level"]),
                    lat=raw_location_data["visit"]["lat"],
                    lng=raw_location_data["visit"]["lng"],
                    place_type=raw_location_data["visit"]["place_type"],
                )
                location_item.visit = visit
            elif raw_location_data["activity"]:
                act = raw_location_data["activity"]
                location_item.activity = ActivityItem(
                    start_lat=act['start_lat'],
                    start_lng=act['start_lng'],
                    end_lat=act['end_lat'],
                    end_lng=act['end_lng'],
                    activity_type=act["activity_type"],
                    distance_meters=act["distance_meters"]
                )
            else:
                timeline_path = []
                for path_point in raw_location_data["timelinePath"]:
                    timeline_path.append(TimelinePathItem(
                        lat=path_point["lat"],
                        lng=path_point["lng"],
                        duration_minutes_offset_from_start_time=int(path_point[
                            "duration_minutes_offset_from_start_time"])
                    ))
                location_item.timelinePath = timeline_path
            location_items.append(location_item)
        return location_items


class GoogleMapsMerge(Merge):
    merge_strategy = MergeStrategy.MERGE
    parser = GoogleMapsParser

    def __init__(self, new_path: str):
        super().__init__(new_path)

    async def dump(self, data: List[LocationItem], dry_run=True) -> bool:
        file_name = f"{self.parser.DATA_PATH}/location-history{'_dry_run' if dry_run else ''}.json"
        try:
            # Convert objects to dictionaries if data elements are custom objects (e.g. dataclasses or Pydantic models)
            # If 'data' is already a list of dicts/primitives, `default=str` or custom serializer can be used.
            async with aiofiles.open(file_name, "w") as f:
                await f.write(
                    json.dumps(
                        data,
                        default=lambda o: (
                            o.__dict__ if hasattr(o, "__dict__") else str(o)
                        ),
                        indent=4,
                    )
                )
            return True
        except Exception as e:
            print(f"Error writing to matches file: {e}")
            return False


class GeoLocation(BaseModel):
    """Google's geo:lat,lng location format."""

    model_config = ConfigDict(extra="forbid")

    latitude: float
    longitude: float

    @classmethod
    def from_google(cls, value: str) -> "GeoLocation":
        if not value.startswith("geo:"):
            raise ValueError(f"Invalid geo location: {value!r}")

        try:
            lat, lon = value.removeprefix("geo:").split(",", 1)
            return cls(latitude=float(lat), longitude=float(lon))
        except (ValueError, TypeError):
            raise ValueError(f"Invalid geo location: {value!r}")

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, value: float) -> float:
        if not -90 <= value <= 90:
            raise ValueError("latitude must be between -90 and 90")
        return value

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, value: float) -> float:
        if not -180 <= value <= 180:
            raise ValueError("longitude must be between -180 and 180")
        return value


class VisitCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probability: float
    semanticType: str
    placeID: str
    placeLocation: str

    @field_validator("placeLocation")
    @classmethod
    def validate_place_location(cls, value: str) -> str:
        GeoLocation.from_google(value)
        return value


class Visit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hierarchyLevel: int
    topCandidate: VisitCandidate
    probability: float
    isTimelessVisit: Optional[bool] = None


class ActivityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    probability: float


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probability: Optional[float] = None
    end: str
    topCandidate: ActivityCandidate
    distanceMeters: float
    start: str

    @field_validator("start", "end")
    @classmethod
    def validate_location(cls, value: str) -> str:
        GeoLocation.from_google(value)
        return value

    @field_validator("distanceMeters")
    @classmethod
    def validate_distance(cls, value: float) -> float:
        if value < 0:
            raise ValueError("distanceMeters cannot be negative")
        return value


class TimeLinePath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point: str
    durationMinutesOffsetFromStartTime: int

    @field_validator("point")
    @classmethod
    def validate_location(cls, value: str) -> str:
        GeoLocation.from_google(value)
        return value

    @model_validator(mode="after")
    def validate_record(self) -> "TimeLinePath":
        if self.durationMinutesOffsetFromStartTime < 0:
            raise ValueError("durationMinutesOffsetFromStartTime cannot be negative")
        return self


class LocationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    startTime: datetime
    endTime: datetime

    visit: Visit | None = None
    activity: Activity | None = None
    timelinePath: List[TimeLinePath] | None = None
    timelineMemory: dict | None = None  # Ignored for now, as it doesn't have coordinates

    @model_validator(mode="after")
    def validate_record(self) -> "LocationModel":
        # startTime <= endTime
        if self.endTime < self.startTime:
            raise ValueError("endTime must be greater than or equal to startTime")

        # Exactly one of visit/activity
        if (self.visit is None) + (self.activity is None) + (self.timelinePath is None) + (
                self.timelineMemory is None) != 3:
            raise ValueError(
                "Exactly one of 'visit', 'activity', 'timelinePath', or 'timelineMemory' must be present"
            )

        if self.timelinePath and len(self.timelinePath) == 0:
            raise ValueError("timelinePath must have at least one entry if present")

        return self


class LocationsModel(RootModel[list[LocationModel]]):
    root: list[LocationModel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_locations(self):
        # So far, a combo of start time - end time can have duplicates but can be eliminated using visit.hierarchylevel
        keys = [(x.startTime, x.endTime, x.visit.hierarchyLevel if x.visit else 'unique') for x in self.root]

        counts = Counter(keys)
        duplicates = {key: count for key, count in counts.items() if count > 1}

        if duplicates:
            for (start_time, end_time), count in duplicates.items():
                print(
                    f"Duplicate found {count} times: "
                    f"startTime={start_time}, endTime={end_time}"
                )

            raise ValueError("Duplicate startTime + endTime combination found")

        return self

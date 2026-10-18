import json
import os
import re
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import List, Optional

import configs
from init import DATA_DIR
from provider.base_provider import MemoryProvider, MessageType, Message


class SpotifyProvider(MemoryProvider):
    NAME = "Spotify"
    DATA_PATH = os.path.join(DATA_DIR, 'spotify')

    def get_allowed_exposed_functions(self) -> List[str]:
        # TODO
        return ['']

    def supports_home(self) -> bool:
        # TODO
        return False

    pattern = re.compile(r"Streaming_History_(?:Audio|Video)_(\d{4})\.json$")

    START_REASONS = {
        "clickrow": "Selected manually",
        "playbtn": "Playback started",
        "trackdone": "Continued from previous track",
        "fwdbtn": "After skipping forward",
        "backbtn": "After going back",
        "appload": "Spotify opened",
        "remote": "Started from another device",
        "uriopen": "Opened directly",
        "clickside": "Selected from sidebar",
        "popup": "Started from a popup",
    }

    END_REASONS = {
        "trackdone": "Finished",
        "endplay": "Playback stopped",
        "fwdbtn": "Skipped forward",
        "backbtn": "Skipped backward",
        "logout": "Spotify session ended",
        "remote": "Playback changed remotely",
        "trackerror": "Playback interrupted",
        "unexpected-exit": "Playback interrupted",
        "unexpected-exit-while-paused": "App closed while paused",
    }

    @staticmethod
    def format_duration(ms):
        seconds = max(0, ms // 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @staticmethod
    def build_spotify_description(entry):
        track = entry.get("master_metadata_track_name")
        artist = entry.get("master_metadata_album_artist_name")
        album = entry.get("master_metadata_album_album_name")

        episode = entry.get("episode_name")
        show = entry.get("episode_show_name")
        audiobook = entry.get("audiobook_title")

        # Keep track details as the main focus.
        if track:
            description = f"{track}: {artist}" if artist else track
            if album:
                description += f" ({album})"
        elif episode:
            description = f"{episode}: {show}" if show else episode
        elif audiobook:
            description = audiobook
        else:
            return None

        context = []
        reason_start = entry.get("reason_start")
        reason_end = entry.get("reason_end")

        # Show manual selection because it is a useful intent signal.
        if reason_start == "clickrow":
            context.append("Selected manually")

        # Keep shuffle as a subtle, optional detail.
        if entry.get("shuffle") is True:
            context.append("Shuffle")

        # The skipped flag is useful, but older Spotify exports may
        # contain inconsistent values. Include end-reason evidence too.
        skipped = entry.get("skipped") is True or reason_end in {
            "fwdbtn",
            "backbtn",
        }

        if skipped:
            context.append("Skipped")
        elif reason_end == "trackdone":
            context.append("Finished")

        # Duration provides useful context without cluttering the title.
        duration = entry.get("ms_played")
        if duration is not None:
            context.append(f"Played {SpotifyProvider.format_duration(duration)}")

        if context:
            description += " · " + " · ".join(context)

        return description

    async def fetch(self,
                    on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    ignore_groups: bool = False,
                    exclude_system_messages: bool = False,
                    senders: List[str] = None,
                    search_regex: str = None) -> List[Message]:
        print(f"Starting to fetch from Spotify {on_date=} {start_date=} {end_date=}")
        memories = []

        if senders:
            if len(senders) != 1:
                return memories
            if senders[0].lower() != configs.USER.lower():
                return memories

        if search_regex:
            return memories

        data_dir = Path(self.DATA_PATH)
        for file_path in data_dir.glob("Streaming_History_*.json"):
            match = self.pattern.fullmatch(file_path.name)
            if not match:
                continue

            file_year = int(match.group(1))

            # Avoid opening files outside the requested year range.
            if start_date and file_year < start_date.year:
                continue
            if end_date and file_year > end_date.year:
                continue

            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            for entry in data:
                timestamp = entry.get("ts")
                if not timestamp:
                    continue

                # ts is the playback end time in UTC.
                end_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                # Derive playback start time.
                start_dt = end_dt - timedelta(
                    milliseconds=entry.get("ms_played") or 0
                )

                if start_date and start_dt.date() < start_date:
                    continue
                if end_date and start_dt.date() > end_date:
                    continue

                description = self.build_spotify_description(entry)
                if not description:
                    continue

                description = f"🎵 {description}"

                memories.append(
                    Message(
                        _datetime=start_dt.astimezone(timezone.utc).replace(tzinfo=None),
                        message_type=MessageType.SENT,
                        sender=configs.USER,
                        provider=SpotifyProvider.NAME,
                        message=description,
                    )
                )

        memories.sort(key=lambda memory: memory.datetime)

        print("Done fetching from Spotify")
        return memories

    async def get_start_end_date(self):
        data_dir = Path(self.DATA_PATH)
        pattern = re.compile(r"Streaming_History_(?:Audio|Video)_(\d{4})\.json$")

        min_dt = None
        max_dt = None

        for file_path in data_dir.glob("Streaming_History_*.json"):
            if not pattern.fullmatch(file_path.name):
                continue

            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            for entry in data:
                timestamp = entry.get("ts")
                if not timestamp:
                    continue

                end_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                start_dt = end_dt - timedelta(
                    milliseconds=entry.get("ms_played") or 0
                )

                if min_dt is None or start_dt < min_dt:
                    min_dt = start_dt

                if max_dt is None or start_dt > max_dt:
                    max_dt = start_dt

        if min_dt is None:
            return None, None

        return min_dt.date(), max_dt.date()

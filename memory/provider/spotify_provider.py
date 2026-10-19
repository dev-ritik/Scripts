import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, date, time
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from flask import jsonify

import configs
from init import DATA_DIR
from provider.base_provider import MemoryProvider, MessageType, Message


class SpotifyProvider(MemoryProvider):
    NAME = "Spotify"
    DATA_PATH = os.path.join(DATA_DIR, 'spotify')

    def get_allowed_exposed_functions(self) -> List[str]:
        return ['get_stats']

    def supports_home(self) -> bool:
        return self.is_working()

    SESSION_GAP = timedelta(minutes=30)

    @staticmethod
    def parse_timestamp(value):
        """Parse Spotify's UTC ISO timestamp into an aware datetime."""
        if not value:
            return None

        try:
            dt = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def parse_bool(value):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() == "true"

    @staticmethod
    def clean(value):
        return str(value).strip() if value else ""

    @staticmethod
    def format_datetime(value):
        return value.isoformat(timespec="seconds") if value else None

    @staticmethod
    @lru_cache(maxsize=4)
    def _load_files_cached(file_signature) -> list:
        """
        Cache parsed events using file paths, sizes, and modification times.
        A changed export automatically produces a new cache key.
        """
        events = []

        for filename, _, _ in file_signature:
            path = Path(filename)

            try:
                with path.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            if isinstance(payload, list):
                events.extend(
                    row for row in payload if isinstance(row, dict)
                )

        return events

    @classmethod
    def load_history(cls) -> list:
        HISTORY_DIR = Path(SpotifyProvider.DATA_PATH)
        if not HISTORY_DIR.exists():
            cls.WORKING = False
            raise FileNotFoundError(
                f"Spotify history directory not found: {HISTORY_DIR}"
            )

        files = sorted(HISTORY_DIR.glob("Streaming_History_Audio_*.json"))
        files += sorted(HISTORY_DIR.glob("Streaming_History_Video_*.json"))

        # Also support Spotify's older naming convention.
        files += sorted(
            p for p in HISTORY_DIR.glob("endsong_*.json")
            if p not in files
        )

        signature = tuple(
            (str(p), p.stat().st_size, p.stat().st_mtime_ns)
            for p in files
        )

        return SpotifyProvider._load_files_cached(signature)

    @staticmethod
    def normalize_event(row):
        """
        Normalize one streaming event.

        Spotify ts = playback end time.
        Playback start is estimated as end - ms_played.
        """
        end_utc = SpotifyProvider.parse_timestamp(row.get("ts"))
        if end_utc is None:
            return None

        try:
            ms_played = max(0, int(row.get("ms_played") or 0))
        except (ValueError, TypeError):
            ms_played = 0

        start_utc = end_utc - timedelta(milliseconds=ms_played)

        track = SpotifyProvider.clean(row.get("master_metadata_track_name"))
        artist = SpotifyProvider.clean(row.get("master_metadata_album_artist_name"))
        album = SpotifyProvider.clean(row.get("master_metadata_album_album_name"))

        episode = SpotifyProvider.clean(row.get("episode_name"))
        show = SpotifyProvider.clean(row.get("episode_show_name"))

        is_podcast = bool(episode or show)
        title = episode if is_podcast else track
        creator = show if is_podcast else artist

        if not title:
            return None

        return {
            "start": start_utc.astimezone(configs.LOCAL_TZ),
            "end": end_utc.astimezone(configs.LOCAL_TZ),
            "ms_played": ms_played,
            "title": title,
            "artist": creator or "Unknown",
            "album": album or "Unknown",
            "uri": SpotifyProvider.clean(
                row.get("spotify_episode_uri") if is_podcast
                else row.get("spotify_track_uri")
            ),
            "is_podcast": is_podcast,
            "skipped": SpotifyProvider.parse_bool(row.get("skipped")),
            "shuffle": SpotifyProvider.parse_bool(row.get("shuffle")),
            "offline": SpotifyProvider.parse_bool(row.get("offline")),
            "incognito": SpotifyProvider.parse_bool(row.get("incognito_mode")),
            "platform": SpotifyProvider.clean(row.get("platform")) or "Unknown",
            "country": SpotifyProvider.clean(row.get("conn_country")) or "Unknown",
            "reason_start": SpotifyProvider.clean(row.get("reason_start")) or "Unknown",
            "reason_end": SpotifyProvider.clean(row.get("reason_end")) or "Unknown",
        }

    @staticmethod
    def duration_label(ms):
        seconds = int(ms / 1000)
        hours, rem = divmod(seconds, 3600)
        minutes, _ = divmod(rem, 60)

        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    @staticmethod
    def date_bounds(start_str, end_str):
        """Return inclusive local dates from the query string."""
        if not start_str or not end_str:
            return None, None, (
                jsonify({
                    "error": "Both start_date and end_date are required."
                }),
                400,
            )

        try:
            start_date = date.fromisoformat(start_str)
            end_date = date.fromisoformat(end_str)
        except ValueError:
            return None, None, (
                jsonify({
                    "error": "Dates must use YYYY-MM-DD format."
                }),
                400,
            )

        if start_date > end_date:
            return None, None, (
                jsonify({
                    "error": "start_date must not be after end_date."
                }),
                400,
            )

        # Inclusive date range, using the existing local-time convention.
        start = datetime.combine(start_date, time.min)
        end = datetime.combine(end_date + timedelta(days=1), time.min)

        return start, end, None

    @staticmethod
    def build_insights(rows, start_date, end_date):
        # Track rankings exclude podcast episodes.
        tracks = [e for e in rows if not e["is_podcast"]]
        podcasts = [e for e in rows if e["is_podcast"]]
        weekday_hourly = Counter()

        def ranked(events, key_fn):
            grouped = {}

            for e in events:
                key = key_fn(e)
                if key not in grouped:
                    grouped[key] = {
                        "name": key,
                        "play_count": 0,
                        "ms_played": 0,
                        "skips": 0,
                        "first_play": e["start"],
                        "last_play": e["start"],
                        "uri": e["uri"],
                    }

                item = grouped[key]
                item["play_count"] += 1
                item["ms_played"] += e["ms_played"]
                item["skips"] += int(e["skipped"])
                item["first_play"] = min(item["first_play"], e["start"])
                item["last_play"] = max(item["last_play"], e["start"])

                if not item["uri"] and e["uri"]:
                    item["uri"] = e["uri"]

            result = list(grouped.values())
            result.sort(
                key=lambda x: (x["ms_played"], x["play_count"]),
                reverse=True,
            )

            for item in result:
                item["minutes"] = round(item["ms_played"] / 60000, 1)
                item["duration_label"] = SpotifyProvider.duration_label(item["ms_played"])
                item["first_play"] = SpotifyProvider.format_datetime(item["first_play"])
                item["last_play"] = SpotifyProvider.format_datetime(item["last_play"])

            return result

        top_tracks = ranked(
            tracks,
            lambda e: (e["title"], e["artist"]),
        )
        top_artists = ranked(tracks, lambda e: e["artist"])
        top_albums = ranked(
            [e for e in tracks if e["album"] != "Unknown"],
            lambda e: (e["album"], e["artist"]),
        )

        # Local date is based on estimated playback start.
        daily_ms = defaultdict(int)
        daily_tracks = Counter()
        hourly_ms = Counter()
        weekday_ms = Counter()
        monthly_ms = defaultdict(int)

        for e in rows:
            day = e["start"].date().isoformat()
            daily_ms[day] += e["ms_played"]
            daily_tracks[day] += 1
            hourly_ms[e["start"].hour] += e["ms_played"]
            weekday_ms[e["start"].weekday()] += e["ms_played"]
            monthly_ms[e["start"].strftime("%Y-%m")] += e["ms_played"]
            weekday_hourly[
                (e["start"].weekday(), e["start"].hour)
            ] += e["ms_played"]

        daily = [
            {
                "date": day,
                "minutes": round(ms / 60000, 1),
                "plays": daily_tracks[day],
            }
            for day, ms in sorted(daily_ms.items())
        ]

        monthly = [
            {"month": month, "hours": round(ms / 3600000, 2)}
            for month, ms in sorted(monthly_ms.items())
        ]

        hourly = [
            {"hour": h, "hours": round(hourly_ms[h] / 3600000, 2)}
            for h in range(24)
        ]

        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                         "Friday", "Saturday", "Sunday"]
        weekday = [
            {
                "day": weekday_names[i],
                "hours": round(weekday_ms[i] / 3600000, 2),
            }
            for i in range(7)
        ]

        # Longest streak of calendar days with any listening.
        active_dates = sorted(daily_ms)
        longest_streak = 0
        current_streak = 0
        previous = None

        for day_text in active_dates:
            day = date.fromisoformat(day_text)
            if previous is not None and day == previous + timedelta(days=1):
                current_streak += 1
            else:
                current_streak = 1

            longest_streak = max(longest_streak, current_streak)
            previous = day

        # Current streak is calculated relative to the latest date with plays.
        current_streak_value = current_streak if active_dates else 0

        # Sessions are approximated using a 30-minute gap between events.
        ordered = sorted(rows, key=lambda e: e["start"])
        sessions = []
        session = None

        for e in ordered:
            if (
                    session is None
                    or e["start"] - session["last_end"] > SpotifyProvider.SESSION_GAP
            ):
                if session:
                    sessions.append(session)

                session = {
                    "start": e["start"],
                    "last_end": e["end"],
                    "plays": 1,
                    "ms_played": e["ms_played"],
                    "artists": Counter([e["artist"]]),
                }
            else:
                session["last_end"] = max(session["last_end"], e["end"])
                session["plays"] += 1
                session["ms_played"] += e["ms_played"]
                session["artists"][e["artist"]] += 1

        if session:
            sessions.append(session)

        longest_session = max(
            sessions, key=lambda s: s["ms_played"], default=None
        )

        def session_output(s):
            return {
                "start": SpotifyProvider.format_datetime(s["start"]),
                "end": SpotifyProvider.format_datetime(s["last_end"]),
                "plays": s["plays"],
                "hours": round(s["ms_played"] / 3600000, 2),
                "top_artist": s["artists"].most_common(1)[0][0],
            }

        skip_events = [e for e in tracks if e["skipped"]]
        platform_counts = Counter(e["platform"] for e in rows)
        country_counts = Counter(e["country"] for e in rows)

        active_day = max(daily, key=lambda d: d["minutes"], default=None)

        total_ms = sum(e["ms_played"] for e in rows)
        track_ms = sum(e["ms_played"] for e in tracks)
        total_track_plays = len(tracks)

        # Return artist/song names separately from aggregate values.
        return {
            "range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "listening_hours": round(total_ms / 3600000, 2),
                "track_hours": round(track_ms / 3600000, 2),
                "total_plays": len(rows),
                "track_plays": total_track_plays,
                "podcast_plays": len(podcasts),
                "unique_tracks": len({(e["title"], e["artist"]) for e in tracks}),
                "unique_artists": len({e["artist"] for e in tracks}),
                "unique_albums": len({
                    (e["album"], e["artist"])
                    for e in tracks if e["album"] != "Unknown"
                }),
                "skipped_tracks": len(skip_events),
                "skip_rate": round(
                    100 * len(skip_events) / total_track_plays, 1
                ) if total_track_plays else 0,
                "shuffle_plays": sum(e["shuffle"] for e in rows),
                "offline_plays": sum(e["offline"] for e in rows),
                "longest_streak_days": longest_streak,
                "current_streak_days": current_streak_value,
                "active_days": len(daily_ms),
                "average_daily_minutes": round(
                    total_ms / 60000 / len(daily_ms), 1
                ) if daily_ms else 0,
                "most_active_day": active_day,
                "longest_session": session_output(longest_session)
                if longest_session else None,
                "top_track": top_tracks[0] if top_tracks else None,
                "top_artist": top_artists[0] if top_artists else None,
                "top_album": top_albums[0] if top_albums else None,
            },
            "top_tracks": top_tracks[:50],
            "top_artists": top_artists[:30],
            "top_albums": top_albums[:30],
            "most_skipped": sorted(
                skip_events,
                key=lambda e: (e["title"], e["artist"]),
            ) and ranked(skip_events, lambda e: (e["title"], e["artist"]))[:20]
                            or [],
            "daily": daily,
            "monthly": monthly,
            "hourly": hourly,
            "weekday": weekday,
            "platforms": [
                {"name": name, "plays": count}
                for name, count in platform_counts.most_common()
            ],
            "countries": [
                {"name": name, "plays": count}
                for name, count in country_counts.most_common(15)
            ],
            "longest_sessions": [
                session_output(s)
                for s in sorted(
                    sessions,
                    key=lambda s: s["ms_played"],
                    reverse=True,
                )[:10]
            ],
            "weekday_hourly": [
                {
                    "weekday": day,
                    "hour": hour,
                    "minutes": round(weekday_hourly[(day, hour)] / 60000, 1),
                }
                for day in range(7)
                for hour in range(24)
            ],
        }

    def get_stats(self, start_date=None, end_date=None, **kwargs):
        try:
            start_date, end_date, error = self.date_bounds(start_date, end_date)
            if error:
                raise error
            raw_events = self.load_history()
            normalized = []

            start_dt = datetime.combine(
                start_date, time.min, tzinfo=configs.LOCAL_TZ
            )
            end_dt = datetime.combine(
                end_date + timedelta(days=1), time.min, tzinfo=configs.LOCAL_TZ
            )

            for raw in raw_events:
                event = self.normalize_event(raw)
                if not event or event["ms_played"] <= 0:
                    continue

                # Filter by estimated local playback start.
                if start_dt <= event["start"] < end_dt:
                    normalized.append(event)

            return jsonify(self.build_insights(normalized, start_date, end_date))

        except (ValueError, KeyError) as exc:
            return jsonify({"error": str(exc)}), 400
        except FileNotFoundError as exc:
            return jsonify({"error": str(exc)}), 500
        except OSError as exc:
            return jsonify({"error": str(exc)}), 500

    pattern = re.compile(r"Streaming_History_(?:Audio|Video)_(\d{4})\.json$")

    # START_REASONS = {
    #     "clickrow": "Selected manually",
    #     "playbtn": "Playback started",
    #     "trackdone": "Continued from previous track",
    #     "fwdbtn": "After skipping forward",
    #     "backbtn": "After going back",
    #     "appload": "Spotify opened",
    #     "remote": "Started from another device",
    #     "uriopen": "Opened directly",
    #     "clickside": "Selected from sidebar",
    #     "popup": "Started from a popup",
    # }
    #
    # END_REASONS = {
    #     "trackdone": "Finished",
    #     "endplay": "Playback stopped",
    #     "fwdbtn": "Skipped forward",
    #     "backbtn": "Skipped backward",
    #     "logout": "Spotify session ended",
    #     "remote": "Playback changed remotely",
    #     "trackerror": "Playback interrupted",
    #     "unexpected-exit": "Playback interrupted",
    #     "unexpected-exit-while-paused": "App closed while paused",
    # }

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
                end_dt = self.parse_timestamp(timestamp)

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

                # TODO: Use the below code to support links
                # uri = SpotifyProvider.clean(
                #                 row.get("spotify_episode_uri") if is_podcast
                #                 else row.get("spotify_track_uri")

                #     function spotifyLink(uri) {
                #         if (!uri || !/^spotify:(track|episode):[A-Za-z0-9]+$/.test(uri)) {
                #             return null;
                #         }
                #         return "https://open.spotify.com/" +
                #             uri.replace("spotify:", "").replace(":", "/");
                #     }

                description = f"🎵 {description}"

                memories.append(
                    Message(
                        _datetime=start_dt.replace(tzinfo=None),
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
        min_dt = None
        max_dt = None

        for entry in self.load_history():
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

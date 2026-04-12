import os
import re
import subprocess
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from zoneinfo import ZoneInfo

import pillow_heif
from PIL import Image

from settings import SUPPORTED_EXTS, OVERWRITE_ORIGINAL, VIDEO_EXTENSIONS

pillow_heif.register_heif_opener()

THUMB_DIR = "/tmp/thumbnails"
os.makedirs(THUMB_DIR, exist_ok=True)

DATE_FIELD = "Date"
GPS_FIELD = "Gps"
TIMEZONE = "+05:30"


def get_real_mime_type(path):
    try:
        out = subprocess.check_output(["file", "--mime-type", "-b", path])
        return out.decode().strip()
    except:
        return None


def parse_with_tz(date_str: str, tz_name: str):
    dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    tz = ZoneInfo(tz_name)
    return dt.replace(tzinfo=tz)


def get_time_variants(date_str: str, tz_name: str):
    local_dt = parse_with_tz(date_str, tz_name)
    utc_dt = local_dt.astimezone(timezone.utc)

    # EXIF format (no timezone inside string)
    exif_local = local_dt.strftime("%Y:%m:%d %H:%M:%S")

    # Offset like +05:30
    offset = local_dt.strftime("%z")
    offset = offset[:3] + ":" + offset[3:]

    # ISO (for QuickTime keys)
    iso_local = local_dt.strftime("%Y:%m:%d %H:%M:%S") + offset

    # UTC string (for video atoms)
    utc_str = utc_dt.strftime("%Y:%m:%d %H:%M:%S")

    return exif_local, offset, iso_local, utc_str


def has_exif_date(filepath):
    return run(["exiftool", "-s3", "-DateTimeOriginal", filepath])


def get_exif_date(filepath):
    raw_date = run(["exiftool", "-s3", "-DateTimeOriginal", filepath])
    if not raw_date:
        return ""
    clean_date = re.sub(r'(.*?)(\s?[+-]\d{2}:\d{2}|Z)$', r'\1', raw_date)

    return clean_date.strip()

def has_exif_gps(filepath):
    return run(["exiftool", "-s3", "-GPSLatitude", filepath])


def dms_to_decimal(dms_str, is_lon=False):
    """
    Converts:
    - '12 deg 58' 26.98" N'
    - '13 deg 26' 1.30"'  (no direction)
    """

    match = re.match(
        r'(\d+)\s*deg\s*(\d+)\'\s*([\d.]+)"\s*([NSEW])?',
        dms_str
    )

    if not match:
        return None

    deg, minutes, seconds, direction = match.groups()

    decimal = float(deg) + float(minutes) / 60 + float(seconds) / 3600

    # Apply direction if present
    if direction:
        if direction in ['S', 'W']:
            decimal *= -1
    else:
        # Assume:
        # latitude = positive
        # longitude = positive (India use-case safe)
        pass

    return decimal


def parse_gps_position(gps_str):
    """
    Handles:
    - '12 deg 58' 26.98" N, 77 deg 42' 5.45" E'
    - '13 deg 26' 1.30", 77 deg 30' 9.95"'
    """

    parts = [p.strip() for p in gps_str.split(",")]
    if len(parts) != 2:
        return None

    lat = dms_to_decimal(parts[0])
    lon = dms_to_decimal(parts[1], is_lon=True)

    if lat is None or lon is None:
        return None

    return lat, lon


def get_exif_gps(filepath):
    gps_str = run(["exiftool", "-s3", "-GPSPosition", filepath])

    if not gps_str:
        return None

    coords = parse_gps_position(gps_str)
    if not coords:
        raise ValueError(f"Unable to parse GPSPosition: {gps_str}")

    lat, lon = coords
    return f"{lat},{lon}"


def is_processed_by_us(filepath=None, field: str = None) -> bool:
    script_tag = extract_tag(filepath)
    if not script_tag:
        return False
    if not field:
        return True
    if field.lower() not in script_tag.lower():
        return False
    return True


def get_script_name() -> str:
    return Path(__file__).name


def get_git_commit() -> str:
    return run(["git", "rev-parse", "--short", "HEAD"])


def get_current_date() -> str:
    return datetime.now().strftime("%Y:%m:%d")


def get_script_tag(fields) -> str:
    return f"UpdatedBy={get_script_name()}@{get_git_commit()};Modified={get_current_date()};Fields={fields}"


def extract_tag(filepath) -> str:
    return run(
        ["exiftool", "-s3", "-UserComment", filepath]
    )


def detect_real_file_type(filepath):
    """
    Return `file` command mime description, e.g.:
        "JPEG image data"
        "ISO Media, HEIC image"
    """
    return run(["file", "-b", filepath])


def get_metadata(path):
    script_tag = extract_tag(path)
    date_processed_by_us = script_tag and DATE_FIELD in script_tag
    gps_processed_by_us = script_tag and GPS_FIELD.lower() in script_tag.lower()

    return {
        "date": get_exif_date(path),
        "gps": get_exif_gps(path),
        "processed_date": date_processed_by_us,
        "processed_gps": gps_processed_by_us,
    }


def run(cmd):
    """Run a subprocess and return stdout as text."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Error running {cmd}: {e.stderr}")
        return None


def extract_date_from_filename(filename, expected_datetime: datetime):
    """
    Try to extract datetime from filename.
    Returns EXIF-style: 'YYYY:MM:DD HH:MM:SS'
    or None if no pattern matches.
    """

    name = Path(filename).stem

    patterns = [
        # IMG_20250110_153245
        r"(\d{4})(\d{2})(\d{2})[_\- ]?(\d{2})(\d{2})(\d{2})",
        # 2022-08-19 14-20-00
        r"(\d{4})[.\-_/ ](\d{2})[.\-_/ ](\d{2})[ _\-]?(\d{2})[.\-_:]?(\d{2})[.\-_:]?(\d{2})",
        # Screenshot from 2024-06-11 23-02-24
        r"\b(\d{4})-(\d{2})-(\d{2})[ _-](\d{2})-(\d{2})-(\d{2})\b",
        # 20240708 (date only)
        r"(\d{4})(\d{2})(\d{2})"
    ]

    for p in patterns:
        m = re.search(p, name)
        if m:
            parts = m.groups()
            try:
                if len(parts) == 6:
                    dt = datetime(
                        int(parts[0]), int(parts[1]), int(parts[2]),
                        int(parts[3]), int(parts[4]), int(parts[5])
                    )
                else:
                    if not expected_datetime:
                        raise ValueError("Expected datetime is missing")
                    dt = datetime(
                        int(parts[0]), int(parts[1]), int(parts[2]), expected_datetime.hour, expected_datetime.minute,
                        expected_datetime.second
                    )
                return dt.strftime("%Y:%m:%d %H:%M:%S")
            except Exception as e:
                print(f"Error parsing date from {filename=}: {e}")

    return None


def apply_exif_updates(filepath,
                       date: str = None,
                       gps: str = None,
                       rewrite: bool = False,
                       force: bool = False,
                       guess_date: bool = False,
                       dry_run: bool = False,
                       skip_existing=False) -> dict:
    """
    Apply EXIF updates using exiftool.
    date: "YYYY:MM:DD HH:MM:SS"
    gps: tuple (lat, lon)
    rewrite: If True, overwrite existing EXIF data even if it was written by us.
    dry_run: If True, don't modify files.
    """

    existing = get_metadata(filepath)

    # 🚫 Skip if already present
    if skip_existing:
        if date and existing.get("date"):
            date = None
        if gps and existing.get("gps"):
            gps = None

    args = []
    changes = {}

    parsed_datetime = extract_date_from_filename(filepath,
                                                 datetime.strptime(date,
                                                                   "%Y:%m:%d %H:%M:%S") if date else None) if guess_date else None
    if parsed_datetime:
        date = parsed_datetime

    mime = get_real_mime_type(filepath)
    ext = os.path.splitext(filepath)[1].lower()

    is_heic = mime in ["image/heic", "image/heif"]
    # even with this, it may not work sometimes. Example:
    # `Error: Not a valid HEIC (looks more like a JPEG) - IMG_8983.HEIC`

    if date and (not has_exif_date(filepath) or (
            rewrite and (force or is_processed_by_us(filepath=filepath, field=DATE_FIELD)))):
        exif_local, offset, iso_local, utc_str = get_time_variants(date, tz_name="Asia/Kolkata")
        if ext in VIDEO_EXTENSIONS or is_heic:
            # 🎥 VIDEO → Standard tags MUST be UTC, but Keys:CreationDate should have the offset
            if not utc_str.endswith('Z'):
                utc_str += 'Z'

            args.extend([
                # 1. Standard QuickTime (Strict UTC)
                f"-CreateDate={utc_str}",
                f"-ModifyDate={utc_str}",
                f"-TrackCreateDate={utc_str}",
                f"-MediaCreateDate={utc_str}",

                # 2. The "Keys" group (The most important for Immich)
                # Force the offset here so Immich doesn't guess
                f"-Keys:CreationDate={iso_local}",
                f"-Keys:DateTimeOriginal={iso_local}",

                # 3. The XMP/Composite tags (The likely culprit)
                # We must overwrite the 'naked' Date/Time Original
                f"-XMP:DateTimeOriginal={iso_local}",
                f"-DateTimeOriginal={iso_local}",
            ])
        else:
            # 🖼️ JPEG → EXIF + offset tags
            args.extend([
                f"-AllDates={exif_local}",
                f"-OffsetTimeOriginal={offset}",
                f"-OffsetTimeDigitized={offset}",
                f"-OffsetTime={offset}",
            ])

        changes[DATE_FIELD] = date

    if gps and (not has_exif_gps(filepath) or (
            rewrite and (force or is_processed_by_us(filepath=filepath, field=GPS_FIELD)))):
        lat, lon = gps
        if is_heic:
            args.extend([
                f"-GPSCoordinates={lat},{lon}",
                f"-Keys:GPSCoordinates={lat},{lon}",
            ])
        else:
            args.extend([
                f"-GPSLatitude={lat}",
                f"-GPSLongitude={lon}",
            ])

        changes["GPS"] = f"{lat},{lon}"

    all_keys_processed = set(changes.keys())
    if existing.get("processed_date"):
        all_keys_processed.add(DATE_FIELD)
    if existing.get("processed_gps"):
        all_keys_processed.add(GPS_FIELD)

    script_tag = get_script_tag(",".join(all_keys_processed))

    if not args or dry_run:
        print(f"[DRY RUN] {filepath} → date={date}, gps={gps}")
        return changes

    command = ["exiftool"]
    if OVERWRITE_ORIGINAL:
        command.append("-overwrite_original")
    command.append(f"-UserComment={script_tag}")
    command.extend(args + [filepath])
    run(command)
    return changes


def scan_files(targets: str):
    all_files = []
    for target_arg in targets:
        # expand glob
        files = [Path(f).resolve() for f in glob(target_arg, recursive=True) if
                 Path(f).suffix.lower().lstrip(".") in SUPPORTED_EXTS]

        if not files:
            p = Path(target_arg).expanduser().resolve()
            if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED_EXTS:
                files = [p]
            elif p.is_dir():
                files = [
                    Path(root) / fn
                    for root, dirs, filenames in os.walk(p)
                    for fn in filenames
                    if fn.lower().split(".")[-1] in SUPPORTED_EXTS
                ]
        all_files.extend(files)
    return all_files


def guess_date_from_filename(path, suggested_datetime):
    return extract_date_from_filename(path,
                                      datetime.strptime(suggested_datetime,
                                                        "%Y:%m:%d %H:%M:%S")) if suggested_datetime else None


def generate_heic_thumbnail(path):
    filename = os.path.basename(path)
    thumb_path = os.path.join(THUMB_DIR, filename + ".jpg")

    if os.path.exists(thumb_path):
        return thumb_path

    try:
        img = Image.open(path)
        img.thumbnail((320, 320))
        img.convert("RGB").save(thumb_path, "JPEG")
        return thumb_path
    except Exception:
        return None


def generate_video_thumbnail(video_path):
    filename = os.path.basename(video_path)
    thumb_path = os.path.join(THUMB_DIR, filename + ".jpg")

    if os.path.exists(thumb_path):
        return thumb_path

    base_cmd = [
        "ffmpeg",
        "-y",  # overwrite
        "-v", "error",
        "-frames:v", "1",
        "-vf", "scale=320:-1",
    ]

    attempts = [
        ["-ss", "1", "-i", video_path],  # try 1s
        ["-ss", "0", "-i", video_path],  # fallback to 0s
        ["-i", video_path],  # last resort (no seek)
    ]

    for attempt in attempts:
        cmd = ["ffmpeg"] + attempt + base_cmd[2:] + [thumb_path]

        try:
            run(cmd)

            if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                return thumb_path
        except Exception:
            pass

    print(f"Failed to generate thumbnail for {video_path}")
    return None

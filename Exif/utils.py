import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from zoneinfo import ZoneInfo

import pillow_heif
from PIL import Image

from constants import EXIF_DATE_TAGS, EXTENSION_TO_MIME, MIME_TO_EXTENSION
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


def is_valid_exif_date(value: str) -> bool:
    """Return True if value contains a parseable date/time."""
    if not value:
        return False

    value = value.strip()
    if not value:
        return False

    # Normalize EXIF dates:
    # 2025:04:06 14:42:05 -> 2025-04-06 14:42:05
    value = re.sub(
        r"^(\d{4}):(\d{2}):(\d{2})",
        r"\1-\2-\3",
        value,
    )

    # datetime.fromisoformat accepts +00:00, not Z on older Python versions.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def get_exif_date_raw(filepath):
    """Return the first valid date tag in Immich's priority order."""
    args = [
        "exiftool",
        "-json",
        *[f"-{tag}" for tag in EXIF_DATE_TAGS],
        filepath,
    ]

    output = run(args)
    if not output:
        return ""

    try:
        metadata = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return ""

    if not metadata:
        return ""

    tags = metadata[0]

    for tag in EXIF_DATE_TAGS:
        value = tags.get(tag)

        # Some metadata values may not be strings.
        if not isinstance(value, str):
            continue

        value = value.strip()
        if is_valid_exif_date(value):
            return value

    return ""


def get_exif_date(filepath):
    """Return a clean date string for display in the UI."""
    raw_date = get_exif_date_raw(filepath)
    if not raw_date:
        return ""

    # Preserve existing UI behavior: remove the timezone suffix.
    return re.sub(
        r"(?:\s*[+-]\d{2}:\d{2}|Z)$",
        "",
        raw_date,
    ).strip()


def has_exif_date(filepath):
    """Check for a valid date in the supported date tags."""
    return bool(get_exif_date_raw(filepath))

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


def clean_gps_position(gps_str):
    if not gps_str:
        return None

    # Matches integers or decimals.
    # It will find '32.000000' and '76.000000' regardless of 'N' or 'E'
    coords = re.findall(r"[-+]?\d*\.\d+|\d+", gps_str)

    if len(coords) >= 2:
        lat = float(coords[0])
        lon = float(coords[1])

        # Logic for negative values:
        # If the original string contains 'S' or 'W', the value should be negative
        if 'S' in gps_str.upper() and lat > 0:
            lat = -lat
        if 'W' in gps_str.upper() and lon > 0:
            lon = -lon

        return f"{lat}, {lon}"
    return None



def get_all_metadata_batched(file_paths):
    paths = [f.as_posix() for f in file_paths]
    if not paths:
        return []

    cmd = [
        "exiftool",
        "-j",
        "-c", "%.6f",
        *[f"-{tag}" for tag in EXIF_DATE_TAGS],
        "-GPSPosition",
        "-UserComment",
        *paths,
    ]

    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        raw_data = json.loads(output)

        results = []
        for entry in raw_data:
            user_comment = entry.get("UserComment", "")

            # Reuse the shared date-priority and validation helpers.
            raw_date = next(
                (
                    value.strip()
                    for tag in EXIF_DATE_TAGS
                    if isinstance(value := entry.get(tag), str)
                       and is_valid_exif_date(value)
                ),
                "",
            )

            # Preserve the existing UI date format.
            clean_date = re.sub(
                r"(?:\s*[+-]\d{2}:\d{2}|Z)$",
                "",
                raw_date,
            ).strip()

            gps_position = clean_gps_position(
                entry.get("GPSPosition", "")
            )

            results.append({
                "path": entry.get("SourceFile"),
                "date": clean_date,
                "gps": gps_position,
                "processed_date": (
                    DATE_FIELD in user_comment if user_comment else False
                ),
                "processed_gps": (
                    GPS_FIELD.lower() in user_comment.lower()
                    if user_comment else False
                ),
            })

        return results

    except Exception as e:
        print(f"Error: {e}")
        return []


def log_command_failure(command, result, filepath=None):
    print(f"[ERROR] Command failed for {filepath or 'unknown file'}")
    print(f"[ERROR] Exit code: {result.returncode}")
    print(f"[ERROR] Command: {shlex.join(command)}")

    if result.stdout.strip():
        print(f"[STDOUT]\n{result.stdout.strip()}")

    if result.stderr.strip():
        print(f"[STDERR]\n{result.stderr.strip()}")

def run(cmd):
    """Run a subprocess and return stdout as text."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            log_command_failure(cmd, result)
            return result.stdout.strip() or None

        return result.stdout.strip()
    except Exception as e:
        print(f"[ERROR] Exception running command: {shlex.join(cmd)}")
        print(f"[ERROR] {type(e).__name__}: {e}")
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


def get_file_type_mismatch(filepath):
    """Return (actual_mime, expected_mimes) if the extension mismatches."""
    actual_mime = get_real_mime_type(filepath)
    ext = Path(filepath).suffix.lower()
    expected_mimes = EXTENSION_TO_MIME.get(ext)

    if actual_mime and expected_mimes and actual_mime not in expected_mimes:
        return actual_mime, expected_mimes

    return None


def is_exiftool_file_type_error(stderr):
    """Recognize ExifTool errors caused by an extension/content mismatch."""
    error = (stderr or "").lower()
    return "not a valid" in error and "looks more like" in error


def run_exiftool_with_type_retry(command, filepath, force=False):
    """
    Run ExifTool normally. If forced and it reports a format mismatch,
    retry with a temporary filename using the detected file type's extension.

    The original filename is restored in all cases.
    """
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode == 0:
        return result

    log_command_failure(command, result, filepath)

    if not force or not is_exiftool_file_type_error(result.stderr):
        print(f"ExifTool failed for {filepath}:\n{result.stderr.strip()}")
        return result

    actual_mime = get_real_mime_type(filepath)
    correct_ext = MIME_TO_EXTENSION.get(actual_mime)

    if not correct_ext:
        print(
            f"[WARN] Cannot retry {filepath}: "
            f"no known extension for detected MIME type {actual_mime!r}"
        )
        print(result.stderr.strip())
        return result

    original = Path(filepath)
    # Keep the original name as a prefix, but end with the correct extension.
    temporary = original.with_name(
        f"{original.name}.exiftool-temp{correct_ext}"
    )

    if temporary.exists():
        print(f"[WARN] Temporary path already exists; refusing to overwrite: {temporary}")
        return result

    print(
        f"[WARN] ExifTool reported a file-type mismatch for {filepath}. "
        f"Retrying temporarily as {temporary.name}"
    )

    try:
        os.replace(original, temporary)

        retry_command = [
            str(temporary) if arg == str(original) else arg
            for arg in command
        ]

        retry_result = subprocess.run(
            retry_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if retry_result.returncode != 0:
            log_command_failure(retry_command, retry_result, filepath)
        else:
            print(f"[INFO] Metadata update succeeded for {filepath}")

        return retry_result

    except Exception as exc:
        print(f"[ERROR] Could not retry ExifTool for {filepath}: {exc}")
        raise

    finally:
        # Restore the original filename regardless of retry success or failure.
        if temporary.exists():
            os.replace(temporary, original)


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

    mismatch = get_file_type_mismatch(filepath)
    if mismatch:
        actual_mime, expected_mimes = mismatch
        print(
            f"[WARN] File extension/type mismatch: {filepath} "
            f"(extension={ext}, detected_mime={actual_mime}, "
            f"expected_mime={', '.join(sorted(expected_mimes))})"
        )

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
                f"-GPSLatitude={lat}",
                f"-GPSLongitude={lon}",
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

    result = run_exiftool_with_type_retry(
        command,
        filepath,
        force=force,
    )

    if result.returncode != 0:
        print(f"[ERROR] Metadata update failed for {filepath}")
        return {}

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

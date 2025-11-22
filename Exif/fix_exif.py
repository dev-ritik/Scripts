#!/usr/bin/env python3
"""
fix_exif.py

Recursively updates EXIF metadata on image/video files:

- Adds DateTimeOriginal (AllDates)
- Adds GPSLatitude / GPSLongitude
- Converts mislabeled *.heic files that are actually JPEG → *.jpg
- Skips files that already contain both fields
- Shows progress bar and logs changes
- Supports dry-run mode
- Can process a single file instead of a directory

Requires:
    exiftool
    python >= 3.6
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from glob import glob
from pathlib import Path

from tqdm import tqdm

# ------------------------------------------
# Supported extensions
# ------------------------------------------
SUPPORTED_EXTS = {
    "jpg", "jpeg", "png",
    "heic", "mp4", "mov", "avi", "mkv", "webp", "gif"
}

OVERWRITE_ORIGINAL = True  # Exiftool will overwrite original file


# ------------------------------------------
# Helpers
# ------------------------------------------
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

def is_processed_by_us(filepath=None, field: str = None) -> bool:
    script_tag = extract_tag(filepath)
    if not script_tag:
        return False
    if not field:
        return True
    if field not in script_tag:
        return False
    return True


def run(cmd):
    """Run a subprocess and return stdout as text."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return result.stdout.strip()


def detect_real_file_type(filepath):
    """
    Return `file` command mime description, e.g.:
        "JPEG image data"
        "ISO Media, HEIC image"
    """
    return run(["file", "-b", filepath])


def has_exif_date(filepath):
    return run(["exiftool", "-s3", "-DateTimeOriginal", filepath])


def has_exif_gps(filepath):
    return run(["exiftool", "-s3", "-GPSLatitude", filepath])


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
        # 20240708   (date only)
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
                    dt = datetime(
                        int(parts[0]), int(parts[1]), int(parts[2]), expected_datetime.hour, expected_datetime.minute,
                        expected_datetime.second
                    )
                return dt.strftime("%Y:%m:%d %H:%M:%S")
            except Exception as e:
                print(f"Error parsing date from {filename=}: {e}")

    return None


def apply_exif_updates(filepath, date: str = None, gps: str = None, rewrite: bool = False, guess_date: bool = False,
                       dry_run: bool = False) -> dict:
    """
    Apply EXIF updates using exiftool.
    date: "YYYY:MM:DD HH:MM:SS"
    gps: tuple (lat, lon)
    rewrite: If True, overwrite existing EXIF data even if it was written by us.
    dry_run: If True, don't actually modify files.
    """
    args = []
    changes = {}

    parsed_datetime = extract_date_from_filename(filepath,
                                                 datetime.strptime(date, "%Y:%m:%d %H:%M:%S")) if guess_date else None
    if parsed_datetime:
        date = parsed_datetime

    # print(f"has_exif_date = {has_exif_date(filepath)}, has_exif_gps= {has_exif_gps(filepath)}")
    # print(f"is_processed_by_us(filepath={filepath}, field='gps') = {is_processed_by_us(filepath=filepath, field='gps')}")

    if date and (not has_exif_date(filepath) or (rewrite and is_processed_by_us(filepath=filepath, field="date"))):
        args.append(f"-AllDates={date}")
        changes["Date"] = date

    # if gps and (not has_exif_gps(filepath) or (rewrite and is_processed_by_us(filepath=filepath, field="gps"))):
    if gps:
        lat, lon = gps
        args.append(f"-GPSLatitude={lat}")
        args.append(f"-GPSLongitude={lon}")
        changes["GPS"] = f"{lat},{lon}"

    script_tag = get_script_tag(",".join(changes.keys()))
    # print(f"script_tag = {script_tag}")

    if not args or dry_run:
        return changes

    command = ["exiftool"]
    if OVERWRITE_ORIGINAL:
        command.append("-overwrite_original")
    command.append(f"-UserComment={script_tag}")
    command.extend(args + [filepath])
    subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return changes


def convert_mislabeled_heic(filepath, dry_run=False):
    """
    If a .heic file is actually JPEG data, rename .HEIC → .jpg
    Return new filepath (or the same one if unchanged).
    """
    filepath = Path(filepath)

    if filepath.suffix.lower() != ".heic":
        return filepath

    description = detect_real_file_type(str(filepath))
    if not description.startswith("JPEG"):
        return filepath  # It's truly HEIC

    # Rename to .jpg safely
    new_path = filepath.with_suffix(".jpg")
    if not dry_run:
        filepath.rename(new_path)
    filepath.rename(new_path)
    return new_path


# ------------------------------------------
# Main
# ------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Fix EXIF metadata and HEIC mislabeled files"
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="One or more files, directories, or glob patterns to process"
    )
    parser.add_argument(
        "--date",
        help='Default date to set, e.g. "2024:01:31 12:30:00"'
    )
    parser.add_argument(
        "--gps",
        help='Default GPS, format "lat,lon"'
    )
    parser.add_argument(
        "--rewrite",
        action="store_true",
        help="Rewrite Exif data even if already present. This will only do it if the last update was by us"
    )
    parser.add_argument(
        "--guess-date",
        action="store_true",
        help="Try to extract date from filename"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files"
    )
    args = parser.parse_args()

    if not args.date and not args.gps:
        print("You must provide --date and/or --gps")
        sys.exit(1)

    gps_tuple = None
    if args.gps:
        parts = args.gps.split(",")
        if len(parts) != 2:
            print("GPS must be in format: lat,lon")
            sys.exit(1)
        gps_tuple = (parts[0].strip(), parts[1].strip())

    all_files = []
    for target_arg in args.targets:
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

    if not all_files:
        print(f"No supported media files found in '{args.targets}'.")
        return

    print(
        f"📸 Found {len(all_files)} media file(s) in '{args.targets}'. Running in {args.dry_run and 'dry-run' or 'normal'} mode")

    # Process with a progress bar
    for filepath in tqdm(all_files, unit="file", ncols=90):
        path = filepath

        # 1) Convert mislabeled HEIC
        new_path = convert_mislabeled_heic(str(path), dry_run=args.dry_run)
        if new_path != path:
            print(f"\n→ Renamed mislabeled HEIC to JPG: {new_path}")
            path = new_path  # Continue with new path

        # 2) Apply EXIF updates
        changes = apply_exif_updates(
            str(path),
            date=args.date,
            gps=gps_tuple,
            rewrite=args.rewrite,
            guess_date=args.guess_date,
            dry_run=args.dry_run
        )

        # 3) Log what changed
        if len(changes) == 2:
            print(f"\n✅ Updated {changes} for: {path}")
        elif "Date" in changes:
            print(f"\n📅 Updated {changes} for: {path}")
        elif "GPS" in changes:
            print(f"\n📍 Updated {changes} for: {path}")
        # else:
        #     print(f"No changes for: {path}")

    print("\n🎉 Done.")


if __name__ == "__main__":
    main()

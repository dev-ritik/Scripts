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
import sys
from pathlib import Path

from tqdm import tqdm

from utils import detect_real_file_type, apply_exif_updates, scan_files


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
        "--force",
        action="store_true",
        help="Rewrite Exif data even if already present. Use together with --rewrite"
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

    all_files = scan_files(args.targets)

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
            force=args.force,
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

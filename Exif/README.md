# Fix EXIF Metadata Script

This script recursively updates EXIF metadata for images and videos in a directory.
It can:
Bash version (`run.sh`):
- Add or fix **photo/video creation date** (`DateTimeOriginal` / `AllDates`)
- Add or fix **GPS location** (`GPSLatitude` / `GPSLongitude`)
- Detect mislabeled **HEIC files that are actually JPEGs** and convert them to `.jpg`
- Skip files that already have both date and GPS EXIF data
- Show a **progress indicator** and **log changes** to stdout
- Work for **images and common video formats**

Python version [PREFERRED] (`fix_exif.py`):
- Add or fix **photo/video creation date** (`DateTimeOriginal` / `AllDates`)
- Add or fix **GPS location** (`GPSLatitude` / `GPSLongitude`)
- Detect mislabeled **HEIC files that are actually JPEGs** and convert them to `.jpg`
- Skip files that already have both date and GPS EXIF data
- Show a **progress indicator** and **log changes** to stdout
- Work for **images and common video formats**
- Support for **multiple directories** and `*` paths
- Intelligent date detection based on filename
- Save edit details in exif metadata
---

## Supported file formats

- **Images:** `jpg`, `jpeg`, `png`, `heic`
- **Videos:** `mp4`, `mov`, `avi`, `mkv`

---

## Prerequisites

- `bash` (Linux/macOS/WSL)
- [`exiftool`](https://exiftool.org/)
- `file` command (Linux/macOS)
- `find` command (Linux/macOS)

---

## Usage

```bash
# Bash
chmod +x run.sh
./run.sh /path/to/media --date "YYYY:MM:DD HH:MM:SS" --gps "lat,lon"
```

```Bash
python fix_exif.py path --date "2024:10:13 12:00:00" --gps "28.61405259399206, 77.2312459210617" --rewrite --guess-date --dry-run
```

```
usage: fix_exif.py [-h] [--date DATE] [--gps GPS] [--rewrite] [--guess-date] [--dry-run] targets [targets ...]

Fix EXIF metadata and HEIC mislabeled files

positional arguments:
  targets       One or more files, directories, or glob patterns to process

options:
  -h, --help    show this help message and exit
  --date DATE   Default date to set, e.g. "2024:01:31 12:30:00"
  --gps GPS     Default GPS, format "lat,lon"
  --rewrite     Rewrite Exif data even if already present. This will only do it if the last update was by us
  --guess-date  Try to extract date from filename
  --dry-run     Show what would change without modifying files
```
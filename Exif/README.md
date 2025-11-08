# Fix EXIF Metadata Script

This script recursively updates EXIF metadata for images and videos in a directory.
It can:

- Add or fix **photo/video creation date** (`DateTimeOriginal` / `AllDates`)
- Add or fix **GPS location** (`GPSLatitude` / `GPSLongitude`)
- Detect mislabeled **HEIC files that are actually JPEGs** and convert them to `.jpg`
- Skip files that already have both date and GPS EXIF data
- Show a **progress indicator** and **log changes** to stdout
- Work for **images and common video formats**

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
chmod +x fix_exif_metadata.sh
./fix_exif_metadata.sh /path/to/media --date "YYYY:MM:DD HH:MM:SS" --gps "lat,lon"

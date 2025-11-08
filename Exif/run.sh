#!/usr/bin/env bash
#
# fix_exif_metadata.sh
# Recursively updates EXIF date and GPS data for images/videos.
# Converts mislabeled HEIC→JPG if needed.
# Skips files that already contain both DateTimeOriginal and GPSLatitude.
# Shows progress and logs operations to stdout.

set -euo pipefail

# === Default values ===
TARGET_DIR="."
DEFAULT_DATE=""
DEFAULT_GPS=""

# === Supported extensions ===
SUPPORTED_EXTS=("jpg" "jpeg" "png" "heic" "mp4" "mov" "avi" "mkv")

# === Parse arguments ===
while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      DEFAULT_DATE="$2"; shift 2 ;;
    --gps)
      DEFAULT_GPS="$2"; shift 2 ;;
    -*)
      echo "Unknown option: $1"; exit 1 ;;
    *)
      TARGET_DIR="$1"; shift ;;
  esac
done

if [[ -z "$DEFAULT_DATE" && -z "$DEFAULT_GPS" ]]; then
  echo "Usage: $0 /path/to/media [--date \"YYYY:MM:DD HH:MM:SS\"] [--gps \"lat,lon\"]"
  exit 1
fi

# === Check dependencies ===
for cmd in exiftool file find; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "❌ $cmd not found. Install it first."; exit 1; }
done

# === Build find command safely ===
FIND_CMD=(find "$TARGET_DIR" -type f \( )
for ext in "${SUPPORTED_EXTS[@]}"; do
  FIND_CMD+=(-iname "*.${ext}" -o)
done
unset 'FIND_CMD[${#FIND_CMD[@]}-1]'  # remove last -o
FIND_CMD+=(\))

# === Collect files ===
mapfile -t FILES < <("${FIND_CMD[@]}" 2>/dev/null)

TOTAL=${#FILES[@]}
if (( TOTAL == 0 )); then
  echo "No supported media files found in '$TARGET_DIR'."
  exit 0
fi

echo "📸 Found $TOTAL media files in '$TARGET_DIR'"
echo

# === Processing Loop ===
i=0
for f in "${FILES[@]}"; do
    echo
  i=$(expr $i + 1)
  percent=$((i * 100 / TOTAL))
  printf "\r[%3d%%] %s" "$percent" "$(basename "$f")"

  # Step 1: Detect mislabeled HEICs that are actually JPEGs
  if [[ "${f,,}" == *.heic ]]; then
    mime=$(file -b "$f")
    if [[ $mime == JPEG* ]]; then
      new="${f%.[Hh][Ee][Ii][Cc]}.jpg"
      mv "$f" "$new"
      echo -e "\n→ Renamed mislabeled HEIC to JPG: $new"
      f="$new"
    fi
  fi

  # Step 2: Check for existing EXIF data
  has_date=$(exiftool -s3 -DateTimeOriginal "$f" 2>/dev/null || true)
  has_gps=$(exiftool -s3 -GPSLatitude "$f" 2>/dev/null || true)

  # Step 3: Determine what needs to be added
  args=()
  changes=()  # track which fields are being updated

  # Add date if missing
  if [[ -z "$has_date" && -n "$DEFAULT_DATE" ]]; then
    args+=(-AllDates="$DEFAULT_DATE")
    changes+=("Date")
  fi

  # Add GPS if missing
  if [[ -z "$has_gps" && -n "$DEFAULT_GPS" ]]; then
    IFS=',' read -r LAT LON <<<"$DEFAULT_GPS"
    args+=(-GPSLatitude="$LAT" -GPSLongitude="$LON")
    changes+=("GPS")
  fi

  # Apply EXIF changes if needed
  if (( ${#args[@]} )); then
    exiftool -overwrite_original "${args[@]}" "$f" >/dev/null

    # Logging details
    if (( ${#changes[@]} == 2 )); then
      echo -e "\n✅ Updated Date + GPS for: $f"
    elif [[ " ${changes[*]} " == *"Date"* ]]; then
      echo -e "\n📅 Updated Date for: $f"
    elif [[ " ${changes[*]} " == *"GPS"* ]]; then
      echo -e "\n📍 Updated GPS for: $f"
    fi
  fi

done

echo -e "\n🎉 Done. Processed $TOTAL files total."

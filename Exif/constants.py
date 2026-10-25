# Src: Immich order: https://github.com/immich-app/immich/blob/main/server/src/services/metadata.service.ts
EXIF_DATE_TAGS = [
    "SubSecDateTimeOriginal",
    "SubSecCreateDate",
    "DateTimeOriginal",
    "CreationDate",
    "CreateDate",
    "MediaCreateDate",
    "DateTimeCreated",
    "GPSDateTime",
    "DateTimeUTC",
    "SonyDateTime2",
    "SourceImageCreateTime",
]

# Known MIME types and their canonical extensions.
MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/gif": ".gif",
    "image/tiff": ".tif",
    "image/avif": ".avif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
    "video/webm": ".webm",
}

EXTENSION_TO_MIME = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".png": {"image/png"},
    ".heic": {"image/heic", "image/heif"},
    ".heif": {"image/heic", "image/heif"},
    ".gif": {"image/gif"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
    ".avif": {"image/avif"},
    ".mp4": {"video/mp4"},
    ".mov": {"video/quicktime", "video/mp4"},
    ".avi": {"video/x-msvideo"},
    ".mkv": {"video/x-matroska"},
    ".webm": {"video/webm"},
}

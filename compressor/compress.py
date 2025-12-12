import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from glob import glob
from pathlib import Path

from tqdm import tqdm

# ============================================================
# COMPRESSION PRESETS
# ============================================================

MODES = {
    "low": {
        "image": {
            "jpg_q": "5",
            "png_level": "3",
            "heic_q": "20",
            "webp_q": "20"
        },
        "audio": {
            "bitrate": "192k",
            "opus_bitrate": "32k"
        },
        "video": {"crf": "18", "audio_bitrate": "160k"},
        "pdf": "/screen"
    },
    "medium": {
        "image": {
            "jpg_q": "10",
            "png_level": "6",
            "heic_q": "28",
            "webp_q": "35"
        },
        "audio": {
            "bitrate": "128k",
            "opus_bitrate": "48k"
        },
        "video": {"crf": "24", "audio_bitrate": "128k"},
        "pdf": "/ebook"
    },
    "high": {
        "image": {
            "jpg_q": "15",
            "png_level": "9",
            "heic_q": "34",
            "webp_q": "50"
        },
        "audio": {
            "bitrate": "96k",
            "opus_bitrate": "64k"
        },
        "video": {"crf": "28", "audio_bitrate": "64k"},
        "pdf": "/printer"
    },
    "extreme": {
        "image": {
            "jpg_q": "20",
            "png_level": "12",
            "heic_q": "40",
            "webp_q": "70"
        },
        "audio": {
            "bitrate": "64k",
            "opus_bitrate": "128k"
        },
        "video": {"crf": "35", "audio_bitrate": "48k"},
        "pdf": "/prepress"
    }
}


def ffmpeg_supports_heic():
    try:
        enc = subprocess.check_output(["ffmpeg", "-encoders"], stderr=subprocess.STDOUT).decode()
        mux = subprocess.check_output(["ffmpeg", "-muxers"], stderr=subprocess.STDOUT).decode()
        return ("libx265" in enc or "hevc" in enc) and ("heic" in mux or "heif" in mux)
    except:
        return False


HEIC_SUPPORTED = ffmpeg_supports_heic()


# ============================================================
# OUTPUT PATH HANDLER
# ============================================================

def get_output_path(original_path, new_ext=None):
    p = Path(original_path)
    suffix = f".compressed.{new_ext or p.suffix.lstrip('.')}"
    return str(p.with_suffix(suffix))


# ============================================================
# COMPRESSION HELPERS
# ============================================================

def run_cmd(cmd):
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def compress_image(path, mode, output) -> list:
    preset = MODES[mode]["image"]
    ext = Path(path).suffix.lower().lstrip(".")

    if ext in ["jpg", "jpeg"]:
        return ["ffmpeg", "-y", "-i", path, "-qscale:v", preset["jpg_q"], output]
    elif ext == "png":
        return ["ffmpeg", "-y", "-i", path, "-compression_level", preset["png_level"], output]
    elif ext == "webp":
        return ["ffmpeg", "-y", "-i", path, "-qscale:v", preset["webp_q"], output]
    elif ext in ["heic", "heif"]:
        if not HEIC_SUPPORTED:
            print(f"[WARN] FFmpeg cannot encode HEIC")
            return []
        else:
            return [
                "ffmpeg", "-y",
                "-i", path,
                "-f", "heic",  # REQUIRED
                "-c:v", "libx265",  # HEVC encoder
                "-tag:v", "hvc1",  # iOS/macOS compat
                "-qscale:v", str(preset["heic_q"]),
                output
            ]
    else:
        print(f"Unsupported image format: {ext}")
        return []


def compress_audio(path, mode, output) -> list:
    preset = MODES[mode]["audio"]
    ext = Path(path).suffix.lower().lstrip(".")

    if ext == "opus":
        return [
            "ffmpeg", "-y", "-i", path,
            "-c:a", "libopus",
            "-b:a", preset["opus_bitrate"],
            output
        ]
    else:
        return [
            "ffmpeg", "-y", "-i", path,
            "-b:a", preset["bitrate"],
            output
        ]


def compress_video(path, mode, output) -> list:
    preset = MODES[mode]["video"]

    return [
        "ffmpeg", "-y", "-i", path,
        "-vcodec", "libx264",
        "-crf", str(preset["crf"]),
        "-preset", "medium",
        "-acodec", "aac",
        "-b:a", preset["audio_bitrate"],
        output
    ]


def compress_pdf(path, mode, output) -> list:
    preset = MODES[mode]["pdf"]

    return [
        "gs", "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={preset}",
        "-dNOPAUSE", "-dQUIET", "-dBATCH",
        f"-sOutputFile={output}",
        path
    ]


# ============================================================
# MAIN DISPATCHER
# ============================================================

def compress_file(path, mode, replace: bool):
    ext = Path(path).suffix.lower().lstrip(".")
    output = get_output_path(path, ext)
    orig_size = os.path.getsize(path)
    if orig_size == 0:
        return

    if ext in ["jpg", "jpeg", "png", "heic", "heif", "webp"]:
        compress_fn = compress_image
    elif ext in ["mp3", "aac", "m4a", "wav", "flac", "opus"]:
        compress_fn = compress_audio
    elif ext in ["mp4", "mov", "mkv"]:
        compress_fn = compress_video
    elif ext == "pdf":
        compress_fn = compress_pdf
    elif ext in ["txt", "md", "py", "c", "java", "sh", "was", "vcf", "enc", "pem", "xltx", "key", "zip", "p12", "crt",
                 "docx", "rar", "json", "apk", "csv", "ipynb", "xlsx"]:
        # .was file are WhatsApp stickers which are already compressed
        # .docx files are complicated to compress, so we leave them as-is
        return
    else:
        print(f"Unsupported file format: {ext=} {path=}")
        return  # unsupported

    cmd = compress_fn(path, mode, output)
    if not cmd:
        print(f"Failed to compress {path}")
        return
    run_cmd(cmd)

    # Compare sizes: keep only if smaller
    if output:
        new_size = os.path.getsize(output)
        if new_size == 0:
            # some .webp files are complicated to compress, so we leave them as-is
            print(f"Failed to compress {path}")
            os.remove(output)
            return
        if new_size >= orig_size:
            os.remove(output)
            return
        if replace:
            os.replace(output, path)

    return


# ============================================================
# RECURSIVE WALK WITH PROGRESS BAR
# ============================================================

def compress_folder(targets, mode, replace):
    all_files = []
    for target_arg in targets:
        # expand glob
        files = [Path(f).resolve() for f in glob(target_arg, recursive=True)]

        if not files:
            p = Path(target_arg).expanduser().resolve()
            if p.is_file():
                files = [p]
            elif p.is_dir():
                files = [
                    Path(root) / fn
                    for root, dirs, filenames in os.walk(p)
                    for fn in filenames
                ]
        files = [f for f in files if f.is_file()]
        all_files.extend(files)

    for f in tqdm(all_files, desc=f"Compressing ({mode})", unit="file"):
        compress_file(f, mode, replace)

    # Run in parallel
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(compress_file, f, mode, replace) for f in all_files]

        for future in tqdm(as_completed(futures), total=len(futures)):
            try:
                future.result()
            except Exception as e:
                print(f"[ERROR] Compression failed: {e}")


# ============================================================
# CLI ENTRY POINT
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recursive Media Compressor")
    parser.add_argument("targets",
                        nargs="+",
                        help="One or more files, directories, or glob patterns to compress")
    parser.add_argument("--mode", default="medium",
                        choices=["low", "medium", "high", "extreme"],
                        help="Compression strength")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate compression without writing files")

    args = parser.parse_args()
    compress_folder(args.targets, args.mode, not args.dry_run)

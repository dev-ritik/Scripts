# app.py

import threading

from flask import Flask, render_template, request, jsonify, send_file, abort

from settings import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, HEIC_EXTENSIONS
from utils import scan_files, apply_exif_updates, generate_video_thumbnail, generate_heic_thumbnail, \
    get_all_metadata_batched

app = Flask(__name__)

PROGRESS = {"total": 0, "done": 0}


@app.route("/")
def index():
    return render_template("index.html")


import os


@app.route("/load", methods=["GET"])
def load():
    import json

    targets = request.args.get("targets")
    targets = json.loads(targets) if targets else []

    files = list(scan_files(targets))

    if not files:
        return jsonify([])

    all_files_data = get_all_metadata_batched(files)
    all_files_data.sort(key=lambda x: x.get("date", ""))

    if len(all_files_data) == 0:
        print("No supported media files found in the specified targets.")

    return jsonify(all_files_data)


@app.route("/thumbnail")
def thumbnail():
    path = request.args.get("path")

    if not path or not os.path.exists(path):
        abort(404)

    ext = os.path.splitext(path)[1].lower()

    # Image → return directly
    if ext in IMAGE_EXTENSIONS:
        return send_file(path, max_age=3600)

    # Video → generate thumbnail
    if ext in VIDEO_EXTENSIONS:
        if thumb := generate_video_thumbnail(path):
            return send_file(thumb, max_age=3600)
        else:
            raise ValueError(f"Failed to generate thumbnail for {path}")

    if ext in HEIC_EXTENSIONS:
        thumb = generate_heic_thumbnail(path)
        if thumb:
            return send_file(thumb, max_age=3600)
        else:
            raise ValueError(f"Failed to generate thumbnail for {path}")

    raise ValueError(f"Unsupported file type: {ext}")


def process_updates(items, options):
    global PROGRESS
    PROGRESS["total"] = len(items)
    PROGRESS["done"] = 0

    for item in items:
        apply_exif_updates(
            item["path"],
            date=item.get("date"),
            gps=item.get("gps"),
            rewrite=options.get("rewrite"),
            force=options.get("force"),
            dry_run=options.get("dry_run"),
            skip_existing=options.get("skip_existing"),
            guess_date=options.get("guess_date")
        )
        PROGRESS["done"] += 1


@app.route("/update", methods=["POST"])
def update():
    payload = request.json

    items = payload["items"]
    options = payload["options"]

    thread = threading.Thread(
        target=process_updates,
        args=(items, options)
    )
    thread.start()

    return jsonify({"status": "started"})


@app.route("/progress")
def progress():
    print(PROGRESS)
    return jsonify(PROGRESS)


# @app.route("/guess-date", methods=["POST"])
# def guess_date():
#     path = request.json["path"]
#     suggested = request.json.get("suggested_datetime")
#
#     guessed = guess_date_from_filename(
#         path,
#         suggested_datetime=suggested
#     )
#
#     return jsonify({"date": guessed})

if __name__ == "__main__":
    app.run(debug=True)

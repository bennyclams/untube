from flask import Blueprint, Response, request, redirect, url_for, flash
from adless.tools import get_progress
from pathlib import Path
import base64
import shutil
import redis
import json
import os

v1 = Blueprint("v1", __name__)
db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
video_dir = os.getenv("VIDEO_DIR", "/tmp/untube")

@v1.route("/queue/", methods=["POST"])
def queue():
    videos = request.json.get("videos", [])
    for video in videos:
        vid = video.get("id", None)
        itag = video.get("quality", None)
        only_audio = video.get("audioOnly", False)
        if not vid:
            continue
        _q = {
            "id": vid,
            "itag": itag,
            "only_audio": only_audio
        }
        db.lpush("download_queue", json.dumps(_q))
    flash("Added %d items to download queue" % len(videos), "success")
    return {"status": "ok"}

@v1.route("/delete/", methods=["POST"])
def delete():
    videos = request.json.get("videos", [])
    for video in videos:
        if db.exists(video):
            video_info = json.loads(db.get(video))
            # video_path = Path(video_dir).joinpath(video_info["title"])
            db.lpush("delete_queue", str(video_info["title"]))
        else:
            video_title = base64.b64decode(video).decode("utf-8")
            # video_path = Path(video_dir).joinpath(video_title)
            db.lpush("delete_queue", str(video_title))
    flash("Added %d items to delete queue" % len(videos), "success")
    return {"status": "ok"}

@v1.route("/thumbnail/<video_name>/", methods=["GET"])
def thumbnail(video_name):
    if db.exists(video_name):
        video_info = json.loads(db.get(video_name))
        video_name = video_info["title"]
    else:
        return f"Not Found: {video_name}", 404
    video_path = Path(video_dir).joinpath(video_name)
    thumb_path = video_path.joinpath(f"{video_name}.jpg")
    if not thumb_path.exists():
        return f"Not Found: {thumb_path}", 404
    with open(thumb_path, "rb") as f:
        thumb_data = f.read()
    response = Response(thumb_data, mimetype="image/jpeg")
    response.cache_control.max_age = 86400
    return response

@v1.route("/progress/", methods=["GET"])
def progress():
    video_id = request.args.get("id", None)
    if not video_id:
        return {"status": "error", "message": "No video ID provided"}
    if not db.exists(video_id):
        return {"status": "error", "message": "Video not found"}
    video_info = json.loads(db.get(video_id))
    progress = get_progress(video_info["title"])
    if progress is None:
        return {"status": "not_started"}
    progress["status"] = "ok"
    return progress
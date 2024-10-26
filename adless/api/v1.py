import re
from flask import Blueprint, Response, request, redirect, url_for, flash, current_app
from adless.tools import find_removed, fix_channel_tags, get_fs_downloads, get_progress, save_video_info
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

@v1.route("/archive/", methods=["POST"])
def archive():
    videos = request.json.get("videos", [])
    for video in videos:
        if db.exists(video):
            video_info = json.loads(db.get(video))
            db.rpush(current_app.config['ARCHIVE_QUEUE'], f"{current_app.config['ARCHIVE_LIBRARY']}:{video_info['title']}")
    flash("Added %d items to archive queue" % len(videos), "success")
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
        thumb_path = Path(__file__).parent.joinpath("static", "thumb_unavailable.jpg")
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

@v1.route("/video_info/<video_id>", methods=["GET"])
def video_info(video_id):
    if not db.exists(video_id):
        return {"status": "error", "message": "Video not found"}
    video_info = json.loads(db.get(video_id))
    return video_info


@v1.route("/clear_queue/", methods=["GET"])
def clear_queue():
    db.delete("download_queue")
    return {"status": "ok"}

@v1.route("/clear_errors/", methods=["GET"])
def clear_errors():
    db.delete("errors")
    return {"status": "ok"}

@v1.route("/write_channels/", methods=["GET"])
def write_channels():
    db.lpush("maintenance_queue", json.dumps({"action": "write_channels"}))
    return {"status": "ok"}

@v1.route("/prune_removed/", methods=["GET"])
def prune_removed():
    db.lpush("maintenance_queue", json.dumps({"action": "prune_removed"}))
    return {"status": "ok"}

@v1.route("/save_video_info/", methods=["GET"])
def save_info():
    db.lpush("maintenance_queue", json.dumps({"action": "save_video_info"}))
    return {"status": "ok"}
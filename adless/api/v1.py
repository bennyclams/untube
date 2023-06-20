from flask import Blueprint, request, redirect, url_for, flash
import redis
import json
import os

v1 = Blueprint("v1", __name__)
db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

@v1.route("/queue/", methods=["POST"])
def queue():
    videos = request.json.get("videos", [])
    for video in videos:
        vid = video.get("id", None)
        itag = video.get("itag", None)
        only_audio = video.get("only_audio", False)
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
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_session import Session
from adless.tools import get_video_info, get_playlist_info, unshorten, get_fs_downloads, get_progress
from adless.api import api
from urllib.parse import urlparse
from urllib.parse import parse_qs
from hashlib import sha1
import redis
import json
import os 


app = Flask(__name__, static_folder="static", static_url_path="/static")
app.register_blueprint(api, url_prefix="/api")
db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379").strip())
app.config["DEBUG"] = (os.getenv("DEBUG", "false").lower() == "true")
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = db
app.config["ADMIN_PASSWORD"] = os.getenv("ADMIN_PASSWORD", "password")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(24))

Session(app)

@app.before_request
def validate_authenticated():
    if request.path.startswith("/login") or request.path.startswith("/manifest.json"):
        return
    else:
        if not session.get("authenticated", False):
            return redirect(url_for("login"))


@app.route("/")
def index():
    recent_search_keys = db.lrange("recent_searches", 0, 9)
    download_queue_keys = db.lrange("download_queue", 0, -1)
    downloads_keys = db.lrange("downloads", 0, 10)
    recent_searches = []
    download_queue = []
    downloads = []
    for key in recent_search_keys:
        try:
            info = json.loads(db.get(key))
        except TypeError:
            db.lrem("recent_searches", 0, key)
            continue
        if info["_type"] == "video":
            info["length"] = str(timedelta(seconds=info["length"]))
        info["title"] = info["title"][:30] + "..." if len(info["title"]) > 30 else info["title"]
        if info["description"]:
            info["description"] = info["description"][:100] + "..." if len(info["description"]) > 100 else info["description"]
        recent_searches.append(info)
    for key in download_queue_keys:
        dlinfo = json.loads(key)
        info = json.loads(db.get(dlinfo["id"]))
        if info["_type"] == "video":
            info["length"] = str(timedelta(seconds=info["length"]))
        info["title"] = info["title"][:30] + "..." if len(info["title"]) > 30 else info["title"]
        if info["description"]:
            info["description"] = info["description"][:100] + "..." if len(info["description"]) > 100 else info["description"]
        download_queue.append(info)
    for key in downloads_keys:
        info = json.loads(db.get(key))
        if info["_type"] == "video":
            info["length"] = str(timedelta(seconds=info["length"]))
        info["title"] = info["title"][:30] + "..." if len(info["title"]) > 30 else info["title"]
        if info["description"]:
            info["description"] = info["description"][:100] + "..." if len(info["description"]) > 100 else info["description"]
        downloads.append(info)
    data = {
        "recent_searches": recent_searches,
        "recent_downloads": downloads,
        "download_queue": download_queue,
        "page": "home"
    }
    return render_template("index.html", **data)


@app.route("/login/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["password"] == app.config["ADMIN_PASSWORD"]:
            session["authenticated"] = True
            return redirect(url_for("index"))
        else:
            flash("Invalid password", "warning")
            return redirect(url_for("login"))
    else:
        return render_template("login.html")


@app.route("/info/", methods=["POST"])
def content_info():
    if "url" not in request.form:
        if "text" in request.form:
            url = request.form["text"]
        else:
            flash("Invalid URL", "warning")
            return redirect(url_for("index"))
    else:
        url = request.form["url"]
    hashed_url = sha1(url.encode("utf-8")).hexdigest()
    parsed_url = urlparse(url)
    if parsed_url.netloc != "youtu.be" and parsed_url.netloc != "www.youtube.com" and parsed_url.netloc != "youtube.com":
        hashed_url = sha1(url.encode("utf-8")).hexdigest()
        key_name = f"video:{hashed_url}"
        db.lpush("recent_searches", key_name)
        db.ltrim("recent_searches", 0, 10)
        return redirect(url_for("video_info", v=url, yt="no"))
    if parsed_url.netloc == "youtu.be":
        new_url = unshorten(url)
        hashed_url = sha1(new_url.encode("utf-8")).hexdigest()
        parsed_url = urlparse(new_url)
    url_args = parse_qs(parsed_url.query)
    for key, value in url_args.items():
        url_args[key] = value[0]
    if parsed_url.path == "/watch":
        key_name = f"video:{hashed_url}"
        db.lpush("recent_searches", key_name)
        db.ltrim("recent_searches", 0, 10)
        return redirect(url_for("video_info", **url_args))
    elif parsed_url.path == "/playlist":
        key_name = f"playlist:{hashed_url}"
        db.lpush("recent_searches", key_name)
        db.ltrim("recent_searches", 0, 10)
        return redirect(url_for("playlist_info", **url_args))
    elif parsed_url.path.startswith("/live"):
        video_id = parsed_url.path.split("/")[-1]
        real_url = f"https://www.youtube.com/watch?v={video_id}"
        key_name = f"video:{sha1(real_url.encode('utf-8')).hexdigest()}"
        db.lpush("recent_searches", key_name)
        db.ltrim("recent_searches", 0, 10)
        return redirect(url_for("video_info", v=video_id))
    else:
        flash("Invalid URL", "warning")
        return redirect(url_for("index"))
    

@app.route("/info/video/", methods=["GET"])
def video_info():
    video_id = request.args.get("v")
    _yt = request.args.get("yt", "yes") == "yes"
    bust_cache = request.args.get("bust_cache", "no") == "yes"
    if _yt:
        full_url = f"https://www.youtube.com/watch?v={video_id}"
        info = get_video_info(full_url, bust_cache=bust_cache)
        info["length"] = str(timedelta(seconds=info["length"]))
        info["progress"] = get_progress(info["title"])
        return render_template("video_info.html", **info)
    else:
        info = get_video_info(video_id, bust_cache=bust_cache)
        info["length"] = str(timedelta(seconds=info["length"]))
        info["progress"] = get_progress(info["title"])
        return render_template("off_youtube_info.html", **info)


@app.route("/info/playlist/", methods=["GET"])
def playlist_info():
    playlist_id = request.args.get("list")
    full_url = f"https://www.youtube.com/playlist?list={playlist_id}"
    info = get_playlist_info(full_url)
    for video in info["videos"]:
        if video["description"]:
            video["description"] = video["description"][:100] + "..." if len(video["description"]) > 100 else video["description"]
    return render_template("playlist_info.html", **info)


@app.route("/queue/", methods=["GET"])
def queue():
    content_key = request.args.get("id")
    _yt = request.args.get("yt", "yes") == "yes"
    title = request.args.get("title", None)
    itag = request.args.get("itag", None)
    only_audio = (request.args.get("only_audio", "no") == "yes")
    if db.exists(content_key):
        info = json.loads(db.get(content_key))
        if not _yt:
            if title:
                info["title"] = title
                db.set(content_key, json.dumps(info))
        queue_info = {
            "id": content_key,
            "itag": itag,
            "only_audio": only_audio
        }
        db.lpush("download_queue", json.dumps(queue_info))
        flash(f"Successfully added {info['_type']} '{info['title']}' to the download queue", "success")
        if _yt:
            if info["_type"] == "video":
                return redirect(url_for("video_info", v=info["id"]))
            elif info["_type"] == "playlist":
                return redirect(url_for("playlist_info", list=info["id"]))
        else:
            return redirect(url_for("video_info", v=info["_url"], yt="no"))
    else:
        flash("Content not yet indexed. Try searching for this content by non-shortened URL.", "warning")
        return redirect(url_for("index"))

@app.route("/downloads/", methods=["GET"])
def downloads():
    to_delete = [x.decode('utf-8') for x in db.lrange("delete_queue", 0, -1)]
    dls = []
    for dl in get_fs_downloads():
        if dl["title"] in to_delete:
            dl["delete_queue"] = True
        if "description" in dl:
            dl["description"] = dl["description"][:100] + "..." if len(dl["description"]) > 100 else dl["description"]

        dls.append(dl)
    return render_template("downloads.html", downloads=dls, page="downloads")

@app.route("/manifest.json", methods=["GET"])
def manifest():
    return {
        "id": "io.untube",
        "short_name": "Untube",
        "name": "Untube",
        "description": "A tool for downloading YouTube videos and playlists via their share links for offline viewing.",
        "display": "standalone",
        "start_url": "/",
        "scope": "/",
        "theme_color": "#2b3035",
        "background_color": "#212529",
        "icons": [
            {
                "src": "/static/web/icon-192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/web/icon-512.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ],
        "share_target": {
            "action": "/info/",
            "method": "POST",
            "enctype": "application/x-www-form-urlencoded",
            "params": {
                "_url": "url",
                "url": "text",
                "text": "text",
                "title": "title"
            }
        }
    }

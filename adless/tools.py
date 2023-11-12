from datetime import datetime
from clilib.util.logging import Logging
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from hashlib import sha1
import threading
import requests
import base64
import ffmpeg
import yt_dlp
import redis
import json
import sys
import re
import os


db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
video_dir = Path(os.getenv("VIDEO_DIR", "/tmp/untube"))
format_filter = os.getenv("FORMAT_FILTER", None)
if format_filter is not None:
    format_filter = format_filter.split(",")
else:
    format_filter = ["mp4", "webm", "ogg", "flv", "3gp", "mkv", "m4a"]
resolution_filter = os.getenv("RESOLUTION_FILTER", None)
if resolution_filter is not None:
    resolution_filter = resolution_filter.split(",")
    resolution_filter = [int(resolution) for resolution in resolution_filter]
else:
    resolution_filter = [2160, 1920, 1440, 1280, 1080, 960, 720, 480]
language_filter = os.getenv("LANGUAGE_FILTER", None)
if language_filter is not None:
    language_filter = language_filter.split(",")
    
def media_exists(title: str):
    """
    Check if a given media exists in the Plex library.
    """
    downloads = get_fs_downloads()
    for download in downloads:
        if download["title"] == title:
            return True
    return False

def escape_ansi(line):
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', line).strip()

def get_progress(video_name):
    """
    Get the progress of a download.
    """
    video_path = Path(video_dir).joinpath(video_name)
    audio_progress_path = video_path.joinpath(f"audio_progress.json")
    video_progress_path = video_path.joinpath(f"video_progress.json")
    processing = video_path.joinpath(".processing")
    processing_done = video_path.joinpath(".processing_done")
    processing_error = video_path.joinpath(".processing_error")
    if not audio_progress_path.exists():
        audio_progress = {"status": "not_started"}
    else:
        with open(audio_progress_path, "r") as f:
            audio_progress = json.loads(f.read())
    if not video_progress_path.exists():
        video_progress = {"status": "not_started"}
    else:
        with open(video_progress_path, "r") as f:
            video_progress = json.loads(f.read())
    processing_status = "not_started"
    if processing.exists():
        processing_status = "processing"
    elif processing_done.exists():
        processing_status = "done"
    elif processing_error.exists():
        processing_status = "error"
    if audio_progress["status"] == "not_started" and video_progress["status"] == "not_started":
        return None
    return {
        "audio": audio_progress,
        "video": video_progress,
        "processing": processing_status,
    }

def ydl_progress(d):
    file_path = None
    if "filename" in d:
        file_path = Path(d["filename"])
    progress_type = file_path.suffix[1:]
    if progress_type in ("mp4", "webm", "ogg", "flv", "3gp", "mkv"):
        progress_type = "video"
    if "downloaded_bytes" not in d:
        d["downloaded_bytes"] = 0
        if file_path:
            file_path = Path(d["filename"])
            file_size = file_path.stat().st_size
            d["downloaded_bytes"] = file_size
    if d['status'] == 'downloading':
        progress = {
            "status": "downloading",
            "part": d["filename"].split(".")[-1],
            "downloaded_bytes": d["downloaded_bytes"],
            "total_bytes": d["total_bytes"] if "total_bytes" in d else None,
            "pct": escape_ansi(d["_percent_str"]) if "_percent_str" in d else None,
        }
        file_path = Path(d["filename"])
        progress_path = file_path.parent.joinpath(f"{progress_type}_progress.json")
        with open(progress_path, "w") as f:
            f.write(json.dumps(progress))   
    elif d['status'] == 'finished':
        progress = {
            "status": "finished",
            "part": d["filename"].split(".")[-1],
            "downloaded_bytes": d["downloaded_bytes"],
            "total_bytes": d["total_bytes"] if "total_bytes" in d else None,
            "pct": escape_ansi(d["_percent_str"]) if "_percent_str" in d else None,
        }
        file_path = Path(d["filename"])
        progress_path = file_path.parent.joinpath(f"{progress_type}_progress.json")
        with open(progress_path, "w") as f:
            f.write(json.dumps(progress))   

def on_progress(stream, chunk, bytes_remaining):
    """
    Prints the current download progress.
    """
    total_size = stream.filesize
    bytes_downloaded = total_size - bytes_remaining

    percent = bytes_downloaded / total_size * 100
    print(f"Downloading {percent:.2f}%", end="\r")
    if bytes_remaining == 0:
        print()

def on_complete(stream, file_path):
    """
    Prints the complete download message.
    """
    print(f"Downloaded to {file_path}")

def get_fs_downloads():
    """
    Get all currently available downloads from the filesystem.
    """
    video_dirs = [d for d in video_dir.iterdir() if d.is_dir()]
    downloads = []
    for _video_dir in video_dirs:
        dbkey_file = _video_dir.joinpath(".key")
        if dbkey_file.exists():
            dbkey = dbkey_file.read_text()
            if db.exists(dbkey):
                downloads.append(json.loads(db.get(dbkey)))
                continue
        encoded_name = base64.b64encode(_video_dir.name.encode()).decode()
        thumb_url = "/api/v1/thumbnail/%s/" % encoded_name
        if not _video_dir.joinpath(f"{_video_dir.name}.jpg").exists():
            thumb_url = "/static/images/thumb_unavailable.png"
        downloads.append({
            "_keyname": encoded_name,
            "id": encoded_name,
            "title": _video_dir.name,
            "author": "Unavailable",
            "length": "Unavailable",
            "type": "video",
            "thumbnail": thumb_url,
        })
    return downloads

def get_off_youtube_video(video_id: str, destination: str, itag: int, filename: str = None):
    """
    download a single video
    """
    destination = Path(destination)
    if not destination.exists():
        destination.mkdir(parents=True)
    video = json.loads(db.get(video_id))
    video_name = video["title"]
    if filename:
        video_name = filename
    video_name = video_name.replace(",", "").replace("|", "").replace("/", "")
    logger = Logging(video["host"]).get_logger()
    logger.info(f"Downloading video: {video_name} ...")
    destination = destination.joinpath(video_name)
    for stream in video["streams"]:
        if stream["itag"] == itag:
            video_format = stream
            break
    try:
        logger.info(f"Getting video ...")
        video_dest = str(destination.joinpath(f"{video_name}.{video_format['mime_type']}"))
        yt_dlp.YoutubeDL({
            "outtmpl": video_dest,
            "logger": logger,
            "format": video_format["itag"],
            "progress_hooks": [ydl_progress],
        }).download([video["_url"]])
    except Exception as e:
        logger.error("Error downloading video")
        logger.error(e)
        return False
    logger.info("Video downloaded to: %s" % video_dest)
    key_file = destination.joinpath(f".key")
    with open(key_file, "w") as f:
        f.write(video['_keyname'])
    db.lpush("downloads", video['_keyname'])

def get_video(video_id: str, destination: str, video_subdir: bool = True, only_audio: bool = False, itag: int = None, filename: str = None):
    """
    download a single video
    """
    destination = Path(destination)
    if not destination.exists():
        destination.mkdir(parents=True)
    video = yt_dlp.YoutubeDL().extract_info(video_id, download=False)
    video_name = video["title"]
    if filename:
        video_name = filename
    video_name = video_name.replace(",", "").replace("|", "").replace("/", "")
    logger = Logging(video["id"]).get_logger()
    logger.info(f"Downloading video: {video_name} ...")
    if not only_audio:
        if video_subdir:
            destination = destination.joinpath(video_name)
        if not destination.exists():
            destination.mkdir(parents=True)
        if itag:
            for stream in video["formats"]:
                if stream["format_id"] == itag:
                    video_format = stream
                    break
        else:
            format_pairs = []
            streams = []
            for stream in video["formats"]:
                # if "format_note" not in stream:
                #     print(stream)
                #     continue
                # if stream["format_note"] == "tiny":
                #     continue
                format_note = "%sp@%s" % (stream["height"], stream["fps"]) if "height" in stream else "audio only"
                if "height" in stream and stream["height"] is not None:
                    if stream["video_ext"] not in format_filter:
                        continue
                    if stream["height"] not in resolution_filter:
                        continue
                    format_pair = "%s/%s" % (stream["resolution"], stream["video_ext"])
                    if format_pair in format_pairs:
                        continue
                    format_pairs.append(format_pair)
                    streams.append(stream)
            streams = sorted(streams, key=lambda x: x["resolution"], reverse=True)
            video_format = streams[0]
        def get_video():
            try:
                logger.info(f"Getting video stream ...")
                yt_dlp.YoutubeDL({
                    "outtmpl": str(destination.joinpath(f"{video_name}.video")),
                    # "progress_hooks": [on_progress],
                    "logger": logger,
                    "format": video_format["format_id"],
                    "progress_hooks": [ydl_progress],
                }).download([video_id])
            except Exception:
                logger.exception("Error downloading video")
                return False
            return True
        video_thread = threading.Thread(target=get_video)
        video_thread.start()


    logger.info("Getting audio stream ...")
    audio_streams = []
    for stream in video["formats"]:
        if stream["audio_ext"] is not None and stream["audio_ext"] != "none" and stream["abr"] is not None:
            audio_streams.append(stream)
    if language_filter is not None:
        old_streams = audio_streams.copy()
        for stream in audio_streams:
            if "language" in stream and stream["language"] not in language_filter:
                audio_streams.remove(stream)
        if len(audio_streams) == 0:
            logger.warn("No audio streams found with language filter: %s, proceeding without filter" % language_filter)
            audio_streams = old_streams
    audio_streams = sorted(audio_streams, key=lambda x: x["abr"], reverse=True)
    audio_format = audio_streams[0]
    yt_dlp.YoutubeDL({
        "outtmpl": str(destination.joinpath(f"{video_name}.audio")),
        # "progress_hooks": [on_progress],
        "logger": logger,
        "format": audio_format["format_id"],
        "progress_hooks": [ydl_progress],
    }).download([video_id])

    if not only_audio:
        video_thread.join()
        
    logger.info("Getting thumbnail ...")
    thumbnail_url = video["thumbnail"]
    thumbnail = requests.get(thumbnail_url)
    with open(destination.joinpath(f"{video_name}.jpg"), "wb") as f:
        f.write(thumbnail.content)

    video_file = destination.joinpath(f"{video_name}.video")
    audio_file = destination.joinpath(f"{video_name}.audio")
    output_file = destination.joinpath(f"{video_name}.%s" % video_format["ext"])

    if not only_audio:
        logger.info("Merging streams ...")
        _p = destination.joinpath(".processing")
        _pd = destination.joinpath(".processing_done")
        if _pd.exists():
            _pd.unlink()
        _p.touch()
        _v = ffmpeg.input(video_file)
        _a = ffmpeg.input(audio_file)
        if output_file.exists():
            output_file.unlink()
        try:
            ffmpeg.output(_v, _a, str(output_file), acodec='copy', vcodec='copy', strict="-2").run()
        except Exception as e:
            logger.exception("Error merging audio and video streams: %s" % e)
            _p.unlink()
            destination.joinpath(".processing_error").touch()
            full_url = f"https://www.youtube.com/watch?v={video['id']}"
            key_name = f"video:{sha1(full_url.encode('utf-8')).hexdigest()}"
            if db.exists(key_name):
                video_info = json.loads(db.get(key_name))
                video_info["error"] = str(e)
                db.set(key_name, json.dumps(video_info))
            db.lpush("errors", key_name)
            return False
            
        video_file.unlink()
        audio_file.unlink()
        _p.unlink()
        _pd.touch()

    full_url = f"https://www.youtube.com/watch?v={video['id']}"
    key_name = f"video:{sha1(full_url.encode('utf-8')).hexdigest()}"
    key_file = destination.joinpath(f".key")
    with open(key_file, "w") as f:
        f.write(key_name)
    db.lpush("downloads", key_name)

def get_playlist_videos(playlist_id: str, destination: str, only_audio: bool = False):
    """
    download all videos in a playlist
    """
    destination = Path(destination)
    if not destination.exists():
        destination.mkdir(parents=True)
    playlist = Playlist(playlist_id)
    logger = Logging(video.video_id).get_logger()
    logger.info(f"Downloading playlist: {playlist.title}")
    # destination = destination.joinpath(playlist.title)
    for i, video in enumerate(playlist.video_urls):
        get_video(video, destination, only_audio=only_audio)
        # video.download(destination=destination, resolution="720p"
    full_url = f"https://www.youtube.com/playlist?list={playlist.playlist_id}"
    key_name = f"playlist:{sha1(full_url.encode('utf-8')).hexdigest()}"
    db.lpush("downloads", key_name)

def get_playlist_info(playlist_id: str):
    """
    Get playlist info from YouTube and cache it in Redis for 24 hours.
    """
    hashed_url = sha1(playlist_id.encode("utf-8")).hexdigest()
    key_name = f"playlist:{hashed_url}"
    if db.exists(key_name):
        info = json.loads(db.get(key_name))
        if info["_pull_time"] + 86400 > int(datetime.now().timestamp()):
            info["_keyname"] = key_name
            return info
    # playlist = Playlist(playlist_id)
    playlist = yt_dlp.YoutubeDL({"quiet": True}).extract_info(playlist_id, download=False)
    # return playlist
    info = {
        "id": playlist['id'],
        "title": playlist['title'],
        # "description": playlist.description,
        "description": playlist['description'] if 'description' in playlist else None,
        # "thumbnail": playlist.thumbnail_url,
        "author": playlist['uploader'],
        "length": len(playlist['entries']),
        # "views": playlist.views,
        "videos": [get_video_info(video['original_url'], video) for video in playlist['entries']]
    }
    info["thumbnail"] = info["videos"][0]["thumbnail"]
    info["_type"] = "playlist"
    info["_pull_time"] = int(datetime.now().timestamp())
    info_dump = json.dumps(info)
    db.set(key_name, info_dump)
    info["_keyname"] = key_name
    return info

def get_video_info(video_id: str, entry: dict = None, bust_cache: bool = False):
    """
    Get video info from YouTube and cache it in Redis for 24 hours.
    """
    parsed_url = urlparse(video_id)
    _yt = True
    if parsed_url.netloc == "www.youtube.com":
        parsed_args = parse_qs(parsed_url.query)
        real_id = parsed_args["v"][0]
        hashed_url = sha1(video_id.encode("utf-8")).hexdigest()
        key_name = f"video:{hashed_url}"
    else:
        _yt = False
        real_id = video_id
        hashed_url = sha1(video_id.encode("utf-8")).hexdigest()
        key_name = f"video:{hashed_url}"
    if db.exists(key_name):
        info = json.loads(db.get(key_name))
        if info["_pull_time"] + 86400 > int(datetime.now().timestamp()):
            info["_keyname"] = key_name
            info["_downloaded"] = media_exists(info["title"])
            if not bust_cache:
                return info
            else:
                db.delete(key_name)
    try:
        # print("Getting video info (%s) ..." % video_id)
        # video = YouTube(video_id)
        if entry:
            video = entry
        else:
            video = yt_dlp.YoutubeDL().extract_info(video_id, download=False)
        format_pairs = []
        streams = []
        for stream in video["formats"]:
            # if "format_note" not in stream:
            #     print(stream)
            #     continue
            # if stream["format_note"] == "tiny":
            #     continue
            format_note = "%sp@%s (%s)" % (stream["height"], stream["fps"], stream["video_ext"]) if "height" in stream else "audio only"
            if "resolution" in stream and stream["resolution"] is not None:
                if stream["video_ext"] not in format_filter:
                    continue
                if stream["height"] not in resolution_filter:
                    continue
                format_pair = "%s/%s" % (stream["resolution"], stream["video_ext"])
                if format_pair in format_pairs:
                    continue
                format_pairs.append(format_pair)

                streams.append({
                    "itag": stream["format_id"],
                    "mime_type": stream["video_ext"],
                    "height": stream["height"],
                    "resolution": stream["resolution"],
                    "fps": stream["fps"] if "fps" in stream else None,
                    "url": stream["url"]
                })

        streams = sorted(streams, key=lambda x: x["resolution"], reverse=True)
        # print("Got video info (%s) ..." % video_id)
    except Exception as e:
        print(e)
        return {
            "id": real_id,
            "title": "Age Restricted Video",
            "description": "Unable to download age-restricted videos at this time ...",
            "thumbnail": None,
            "author": "Unknown",
            "length": 0,
            "views": 0,
            "rating": None,
            "publish_date": 0,
            "streams": [],
            "_type": "video",
            "_pull_time": int(datetime.now().timestamp()),
            "_keyname": key_name,
            "_downloaded": False,
            "_unavailable": True,
            "_error": str(e)
        }

    if _yt:
        info = {
            "id": video["id"],
            # Remove commas due to plex bug which causes incorrect 
            # media to be returned when title contains comma.
            "_keyname": key_name,
            "_youtube": True,
            "title": video["title"].replace(",", "").replace("|", "").replace("/", ""),
            "description": video["description"],
            "thumbnail": video["thumbnail"],
            "author": video["uploader"],
            "length": video["duration"],
            "views": video["view_count"],
            "rating": video["average_rating"],
            "publish_date": datetime.strptime(video["upload_date"], "%Y%m%d").timestamp(),
            "keywords": video["tags"],
            "streams": streams
        }
    else:
        info = {
            "id": video["id"],
            # Remove commas due to plex bug which causes incorrect 
            # media to be returned when title contains comma.
            "_keyname": key_name,
            "_youtube": False,
            "_url": video_id,
            "title": video["title"].replace(",", "").replace("|", "").replace("/", ""),
            "description": video["description"] if "description" in video else None,
            "thumbnail": video["thumbnail"] if "thumbnail" in video else None,
            "author": video["uploader"] if "uploader" in video else None,
            "length": video["duration"] if "duration" in video else None,
            "publish_date": datetime.strptime(video["upload_date"], "%Y%m%d").timestamp() if "upload_date" in video else None,
            "host": parsed_url.netloc,
            "streams": streams
        }
    info["_type"] = "video"
    info["_pull_time"] = int(datetime.now().timestamp())
    info_dump = json.dumps(info)
    db.set(key_name, info_dump)
    info["_downloaded"] = media_exists(info["title"])
    info["_unavailable"] = False
    return info

def unshorten(url: str):
    """
    Attempt to get real URL from shortened youtube URL. Technically would work
    with any URL shortener which just redirects with a Location header.
    """
    res = requests.head(url)
    if "Location" not in res.headers:
        return url
    new_url = urlparse(res.headers["Location"])
    args = parse_qs(new_url.query)
    if new_url.netloc == "www.youtube.com":
        if new_url.path == "/watch":
            print("Found video ID")
            return f"https://www.youtube.com/watch?v={args['v'][0]}"
        elif new_url.path == "/playlist":
            return f"https://www.youtube.com/playlist?list={args['list'][0]}"
    return res.headers["Location"]

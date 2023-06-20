from datetime import datetime
from clilib.util.logging import Logging
from adless.plex import media_exists
from urllib.parse import parse_qs, urlparse
from pytube import YouTube, Playlist
# from pytube.exceptions import AgeRestrictedError, VideoUnavailable
import pytube.exceptions as exceptions
from pathlib import Path
from hashlib import sha1
import requests
import ffmpeg
import redis
import json
import re
import os


db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

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

def get_video(video_id: str, destination: str, video_subdir: bool = True, only_audio: bool = False, itag: int = None, filename: str = None):
    """
    download a single video
    """
    destination = Path(destination)
    video = YouTube(video_id, on_progress_callback=on_progress, on_complete_callback=on_complete)
    video_name = video.title
    if filename:
        video_name = filename
    video_name = video_name.replace(",", "").replace("|", "").replace("/", "")
    logger = Logging(video.video_id).get_logger()
    logger.info(f"Downloading video: {video_name} ...")
    if only_audio:
        logger.info("only_audio is set to True, assuming this is music ...")
        # Assume this is being downloaded as music, and attempt to get track information
        logger.info("Getting track information ...")
        metadata = {}
        if video.description:
            matches = re.findall(r"([A-Z][a-z]+): (.*)", video.description)
            for match in matches:
                key = match[0].lower()
                if key in metadata:
                    continue
                metadata[key] = match[1]
        metadata["title"] = video_name
        metadata["artist"] = video.author
        if "album" not in metadata:
            metadata["album"] = "Unknown"

    if only_audio:
        destination = destination.joinpath(metadata["artist"]).joinpath(metadata["album"])
        if not destination.exists():
            destination.mkdir(parents=True)
    else:
        if video_subdir:
            destination = destination.joinpath(video_name)
        if not destination.exists():
            destination.mkdir(parents=True)

    thumbnail = destination.joinpath(f"{video_name}.jpg")
    res = requests.get(video.thumbnail_url)
    with open(thumbnail, "wb") as f:
        f.write(res.content)
    if not only_audio:
        logger.info("Getting video stream ...")
        if itag:
            logger.info(f"Using itag: {itag} ...")
            _vs = video.streams.get_by_itag(itag)
        else:
            logger.info("Using highest resolution stream ...")
            _vs = video.streams.order_by("resolution").desc().first()
        file_extension = _vs.mime_type.split("/")[-1]
        video_filename = f"{video_name}.{file_extension}"
        _vs.download(output_path=destination, filename=f"{video_name}.tmp")
    logger.info("Getting audio stream ...")
    video.streams.filter(only_audio=True).order_by("abr").desc().first().download(output_path=destination, filename=f"{video_name}.mp3")
    video_file = destination.joinpath(f"{video_name}.tmp")
    audio_file = destination.joinpath(f"{video_name}.mp3")
    if not only_audio:
        output_file = str(destination.joinpath(video_filename))
        logger.info("Merging streams ...")
        _v = ffmpeg.input(video_file)
        _a = ffmpeg.input(audio_file)
        ffmpeg.output(_v, _a, output_file, acodec='copy', vcodec='copy').run()
        video_file.unlink()
    if not only_audio:
        audio_file.unlink()
    full_url = f"https://www.youtube.com/watch?v={video.video_id}"
    key_name = f"video:{sha1(full_url.encode('utf-8')).hexdigest()}"
    db.lpush("downloads", key_name)
    # video.download(destination=destination, resolution="720p")

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
    playlist = Playlist(playlist_id)
    # return playlist
    info = {
        "id": playlist.playlist_id,
        "title": playlist.title,
        # "description": playlist.description,
        "description": None,
        # "thumbnail": playlist.thumbnail_url,
        "author": playlist.owner,
        "length": len(playlist.video_urls),
        # "views": playlist.views,
        "videos": [get_video_info(video_id) for video_id in playlist.video_urls]
    }
    info["thumbnail"] = info["videos"][0]["thumbnail"]
    info["_type"] = "playlist"
    info["_pull_time"] = int(datetime.now().timestamp())
    info_dump = json.dumps(info)
    db.set(key_name, info_dump)
    info["_keyname"] = key_name
    return info

def get_video_info(video_id: str):
    """
    Get video info from YouTube and cache it in Redis for 24 hours.
    """
    parsed_url = urlparse(video_id)
    parsed_args = parse_qs(parsed_url.query)
    real_id = parsed_args["v"][0]
    hashed_url = sha1(video_id.encode("utf-8")).hexdigest()
    key_name = f"video:{hashed_url}"
    if db.exists(key_name):
        info = json.loads(db.get(key_name))
        if info["_pull_time"] + 86400 > int(datetime.now().timestamp()):
            info["_keyname"] = key_name
            info["_downloaded"] = media_exists(info["title"])
            return info
    try:
        # print("Getting video info (%s) ..." % video_id)
        video = YouTube(video_id)
        # print("Got video info (%s) ..." % video_id)
    except exceptions.AgeRestrictedError:
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
            "_unavailable": True
        }
    except Exception as e:
        # print("Unable to get video info (%s): %s" % (video_id, e))
        return {
            "id": real_id,
            "title": "Video Unavailable (%s)" % e,
            "description": "Unable to download video at this time ...",
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
            "_unavailable": True
        }
    streams = []
    try:
        for stream in video.streams.filter(adaptive=True, mime_type="video/webm", only_video=True):
            streams.append({
                "itag": stream.itag,
                "mime_type": stream.mime_type,
                "resolution": stream.resolution,
                "fps": stream.fps,
                "bitrate": stream.bitrate,
                "type": "video"
            })
    except exceptions.AgeRestrictedError:
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
            "_unavailable": True
        }
    info = {
        "id": video.video_id,
        # Remove commas due to plex bug which causes incorrect 
        # media to be returned when title contains comma.
        "_keyname": key_name,
        "title": video.title.replace(",", "").replace("|", "").replace("/", ""),
        "description": video.description,
        "thumbnail": video.thumbnail_url,
        "author": video.author,
        "length": video.length,
        "views": video.views,
        "rating": video.rating,
        "publish_date": int(video.publish_date.timestamp()),
        "keywords": video.keywords,
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

from adless.config import db, video_dir, format_filter, resolution_filter, language_filter, cookies_path
# from adless.library import media_exists, thumbnail_exists, save_video_info, get_keyname
from urllib.parse import parse_qs, urlparse
from clilib.util.logging import Logging
from datetime import datetime
from mutagen.mp4 import MP4
from pathlib import Path
from hashlib import sha1
from adless import library, tools
import threading
import requests
import ffmpeg
import yt_dlp
import json


def get_progress(video_name: str):
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
            "pct": tools.escape_ansi(d["_percent_str"]) if "_percent_str" in d else None,
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
            "pct": tools.escape_ansi(d["_percent_str"]) if "_percent_str" in d else None,
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
    video_name = tools.sanitize_filename(video_name)
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
    # Generate thumbnail with ffmpeg
    logger.info("Generating thumbnail ...")
    thumbnail_dest = destination.joinpath(f"{video_name}.jpg")
    if thumbnail_dest.exists():
        thumbnail_dest.unlink()
    try:
        _v = ffmpeg.input(video_dest)
        ffmpeg.output(_v, str(thumbnail_dest), ss='00:00:01.000', vframes=1).run()
    except Exception as e:
        logger.error("Error generating thumbnail")
        logger.error(e)
    logger.info("Video downloaded to: %s" % video_dest)
    key_file = destination.joinpath(f".key")
    if "author" in video:
        mp4 = MP4(video_dest)
        mp4["\xa9gen"] = [video["author"]]
        mp4.save()
    # else:
    #     video_info = json.loads(db.get(key_name))
    #     if "author" in video_info:
    #         mp4 = MP4(output_file)
    #         mp4["\xa9gen"] = [video_info["author"]]
    #         mp4.save()
    with open(key_file, "w") as f:
        f.write(video['_keyname'])
    library.save_video_info(video['_keyname'])
    db.lpush("downloads", video['_keyname'])

def get_video(video_id: str, destination: str, video_subdir: bool = True, only_audio: bool = False, itag: int = None, filename: str = None, channel_mode: bool = False):
    """
    download a single video
    """
    destination = Path(destination)
    if not destination.exists():
        destination.mkdir(parents=True)
    if cookies_path:
        print("Using cookies")
        video = yt_dlp.YoutubeDL({
            "cookiefile": cookies_path
        }).extract_info(video_id, download=False)
    else:
        video = yt_dlp.YoutubeDL().extract_info(video_id, download=False)
    video_name = tools.sanitize_filename(video["title"])
    channel_name = video["uploader"] if "uploader" in video else "Unknown"
    if filename:
        video_name = filename
    video_name = tools.sanitize_filename(video_name)
    logger = Logging(video["id"]).get_logger()
    logger.info(f"Downloading video: {video_name} ...")
    if not only_audio:
        if video_subdir:
            if channel_mode:
                destination = destination.joinpath(channel_name)
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
                if cookies_path:
                    print("Using cookies")
                    yt_dlp.YoutubeDL({
                        "outtmpl": str(destination.joinpath(f"{video_name}.video")),
                        "logger": logger,
                        "format": video_format["format_id"],
                        "progress_hooks": [ydl_progress],
                        "cookiefile": cookies_path
                    }).download([video_id])
                else:
                    yt_dlp.YoutubeDL({
                        "outtmpl": str(destination.joinpath(f"{video_name}.video")),
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
            logger.warning("No audio streams found with language filter: %s, proceeding without filter" % language_filter)
            audio_streams = old_streams
    audio_streams = sorted(audio_streams, key=lambda x: x["abr"], reverse=True)
    audio_format = audio_streams[0]
    if cookies_path:
        print("Using cookies")
        yt_dlp.YoutubeDL({
            "outtmpl": str(destination.joinpath(f"{video_name}.audio")),
            "logger": logger,
            "format": audio_format["format_id"],
            "progress_hooks": [ydl_progress],
            "cookiefile": cookies_path
        }).download([video_id])
    else:
        yt_dlp.YoutubeDL({
            "outtmpl": str(destination.joinpath(f"{video_name}.audio")),
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
    # output_file = destination.joinpath(f"{video_name}.%s" % video_format["ext"])
    output_file = destination.joinpath(f"{video_name}.mp4")
    # final_file = destination.joinpath(f"{video_name}.mp4")

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
            ffmpeg.output(_v, _a, str(output_file), acodec='copy', vcodec='copy', strict="-2").run(capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            logger.error("Error merging audio and video streams: %s" % e)
            _p.unlink()
            destination.joinpath(".processing_error").touch()
            if db.exists(video_id):
                video_info = json.loads(db.get(video_id))
                video_info["error"] = "Failed to merge audio and video streams due to ffmpeg error."
                db.set(video_id, json.dumps(video_info))
            error_entry = {
                "item": {
                    "id": video_id,
                    "itag": itag,
                    "only_audio": only_audio
                }, 
                "error": str(e),
                "error_details": {
                    "stderr": e.stderr.decode("utf-8"),
                    "stdout": e.stdout.decode("utf-8")
                }
            }
            return False
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
            error_entry = {
                "item": {
                    "id": key_name,
                    "itag": itag,
                    "only_audio": only_audio
                }, 
                "error": str(e)
            }
            db.lpush("errors", json.dumps(error_entry))
            return False
            
        video_file.unlink()
        audio_file.unlink()
        _p.unlink()
        _pd.touch()
        # Write genre tag to video file
        #     output_file.unlink()
        # else:
        #     shutil.move(str(output_file), str(final_file))

    full_url = f"https://www.youtube.com/watch?v={video['id']}"
    key_name = f"video:{sha1(full_url.encode('utf-8')).hexdigest()}"
    if not only_audio:
        if "uploader" in video:
            mp4 = MP4(output_file)
            mp4["\xa9gen"] = [video["uploader"]]
            mp4.save()
        else:
            video_info = json.loads(db.get(key_name))
            if "author" in video_info:
                mp4 = MP4(output_file)
                mp4["\xa9gen"] = [video_info["author"]]
                mp4.save()
    key_file = destination.joinpath(f".key")
    with open(key_file, "w") as f:
        f.write(key_name)
    library.save_video_info(key_name)
    db.lpush("downloads", key_name)

# def get_playlist_videos(playlist_id: str, destination: str, only_audio: bool = False):
#     """
#     download all videos in a playlist
#     """
#     destination = Path(destination)
#     if not destination.exists():
#         destination.mkdir(parents=True)
#     playlist = yt_dlp.YoutubeDL().extract_info(playlist_id, download=False)
#     logger = Logging(video.video_id).get_logger()
#     logger.info(f"Downloading playlist: {playlist.title}")
#     # destination = destination.joinpath(playlist.title)
#     for i, video in enumerate(playlist.video_urls):
#         get_video(video, destination, only_audio=only_audio)
#         # video.download(destination=destination, resolution="720p"
#     full_url = f"https://www.youtube.com/playlist?list={playlist.playlist_id}"
#     key_name = f"playlist:{sha1(full_url.encode('utf-8')).hexdigest()}"
#     db.lpush("downloads", key_name)

def get_playlist_info(playlist_id: str, bust_cache: bool = False):
    """
    Get playlist info from YouTube and cache it in Redis for 24 hours.
    """
    hashed_url = sha1(playlist_id.encode("utf-8")).hexdigest()
    key_name = f"playlist:{hashed_url}"
    if db.exists(key_name):
        if not bust_cache:
            info = json.loads(db.get(key_name))
            if info["_pull_time"] + 86400 > int(datetime.now().timestamp()):
                info["_keyname"] = key_name
                return info
        else:
            db.delete(key_name)
    # playlist = Playlist(playlist_id)
    playlist = yt_dlp.YoutubeDL({
        "ignoreerrors": True,
        "cookiefile": cookies_path,
        "extract_flat": "in_playlist"
    }).extract_info(playlist_id, download=False)
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
        # "videos": [get_video_info(video['original_url'], video, bust_cache=bust_cache) for video in playlist['entries'] if video]
        "videos": [video["id"] for video in playlist['entries'] if video]
    }
    # info["thumbnail"] = info["videos"][0]["thumbnail"]
    info["_type"] = "playlist"
    info["_youtube"] = True
    info["_pull_time"] = int(datetime.now().timestamp())
    info_dump = json.dumps(info)
    db.set(key_name, info_dump)
    info["_keyname"] = key_name
    return info

def get_video_info(video_id: str, entry: dict = None, bust_cache: bool = False):
    """
    Get video info from YouTube and cache it in Redis for 24 hours.
    """
    # parsed_url = urlparse(video_id)
    # _yt = True
    # if parsed_url.netloc == "www.youtube.com":
    #     parsed_args = parse_qs(parsed_url.query)
    #     real_id = parsed_args["v"][0]
    #     hashed_url = sha1(video_id.encode("utf-8")).hexdigest()
    #     key_name = f"video:{hashed_url}"
    # else:
    #     _yt = False
    #     real_id = video_id
    #     hashed_url = sha1(video_id.encode("utf-8")).hexdigest()
    #     key_name = f"video:{hashed_url}"
    original_formats_by_itag = {}
    if video_id.startswith("video:"):
        key_name = video_id
        cached = True
        bust_cache = False
    else:
        cached = False
        parsed_url = urlparse(video_id)
        parsed_args = parse_qs(parsed_url.query)
        key_name, _yt = library.get_keyname(video_id)
        if _yt:
            real_id = parsed_args["v"][0]
        else:
            real_id = video_id
    if db.exists(key_name):
        info = json.loads(db.get(key_name))
        if library.thumbnail_exists(info["title"]):
            info["thumbnail"] = f"/api/v1/thumbnail/{info['_keyname']}/"
        if (info["_pull_time"] + 86400 > int(datetime.now().timestamp())) or cached:
            info["_keyname"] = key_name
            info["_downloaded"] = library.media_exists(info["title"])
            if not bust_cache:
                db.set(key_name, json.dumps(info))
                return info
            else:
                db.delete(key_name)
    else:
        if cached:
            raise KeyError("Video not found in cache")
    try:
        # print("Getting video info (%s) ..." % video_id)
        # video = YouTube(video_id)
        if entry:
            video = entry
        else:
            if cookies_path:
                print("Using cookies")
                if not Path(cookies_path).exists():
                    print(f"Warning: {cookies_path} does not exist.")
                video = yt_dlp.YoutubeDL({
                    "cookiefile": cookies_path
                }).extract_info(video_id, download=False)
            else:
                video = yt_dlp.YoutubeDL().extract_info(video_id, download=False)
            # video = yt_dlp.YoutubeDL().extract_info(video_id, download=False)
        video_name = tools.sanitize_filename(video["title"])
        format_pairs = []
        streams = []
        invalid_streams = []
        # original_formats_by_itag = { stream["format_id"]: stream for stream in video["formats"] }
        for stream in video["formats"]:
            # if "format_note" not in stream:
            #     print(stream)
            #     continue
            # if stream["format_note"] == "tiny":
            #     continue
            format_note = "%sp@%s (%s)" % (stream["height"], stream["fps"], stream["video_ext"]) if "height" in stream else "audio only"
            if "resolution" in stream and stream["resolution"] is not None:
                if stream["video_ext"] not in format_filter:
                    invalid_streams.append({
                        "itag": stream["format_id"],
                        "mime_type": stream["video_ext"],
                        "height": stream["height"] if "height" in stream else None,
                        "resolution": stream["resolution"],
                        "format": stream["format_note"] if "format_note" in stream else None,
                        "fps": stream["fps"] if "fps" in stream else None,
                        "url": stream["url"]
                    })
                    continue
                if stream["height"] not in resolution_filter:
                    invalid_streams.append({
                        "itag": stream["format_id"],
                        "mime_type": stream["video_ext"],
                        "height": stream["height"] if "height" in stream else None,
                        "resolution": stream["resolution"],
                        "format": stream["format_note"] if "format_note" in stream else None,
                        "fps": stream["fps"] if "fps" in stream else None,
                        "url": stream["url"]
                    })
                    continue
                format_pair = "%s/%s" % (stream["resolution"], stream["video_ext"])
                if format_pair in format_pairs:
                    invalid_streams.append({
                        "itag": stream["format_id"],
                        "mime_type": stream["video_ext"],
                        "height": stream["height"],
                        "resolution": stream["resolution"],
                        "format": stream["format_note"] if "format_note" in stream else None,
                        "fps": stream["fps"] if "fps" in stream else None,
                        "url": stream["url"]
                    })
                    continue
                format_pairs.append(format_pair)

                streams.append({
                    "itag": stream["format_id"],
                    "mime_type": stream["video_ext"],
                    "height": stream["height"],
                    "resolution": stream["resolution"],
                    "format": stream["format_note"] if "format_note" in stream else stream["format"] if "format" in stream else None,
                    "fps": stream["fps"] if "fps" in stream else None,
                    "url": stream["url"]
                })
            for stream in video["formats"]:
                if "format_id" in stream:
                    original_formats_by_itag[stream["format_id"]] = {
                        "itag": stream["format_id"],
                        "mime_type": stream["video_ext"],
                        "height": stream["height"] if "height" in stream else None,
                        "resolution": stream["resolution"],
                        "format": stream["format_note"] if "format_note" in stream else None,
                        "fps": stream["fps"] if "fps" in stream else None,
                        "url": stream["url"]
                    }

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
            "_youtube": _yt,
            "_error": str(e)
        }

    if _yt:
        info = {
            "id": video["id"],
            "_keyname": key_name,
            "_youtube": True,
            # "title": video["title"].replace(",", "").replace("|", "").replace("/", ""), shouldn't need to do this anymore (minus slashes)
            "original_title": video_name,
            "title": video_name,
            "description": video["description"],
            "thumbnail": video["thumbnail"],
            "author": video["uploader"],
            "length": video["duration"],
            "views": video["view_count"],
            "rating": video["average_rating"],
            "publish_date": datetime.strptime(video["upload_date"], "%Y%m%d").timestamp(),
            "keywords": video["tags"],
            "streams": streams,
            "invalid_streams": invalid_streams,
            "original_formats": original_formats_by_itag
        }
    else:
        uploader = "Unknown"
        if "uploader" in video:
            uploader = video["uploader"]
        if "author" in video:
            uploader = video["author"]
        info = {
            "id": video["id"],
            # Remove commas due to plex bug which causes incorrect 
            # media to be returned when title contains comma.
            "_keyname": key_name,
            "_youtube": False,
            "_url": video_id,
            "original_title": video_name,
            # "title": video["title"].replace(",", "").replace("|", "").replace("/", ""),
            "title": video_name,
            "description": video["description"] if "description" in video else None,
            "thumbnail": video["thumbnail"] if "thumbnail" in video else None,
            "author": uploader,
            "length": video["duration"] if "duration" in video else None,
            "publish_date": datetime.strptime(video["upload_date"], "%Y%m%d").timestamp() if "upload_date" in video else None,
            "host": parsed_url.netloc,
            "streams": streams,
            "invalid_streams": invalid_streams,
            "original_formats": original_formats_by_itag
        }
    info["_type"] = "video"
    info["_pull_time"] = int(datetime.now().timestamp())
    for k, v in info.items():
        print(f"{k}: {type(v)}")
        if isinstance(v, dict):
            for k2, v2 in v.items():
                print(f"    {k2}: {type(v2)}")
    info_dump = json.dumps(info)
    db.set(key_name, info_dump)
    info["_downloaded"] = library.media_exists(info["title"])
    info["_unavailable"] = False
    return info
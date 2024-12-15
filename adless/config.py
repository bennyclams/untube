from pathlib import Path
import redis
import os


db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
video_dir = Path(os.getenv("VIDEO_DIR", "/tmp/untube"))
format_filter = os.getenv("FORMAT_FILTER", None)
audio_dir = Path(os.getenv("AUDIO_DIR", "/tmp/untube"))
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
cookies_path = os.getenv("COOKIES_PATH", None)
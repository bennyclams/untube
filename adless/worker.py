from clilib.builders.app import EasyCLI
from adless.tools import get_playlist_info, get_video, get_playlist_videos
from pathlib import Path
import redis
import time
import json
import os

db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
video_dir = os.getenv("VIDEO_DIR", "/tmp/untube")
audio_dir = os.getenv("AUDIO_DIR", "/tmp/untube")
audio_storage_format = os.getenv("AUDIO_FILENAME", "{title}")
video_dir = Path(video_dir)
audio_dir = Path(audio_dir)
if not audio_dir.exists():
    audio_dir.mkdir(parents=True)
if not video_dir.exists():
    video_dir.mkdir(parents=True)
    

def worker():
    """
    UnTube worker process which downloads and processes videos from the download queue.
    """
    try:
        print("Starting UnTube worker...")
        while True:
            qi = db.lpop("download_queue")
            if qi:
                item = json.loads(qi)
                if "only_audio" not in item:
                    item["only_audio"] = False
                key_name = item["id"]
                info = json.loads(db.get(key_name))
                if info["_type"] == "video":
                    full_url = f"https://www.youtube.com/watch?v={info['id']}"
                    get_video(full_url, audio_dir if item["only_audio"] else video_dir, itag=item["itag"], only_audio=item["only_audio"])
                elif info["_type"] == "playlist":
                    full_url = f"https://www.youtube.com/playlist?list={info['id']}"
                    get_playlist_videos(full_url, audio_dir if item["only_audio"] else video_dir, only_audio=item["only_audio"])
                else:
                    print(f"[{info['id']}] Warning: Invalid type: {info['_type']}")
                    continue
                # db.delete(key_name)
            else:
                print("Download queue empty. Sleeping for 5 seconds...")
                time.sleep(5)

    except KeyboardInterrupt:
        print("UnTube Worker Exiting...")
        exit(0)

if __name__ == "__main__":
    EasyCLI(worker)

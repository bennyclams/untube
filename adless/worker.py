from clilib.builders.app import EasyCLI
from adless.tools import get_video, get_playlist_videos
from pathlib import Path
import redis
import time
import json
import os

db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
media_dir = os.getenv("MEDIA_DIR", "/tmp/untube")
media_dir = Path(media_dir)
if not media_dir.exists():
    media_dir.mkdir(parents=True)

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
                key_name = item["id"]
                info = json.loads(db.get(key_name))
                if info["_type"] == "video":
                    full_url = f"https://www.youtube.com/watch?v={info['id']}"
                    get_video(full_url, media_dir, itag=item["itag"])
                elif info["_type"] == "playlist":
                    full_url = f"https://www.youtube.com/playlist?list={info['id']}"
                    get_playlist_videos(full_url, media_dir)
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

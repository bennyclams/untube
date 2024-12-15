from clilib.builders.app import EasyCLI
from adless.config import db, video_dir, audio_dir
# from adless.tools import find_removed, fix_channel_tags, get_playlist_info, get_video, get_off_youtube_video, prune_removed, save_video_info
from pathlib import Path
import shutil
import redis
import time
import json
import os

from adless.download import get_off_youtube_video, get_video
from adless.library import fix_channel_tags, prune_removed, save_video_info

# db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
# video_dir = os.getenv("VIDEO_DIR", "/tmp/untube")
# audio_dir = os.getenv("AUDIO_DIR", "/tmp/untube")
global_channel_mode = os.getenv("CHANNEL_MODE", "false").lower() == "true"
audio_storage_format = os.getenv("AUDIO_FILENAME", "{title}")
# video_dir = Path(video_dir)
# audio_dir = Path(audio_dir)
if not audio_dir.exists():
    audio_dir.mkdir(parents=True)
if not video_dir.exists():
    video_dir.mkdir(parents=True)
    

def process_download(item):
    item = json.loads(item)
    if "only_audio" not in item:
        item["only_audio"] = False
    key_name = item["id"]
    db.set("in_progress", key_name)
    info = json.loads(db.get(key_name))
    if info["_youtube"]:
        if info["_type"] == "video":
            full_url = f"https://www.youtube.com/watch?v={info['id']}"
            channel_mode = item.get("channel_mode", global_channel_mode)
            get_video(full_url, audio_dir if item["only_audio"] else video_dir, itag=item["itag"], only_audio=item["only_audio"], channel_mode=channel_mode)
        # Playlists are queued as single videos now 
        # elif info["_type"] == "playlist":
        #     full_url = f"https://www.youtube.com/playlist?list={info['id']}"
        #     get_playlist_videos(full_url, audio_dir if item["only_audio"] else video_dir, only_audio=item["only_audio"])
        else:
            print(f"[{info['id']}] Warning: Invalid type: {info['_type']}")
            return
    else:
        get_off_youtube_video(item["id"], video_dir, itag=item["itag"])
    db.delete("in_progress")
    
def process_delete(item):
    video_path = video_dir / item
    print(f"Deleting {video_path} ...")
    if video_path.exists():
        # key_path = video_path / ".key"
        # # if key_path.exists():
        # #     video_id = key_path.read_text()
        # #     db.delete(video_id)
        shutil.rmtree(video_path)
    else:
        print(f"{video_path} does not exist.")

def process_maintenance(item):
    item = json.loads(item)
    if item["action"] == "write_channels":
        fix_channel_tags()
    elif item["action"] == "prune_removed":
        prune_removed()
    elif item["action"] == "save_video_info":
        prune_removed()
        video_ids = db.keys("video:*")
        for video_id in video_ids:
            save_video_info(video_id.decode("utf-8"))
    else:
        raise ValueError(f"Invalid maintenance action: {item['action']}")

def worker():
    """
    UnTube worker process which downloads and processes videos from the download queue.
    """
    try:
        print("Starting UnTube worker...")
        db.set("downloads_since_restart", 0)
        while True:
            qi = db.lpop("maintenance_queue")
            if qi:
                try:
                    print(f"Processing maintenance item: {qi}")
                    process_maintenance(qi)
                except Exception as e:
                    print(f"Error processing maintenance item: {qi}")
                    print(e)
                    db.lpush("errors", json.dumps({"item": json.loads(qi), "error": str(e)}))
            qi = db.lpop("download_queue")
            if qi:
                try:
                    process_download(qi)
                    db.incr("downloads_since_restart")
                except Exception as e:
                    print(f"Error processing item: {qi}")
                    print(e)
                    db.lpush("errors", json.dumps({"item": json.loads(qi), "error": str(e)}))
            else:
                print("Download queue empty. Checking delete queue...")
            dqi = db.lpop("delete_queue")
            if dqi:
                process_delete(dqi.decode("utf-8"))
            else:
                print("Delete queue empty. Sleeping...")
                time.sleep(5)

    except KeyboardInterrupt:
        print("UnTube Worker Exiting...")
        exit(0)

if __name__ == "__main__":
    EasyCLI(worker)

from adless.tools import sanitize_filename
from adless.config import db, video_dir
from urllib.parse import urlparse
from adless import download
from hashlib import sha1
from mutagen.mp4 import MP4
import base64
import shutil
import json
import os


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
            "author": "Unknown",
            "length": "Unknown",
            "type": "video",
            "thumbnail": thumb_url,
        })
    return downloads

def thumbnail_exists(title: str):
    """
    Check if a given media has a thumbnail.
    """
    path = video_dir.joinpath(title)
    if path.joinpath(f"{title}.jpg").exists():
        return True
    return False

def media_exists(title: str):
    """
    Check if a given media exists in the Plex library.
    """
    downloads = get_fs_downloads()
    for download in downloads:
        if download["title"] == title:
            return True
    return False

def find_existing_channels():
    """
    Find all existing channels on the filesystem.
    """
    downloads = get_fs_downloads()
    channels = []
    for download in downloads:
        if download["author"] is None:
            download["author"] = "Unknown"
        if download["author"] not in channels and download["author"] != "Unknown":
            channels.append(download["author"])
    return channels

def fix_channel_tags():
    """
    Fix channel tags for all videos on the filesystem.
    """
    downloads = get_fs_downloads()
    for download in downloads:
        key_name = download["_keyname"]
        if db.exists(key_name):
            video_info = json.loads(db.get(key_name))
            if "author" in video_info:
                video_path = video_dir / sanitize_filename(video_info['title']) / f"{sanitize_filename(video_info['title'])}.mp4"
                mp4 = MP4(video_path)
                if video_info["author"] is None:
                    video_info["author"] = "Unknown"
                if video_info["author"] not in mp4["\xa9gen"]:
                    mp4["\xa9gen"] = [video_info["author"]]
                    print(f"Fixed channel tag for {video_info['title']}")
                else:
                    print(f"Channel tag already correct for {video_info['title']}")
                mp4.save()

def save_video_info(video_id: str):
    """
    Save cached info to disk
    """
    if not video_id.startswith("video:"):
        key_name, _yt = get_keyname(video_id)
    else:
        key_name = video_id
    if db.exists(key_name):
        video_info = json.loads(db.get(key_name))
        with open(video_dir.joinpath(sanitize_filename(video_info["title"]), ".info"), "w") as f:
            f.write(json.dumps(video_info))

def find_removed():
    """
    Find videos which have been removed from the filesystem
    but still exist in the database.
    """
    existing_keys = db.keys("video:*")
    downloads = get_fs_downloads()
    dl_keys = [d["_keyname"] for d in downloads]
    removed = []
    for key in existing_keys:
        if key not in dl_keys:
            removed.append(key)
    return removed

def prune_removed():
    """
    Prune videos which have been removed from the filesystem
    but still exist in the database.
    """
    removed_keys = find_removed()
    for key in removed_keys:
        db.delete(key)

def move_video(video_id: str, new_title: str):
    """
    Move a video to a new title.
    """
    keyname, _yt = get_keyname(video_id)
    if db.exists(keyname):
        video_info = json.loads(db.get(keyname))
        old_title = video_info["title"]
        old_path = video_dir.joinpath(old_title)
        new_path = video_dir.joinpath(new_title)
        if new_path.exists():
            return False
        old_path_files = [f for f in old_path.iterdir()]
        for f in old_path_files:
            shutil.copy2(f, new_path)
            os.unlink(f)
        old_path.rmdir()
        return True
    return False

def get_keyname(video_id: str):
    """
    Get the Redis keyname for a given video ID (video URL).
    """
    parsed_url = urlparse(video_id)
    _yt = True
    if parsed_url.netloc == "www.youtube.com":
        # parsed_args = parse_qs(parsed_url.query)
        hashed_url = sha1(video_id.encode("utf-8")).hexdigest()
        key_name = f"video:{hashed_url}"
    else:
        _yt = False
        # real_id = video_id
        hashed_url = sha1(video_id.encode("utf-8")).hexdigest()
        key_name = f"video:{hashed_url}"
    return key_name, _yt

def update_video_info(video_id: str, new_info: dict = None, bust_cache: bool = False):
    """
    Update video info in Redis.
    """
    keyname, _yt = get_keyname(video_id)
    cached_info = None
    video_info = None
    original_name = None
    if db.exists(keyname):
        cached_info = json.loads(db.get(keyname))
        original_name = cached_info["title"]
    if cached_info:
        video_info = cached_info
        if bust_cache:
            try:
                video_info = download.get_video_info(video_id, bust_cache=bust_cache)
            except Exception as e:
                print("Error pulling video info: %s, falling back on cache..." % e)
                video_info = cached_info
    else:
        video_info = download.get_video_info(video_id)
    # old_info = video_info.copy()
    if new_info:
        video_info.update(new_info)
        if new_info["title"] != original_name:
            shutil.move
    
    key_name = video_info["_keyname"]
    db.set(key_name, json.dumps(video_info))
    return video_info

def key_exists(key: str):
    """
    Check if a key exists in Redis.
    """
    return db.exists(key)
from tempfile import NamedTemporaryFile
from b2sdk.v2 import B2Api
import redis
import json
import os

from adless.library import key_exists


db = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379").strip())
bucket_name = os.getenv("ARCHIVE_BUCKET_NAME", "my-bucket")
bucket_prefix = os.getenv("ARCHIVE_BUCKET_PREFIX", "youtube/")
if not bucket_prefix.endswith("/"):
    bucket_prefix += "/"
b2_key_id = os.getenv("B2_APPLICATION_KEY_ID", None)
b2_application_key = os.getenv("B2_APPLICATION_KEY", None)
b2_api = B2Api()
if b2_key_id and b2_application_key: 
    b2_api.authorize_account("production", b2_key_id, b2_application_key)


def list_archive_files():
    """
    List the files in the archive with the specified prefix.
    """
    bucket = b2_api.get_bucket_by_name(bucket_name)
    bucket_files = bucket.ls(bucket_prefix, recursive=True)
    # return bucket_files
    archive_items = {}
    for f in bucket_files:
        # print(f[1])
        file_name_parts = f[0].file_name.split("/")
        media_name = file_name_parts[1]
        file_name = file_name_parts[2]
        if media_name not in archive_items:
            archive_items[media_name] = []
        archive_items[media_name].append({
            "file_name": file_name,
            "file_size": f[0].size,
            "file_id": f[0].id_,
        })
    return archive_items

def get_archived_media(author: str = None):
    """
    Get archived media and associate with media information if available.
    """
    archive_items = list_archive_files()
    media_info = {}
    channels = []
    for media_name, files in archive_items.items():
        info = None
        for f in files:
            if f["file_name"] == ".info":
                if not key_exists(f"archive:{media_name}:info:{f['file_id']}"):
                    info = json.loads(get_file_contents(f["file_id"]))
                    db.set(f"archive:{media_name}:info:{f['file_id']}", json.dumps(info))
                else:
                    info = json.loads(db.get(f"archive:{media_name}:info:{f['file_id']}"))
                # f["info"] = info
                break
            if f["file_name"] == ".key":
                if not key_exists(f"archive:{media_name}:key:{f['file_id']}"):
                    key_content = get_file_contents(f["file_id"])
                    db.set(f"archive:{media_name}:key:{f['file_id']}", key_content)
                else:
                    key_content = db.get(f"archive:{media_name}:key:{f['file_id']}")
                if key_exists(key_content):
                    f["cached"] = True
                    info = json.loads(db.get(key_content))
        if not info:
            if key_exists(key_content):
                info = json.loads(db.get(key_content))
        if info:
            if "author" in info:
                if info["author"] not in channels:
                    channels.append(info["author"])
            if author:
                if info["author"] == author:
                    media_info[media_name] = info
            else:
                media_info[media_name] = info
    return media_info, channels

def get_file_contents(file_id: str):
    """
    Get the contents of a file from the B2 bucket using its file ID.
    :param file_id: The ID of the file to retrieve.
    :return: The contents of the file.
    """
    bucket = b2_api.get_bucket_by_name(bucket_name)
    file_info = bucket.get_file_info_by_id(file_id)
    with NamedTemporaryFile() as temp_file:
        dld = file_info.download()
        dld.save_to(temp_file.name)
        # temp_file.seek(0)
        return temp_file.read()
    
def fetch_media_key(media_name: str):
    """
    Fetch the media key for the specified media name from the archive.
    :param media_name: The name of the media to fetch the key for.
    :return: The media key.
    """
    archive_items = list_archive_files()
    if media_name in archive_items:
        for item in archive_items[media_name]:
            if item["file_name"] == ".key":
                return get_file_contents(item["file_id"])
            
def upload_video_info(media_name: str, video_info: dict):
    """
    Upload video information to the archive.
    :param media_name: The name of the media to upload information for.
    :param video_info: The video information to upload.
    """
    bucket = b2_api.get_bucket_by_name(bucket_name)
    file_name = f"{bucket_prefix}{media_name}/video_info.json"
    bucket.upload_bytes(json.dumps(video_info).encode("utf-8"), file_name)
    
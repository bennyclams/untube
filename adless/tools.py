from urllib.parse import parse_qs, urlparse

from flask import current_app
from adless import download
import requests
import re
import os


def escape_ansi(line):
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', line).strip()

def sanitize_filename(filename: str):
    """
    Sanitize a filename to remove invalid characters.
    """
    return filename.replace("/", "-").replace(":", "-").replace("?", "").replace("!", "").replace("&", "-").replace("%", "-").replace("”", "").strip()

def get_video_title(video_id: str):
    """
    Get the title of a video from its ID.
    """
    try:
        video_info = download.get_video_info(video_id)
        return video_info["title"]
    except Exception as e:
        print(e)
        return None

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

def archive_request(archive_url: str, media_library: str, media_name: str):
    """
    Submit a request to archive a media item.
    """
    archive_url = "%s/api/v1/archive"
    archive_key = current_app.config['ARCHIVE_API_KEY']
    request_data = {
        "media_library": media_library,
        "media_name": media_name,
    }
    headers = {
        "Authorization": f"Bearer {archive_key}"
    }
    res = requests.post(archive_url, json=request_data, headers=headers)
    return res.json()

def sizeof_fmt(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

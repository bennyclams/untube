# Untube

Untube is a simple web application that allows you to quickly download videos and playlists from YouTube and save them locally. 
Untube uses flask for the web backend, and yt-dlp for accessing the YouTube API. Currently, there is no way to 
download privated videos, videos which are for members only, or private playlists. Untube now supports videos on other platforms
as long as you can provide the m3u8 link to the video. This allows you to download whole VODs from twitch, as well as videos from 
member sites like Patreon or Fourthwall creator sites.

Untube will allow you to download either the best available quality video, or you can choose from a list of available formats. 
You are able to set a filter via environment variable for formats as well as resolutions, to keep the list of available streams 
less cluttered. Some youtube channels have audio streams in multiple languages, so there's also an optional language filter. If
you do not specify a language filter, the worker will not differentiate between audio streams in different languages.

The Untube worker will download both the video and audio stream of the video, and then merge them with ffmpeg. 
The merge uses a copy, which should be fine in most scenarios, but if you have issues with the merge, please open an issue.

For off-youtube videos, the worker will attempt to automatically generate a thumbnail for the video with ffmpeg. If this fails,
the worker will continue and leave a message in the log indicating that the thumbnail could not be generated along with an error.

## Future Plans

    * Add support for downloading private videos and playlists

## Quickstart
The easiest way to get started is to just run the docker-compose provided and mount the plex media directory you want to use for
your downloads as the media directory set in the worker's environment. The web interface is accessible via port 8000 by default, and
the default admin password is just 'password'. You can change this by setting the environment variable `ADMIN_PASSWORD`.

## Mobile
Untube is mobile friendly, and the UI is the same as the desktop version. On Android devices, you can install Untube as a PWA which
will allow you to use the system share dialog to share videos directly from YouTube to Untube. This will automatically open the Untube
PWA to the video or playlist info page, which will allow you to download the video or playlist.

## Configuration

Variable | Description | Default
--- | --- | ---
ADMIN_PASSWORD | Password for the admin user | `password`
REDIS_URL | Redis URL for data storage | `redis://localhost:6379`
VIDEO_DIR | Directory to store downloaded videos | `/tmp/untube`
FORMAT_FILTER | Filter for available formats | `["mp4", "webm", "ogg", "flv", "3gp", "mkv", "m4a"]`
RESOLUTION_FILTER | Filter for available resolutions | `[2160, 1920, 1440, 1280, 1080, 960, 720, 480]`
LANGUAGE_FILTER | Filter for available languages | `None`

Note: Any environment variable which can accept multiple values needs to be specified in a comma separated list of values. For example,
`FORMAT_FILTER=mp4,webm,ogg,flv,3gp,mkv,m4a`
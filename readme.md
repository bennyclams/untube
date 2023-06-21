# Untube

Untube is a simple web application that allows you to quickly download videos and playlists from YouTube and save them locally. 
Untube uses flask for the web backend, and pytube for accessing the YouTube API. Currently, there is no way to 
download privated videos, videos which are for members only, or private playlists.

Untube will allow you to download either the best available quality video, or you can choose from a list of available formats. Currently,
the only supported/queried format is webm. The Untube worker will download both the video and audio stream of the video, and then merge
them with ffmpeg. The merge uses a copy, which should be fine in most scenarios, but if you have issues with the merge, please open an issue.

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
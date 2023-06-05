from plexapi.server import PlexServer
import os

server_url = os.getenv("PLEX_URL", "http://localhost:32400")
plex_library = os.getenv("PLEX_LIBRARY", "Youtube")
server_token = os.getenv("PLEX_TOKEN", "")

def media_exists(media: str):
    """
    Check if a given media exists in the Plex library.
    """
    plex = PlexServer(server_url, server_token)
    try:
        plex.library.section(plex_library).get(media)
        return True
    except:
        return False
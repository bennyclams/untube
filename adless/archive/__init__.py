from sys import prefix
from tempfile import NamedTemporaryFile
from b2sdk.v2 import B2Api
import os

bucket_name = os.getenv("ARCHIVE_BUCKET_NAME", "my-bucket")
bucket_prefix = os.getenv("ARCHIVE_BUCKET_PREFIX", "youtube/")
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
    
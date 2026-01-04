import os

PERSISTENT_STORAGE_DIR = os.path.join(os.path.dirname(__file__), ".persistent_storage")


def get_filename(filename: str) -> str:
    """Get the full path to a cache file."""
    if not os.path.exists(PERSISTENT_STORAGE_DIR):
        os.makedirs(PERSISTENT_STORAGE_DIR)

    full_name = os.path.join(PERSISTENT_STORAGE_DIR, filename)
    directory = os.path.dirname(full_name)
    if not os.path.exists(directory):
        os.makedirs(directory)

    return full_name


def get_directory(dirname: str) -> str:
    """Get the current persistent storage directory."""
    dir = os.path.join(PERSISTENT_STORAGE_DIR, dirname)
    if not os.path.exists(dir):
        os.makedirs(dir)
    return dir


def set_persistent_storage_dir(path: str) -> None:
    """Set a new persistent storage directory."""
    global PERSISTENT_STORAGE_DIR
    PERSISTENT_STORAGE_DIR = path

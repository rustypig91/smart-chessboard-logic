import os
import pickle
import chessboard.events as events

PERSISTENT_STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".persistent_storage"))


def get_filename(*filename_parts) -> str:
    """Get the full path to a cache file."""
    full_name = os.path.join(PERSISTENT_STORAGE_DIR, *filename_parts)
    directory = os.path.dirname(full_name)
    os.makedirs(directory, exist_ok=True)

    return full_name


def get_directory(dirname: str) -> str:
    """Get the current persistent storage directory."""
    dir = os.path.join(PERSISTENT_STORAGE_DIR, dirname)
    os.makedirs(dir, exist_ok=True)
    return dir


def set_persistent_storage_dir(path: str) -> None:
    """Set a new persistent storage directory."""
    global PERSISTENT_STORAGE_DIR
    PERSISTENT_STORAGE_DIR = path


class PersistentClass:
    """ A base class for classes that can be persisted to disk. """

    def __init__(self):
        events.event_manager.subscribe(events.SaveEvent, self._handle_save_event)

    def _handle_save_event(self, _: events.SaveEvent):
        savefile = get_filename(f"{self.__class__.__name__}.pkl")
        new_data = pickle.dumps(self)
        try:
            with open(savefile, "rb") as f:
                old_data = f.read()
        except FileNotFoundError:
            old_data = None

        if old_data != new_data:
            with open(savefile, "wb") as f:
                f.write(new_data)

    @classmethod
    def load(cls):
        """ Load the object from persistent storage. """
        savefile = get_filename(f"{cls.__name__}.pkl")
        try:
            with open(savefile, "rb") as f:
                loaded = pickle.load(f)
                events.event_manager.subscribe(events.SaveEvent, loaded._handle_save_event)
                return loaded
        except Exception:
            return cls()

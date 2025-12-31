import json
import os
from typing import Any, Optional
from chessboard.logger import log
import chessboard.persistent_storage as persistent_storage


class ColorSetting(tuple):
    def __new__(cls, r: int | tuple[int, int, int] | list[int], g: Optional[int] = None, b: Optional[int] = None):
        """ A setting representing an RGB color. 

        r: Red component (0-255) or a tuple/list of (r, g, b)
        g: Green component (0-255)
        b: Blue component (0-255)
        """
        if isinstance(r, (list, tuple)):
            if len(r) != 3:
                raise ValueError("ColorSetting requires 3 components (r, g, b)")
            r, g, b = r
        if g is None or b is None:
            raise TypeError("ColorSetting expects r, g, b values")
        return super(ColorSetting, cls).__new__(cls, (int(r), int(g), int(b)))
    typename = "color"

    def to_json(self) -> dict:
        return {
            'value': (self[0], self[1], self[2])
        }


class _Setting:
    def __init__(self, name: str, default: Any, description: str = ""):
        self.name = name
        self._default = default
        self.value = default
        self.description = description
        self.type = type(default)

    @property
    def default(self) -> Any:
        return self._default

    def to_json(self) -> dict:
        return {
            'name': self.name,
            'value': self.value,
            'default': self.default,
            'description': self.description,
            'type': self.type.__name__
        }


class _Settings:
    def __init__(self, settings_file: str = 'settings.json'):
        self._settings: dict[str, _Setting] = {}
        self._settings_file: str = settings_file
        self._loaded_settings: dict[str, Any] = {}
        self._load()

    def __getitem__(self, key: str) -> Any:
        return self.get(key).value

    def __setitem__(self, key: str, value: object):
        self.set(key, value)

    @property
    def all_settings(self) -> dict[str, _Setting]:
        log.debug(f"Retrieving all settings: {self._settings}")
        return self._settings

    def get(self, key: str) -> _Setting:
        try:
            return self._settings[key]
        except KeyError as e:
            raise KeyError(f"Setting '{key}' not found") from e

    def register(self, key: str, default: object, description: str = ""):
        if key in self._settings:
            raise KeyError(f"Setting '{key}' is already registered")

        self._settings[key] = _Setting(key, default, description)

        if key in self._loaded_settings:
            self._settings[key].value = self._loaded_settings[key]
            log.info(f"Loaded setting '{key}' with value '{self._loaded_settings[key]}' from file")

        log.info(f"Registered setting '{key}' with default '{default}'")

    def set(self, key: str, value: object):
        if key not in self._settings:
            raise KeyError(f"Setting '{key}' not found")

        self._settings[key].value = value
        log.info(f"Set setting '{key}' to '{value}'")
        self._save()

    def _save(self):
        filename = persistent_storage.get_filename(self._settings_file)

        save_data = {}
        for key, setting in self._settings.items():
            if setting.value is not None and setting.value != setting.default:
                save_data[key] = setting.value

        with open(filename, 'w') as f:
            json.dump(save_data, f, indent=4)
        log.info(f"Saved settings to {filename}")

    def _load(self):
        filename = persistent_storage.get_filename(self._settings_file)
        try:
            with open(filename, 'r') as f:
                self._loaded_settings = json.load(f)
                log.info(f"Loaded settings from {filename}")
        except FileNotFoundError:
            log.info(f"Settings file {filename} not found, using defaults")

    def restore_defaults(self):
        for _, setting in self._settings.items():
            setting.value = setting.default
        log.info("Restored all settings to default values")
        self._save()


settings = _Settings()


if __name__ == "__main__":
    import tempfile
    with tempfile.NamedTemporaryFile() as temp_settings_file:
        settings = _Settings(settings_file=temp_settings_file.name)
        print("Current settings:", settings._settings)
        settings.set("leds.colors.test_color", (123, 45, 67))
        print("Updated settings:", settings._settings)

        print(f"leds.colors.test_color={settings['leds.colors.test_color']}")

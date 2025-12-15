import json
import os
from typing import Any
from chessboard.logger import log


class ColorSetting(tuple):
    def __new__(cls, r: int, g: int, b: int):
        return super(ColorSetting, cls).__new__(cls, (r, g, b))
    typename = "color"


class _Setting:
    def __init__(self, name: str, default: Any, description: str = ""):
        self.name = name
        self._default = default
        self.value = default
        self.description = description
        self.type = type(default).__name__

    @property
    def default(self) -> Any:
        return self._default

    def to_json(self) -> dict:
        return {
            'name': self.name,
            'value': self.value,
            'default': self.default,
            'description': self.description,
            'type': self.type
        }


class _Settings:
    def __init__(self, settings_file: str = '/var/lib/chessboard/settings.yaml'):
        self._settings: dict[str, _Setting] = {}
        self._settings_file: str = settings_file
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
        log.info(f"Registered setting '{key}' with default '{default}'")

    def set(self, key: str, value: object):
        if key not in self._settings:
            raise KeyError(f"Setting '{key}' not found")

        self._settings[key].value = value
        log.info(f"Set setting '{key}' to '{value}'")
        self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self._settings_file), exist_ok=True)

        with open(self._settings_file, 'w') as f:
            json.dump(self._settings, f, indent=4)

    def _load(self):
        self._settings = {}
        try:
            with open(self._settings_file, 'r') as f:
                if os.stat(self._settings_file).st_size == 0:
                    return
                self._settings.update(json.load(f))
                log.info(f"Loaded settings from {self._settings_file}")
        except FileNotFoundError:
            log.info(f"Settings file {self._settings_file} not found, using defaults")


settings = _Settings()


if __name__ == "__main__":
    import tempfile
    with tempfile.NamedTemporaryFile() as temp_settings_file:
        settings = _Settings(settings_file=temp_settings_file.name)
        print("Current settings:", settings._settings)
        settings.set("leds.colors.test_color", (123, 45, 67))
        print("Updated settings:", settings._settings)

        print(f"leds.colors.test_color={settings['leds.colors.test_color']}")

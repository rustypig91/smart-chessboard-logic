import chess
from chessboard.settings import settings
from chessboard.events import event_manager, TimeButtonPressedEvent
from chessboard.logger import log

import keyboard

settings.register("buttons.time_button_white_key", "enter")
settings.register("buttons.time_button_black_key", "space")


class _ButtonHandler:
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(_ButtonHandler, cls).__new__(cls)
            cls.instance._initialized = False

        return cls.instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        keyboard.on_press_key(settings['buttons.time_button_black_key'], self._on_black_button_press)
        keyboard.on_press_key(settings['buttons.time_button_white_key'], self._on_white_button_press)
        log.info("ButtonHandler initialized")

    def _on_white_button_press(self, _):
        time_button_event = TimeButtonPressedEvent(color=chess.WHITE)
        event_manager.publish(time_button_event)

    def _on_black_button_press(self, _):
        time_button_event = TimeButtonPressedEvent(color=chess.BLACK)
        event_manager.publish(time_button_event)


button_handler = _ButtonHandler()


if __name__ == '__main__':
    # Keep the program running to listen for events
    from time import sleep

    def on_time_button_pressed(event: TimeButtonPressedEvent):
        print(f"Time button pressed for color: {event.color}")

    event_manager.subscribe(
        TimeButtonPressedEvent, on_time_button_pressed)

    print("Listening for button presses. Press Ctrl+C to exit")
    while True:
        # Just keep the program running while listening for button presses
        sleep(1)

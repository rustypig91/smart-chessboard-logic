import asyncio
from collections.abc import Callable
import chess
from chessboard.logger import log
import time
import threading
import traceback
import atexit
import inspect


class Event:
    def __init__(self):
        self.sender = "Unknown"

    def _parse_color(self, color: chess.Color | str) -> chess.Color | None:
        if isinstance(color, str):
            if color.lower() == 'white':
                return chess.WHITE
            elif color.lower() == 'black':
                return chess.BLACK
            elif color.lower() == 'none':
                return None
            else:
                raise ValueError(f"Invalid color string: {color}")
        else:
            return color

    def to_json(self) -> dict:
        return self.__dict__


class SetSquareColorEvent(Event):
    """ Requests setting the color chess squares to specific RGB values. """

    def __init__(self, color_map: dict[chess.Square, tuple[int, int, int] | None]):
        """        
        color_map: A dictionary mapping squares to RGB color tuples or None to not change the led
        """
        self.color_map = color_map

    def __repr__(self):
        return f"LedChangeEvent(color_map={{ {', '.join(f'{chess.square_name(sq)}: {color}' for sq, color in self.color_map.items())} }})"


class SquarePieceStateChange(Event):
    def __init__(self, squares: list[chess.Square], colors: list[chess.Color | None | str]):
        self.squares = squares
        self.colors = [self._parse_color(color) if color is not None else None for color in colors]

    def __repr__(self):
        return f"SquarePieceStateChange(square={self.squares}, color={self.colors})"


class TimeButtonPressedEvent(Event):
    def __init__(self, color: chess.Color | str):
        self.color = self._parse_color(color)

    def __repr__(self):
        return f"TimeButtonPressedEvent(color={'white' if self.color == chess.WHITE else 'black'})"


class HalSensorVoltageEvent(Event):
    def __init__(self, square: chess.Square, voltage: float):
        self.square = square
        self.voltage = voltage


class ChessMoveEvent(Event):
    def __init__(self, move: chess.Move):
        self.move = move

    def to_json(self):
        return {
            "from_square": chess.square_name(self.move.from_square),
            "to_square": chess.square_name(self.move.to_square),
            "promotion": chess.piece_symbol(self.move.promotion) if self.move.promotion else None
        }


class ClockTickEvent(Event):
    def __init__(self, white_time_left: float, black_time_left: float, turn: chess.Color):
        self.white_time_left = white_time_left
        self.black_time_left = black_time_left
        self.turn = turn


class GameOverEvent(Event):
    def __init__(self, winner: chess.Color | None, reason: str):
        self.winner = winner
        self.reason = reason


class PlayerNotifyEvent(Event):
    def __init__(self, title: str, message: str):
        self.title = title
        self.message = message


class GameStartedEvent(Event):
    def __init__(self):
        pass


class GamePausedEvent(Event):
    def __init__(self):
        pass


class GameResumedEvent(Event):
    def __init__(self):
        pass


class _EventManager:
    def __init__(self):
        self._subscribers: dict[type[Event],
                                list[Callable]] = {}
        for event_type in Event.__subclasses__():
            self._subscribers[event_type] = []

        self._event_queue = asyncio.Queue()

        self._event_loop = asyncio.new_event_loop()
        self._event_task = self._event_loop.create_task(self._main())

        self._thread = threading.Thread(target=self.main, daemon=True)
        self._thread.start()

        log.info("EventManager initialized")

    def __del__(self):
        self.stop()

    def subscribe(self, event_type: type[Event], callback: Callable):
        if event_type not in self._subscribers:
            raise ValueError(f"Unknown event type: {event_type}")

        self._subscribers[event_type].append(callback)

    def subscribe_all_events(self, callback: Callable[[Event], None]):
        for event_type in Event.__subclasses__():
            self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: type[Event], callback: Callable):
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)

    def publish(self, event: Event):
        event.sender = inspect.stack()[1].frame.f_globals.get('__name__', 'Unknown')

        asyncio.run_coroutine_threadsafe(
            self._event_queue.put(event), self._event_loop)

    def _handle_event(self, event: Event):
        event_type = type(event)
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    callback(event)
                except Exception as e:
                    log.error(f"Error in event callback: {e}")
                    traceback.print_exc()

    async def _main(self):
        while True:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if not isinstance(event, HalSensorVoltageEvent):
                # Skip logging for high-frequency events
                log.debug(f"{type(event).__name__}: {event.to_json()}")

            self._handle_event(event)
            self._event_queue.task_done()

    def main(self):
        asyncio.set_event_loop(self._event_loop)
        self._event_loop.run_until_complete(self._event_task)

    def stop(self):
        if self._event_loop.is_running():
            self._event_task.cancel()
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2)
                self._thread = None
            log.info("EventManager stopped")


event_manager = _EventManager()
atexit.register(event_manager.stop)

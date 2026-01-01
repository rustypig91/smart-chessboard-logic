from collections.abc import Callable
from types import ModuleType
import chess
from chessboard.logger import log
import threading
import traceback
import atexit
import inspect
import queue


class Event:
    def __init__(self):
        self.sender: ModuleType | None = None
        # Used for blocking publish
        self._sync_event: threading.Event | None = None

    def _parse_color(self, color: chess.Color | str | None) -> chess.Color | None:
        if isinstance(color, str):
            if color.lower() == 'white':
                return chess.WHITE
            elif color.lower() == 'black':
                return chess.BLACK
            elif color.lower() == 'none':
                return None
            else:
                raise ValueError(f"Invalid color string: {color}")
        elif isinstance(color, chess.Color) or color is None:
            return color
        else:
            raise ValueError(f"Invalid color type: {type(color)}")

    def _color_to_str(self, color: chess.Color | None) -> str | None:
        if color is None:
            return None
        return 'white' if color == chess.WHITE else 'black'

    @staticmethod
    def _convert_to_json_value(value: object) -> object:
        if isinstance(value, float) and value == float('inf'):
            return 'inf'
        elif isinstance(value, chess.Board):
            return value.fen()
        elif isinstance(value, ModuleType):
            return value.__name__
        else:
            return value

    def to_json(self) -> dict:
        json_items = {}

        for key, value in self.__dict__.items():
            if key.startswith('_'):
                # Skip private attributes
                continue

            if isinstance(value, list) or isinstance(value, tuple):
                json_items[key] = [self._convert_to_json_value(v) for v in value]
            else:
                json_items[key] = self._convert_to_json_value(value)

        return json_items


class SetSquareColorEvent(Event):
    """ Requests setting the color chess squares to specific RGB values. """

    def __init__(self, color_map: dict[chess.Square, tuple[int, int, int]]):
        """
        color_map: A dictionary mapping squares to RGB color tuples or None to not change the led
        """
        super().__init__()
        self.color_map = color_map

    def __repr__(self):
        return f"LedChangeEvent(color_map={{ {', '.join(f'{chess.square_name(sq)}: {color}' for sq, color in self.color_map.items())} }})"


class SquarePieceStateChangeEvent(Event):
    def __init__(self, squares: list[chess.Square], colors: list[chess.Color | None | str]):
        super().__init__()
        self.squares = squares
        self.colors = [self._parse_color(color) for color in colors]

    def __repr__(self):
        return f"SquarePieceStateChangeEvent(square={self.squares}, color={self.colors})"

    def to_json(self):
        items = super().to_json()
        items['colors'] = [self._color_to_str(color) for color in self.colors]
        return items


class TimeButtonPressedEvent(Event):
    def __init__(self, color: chess.Color | str):
        super().__init__()

        parsed_color = self._parse_color(color)
        if parsed_color is None:
            raise ValueError("Color cannot be None for TimeButtonPressedEvent")

        self.color: chess.Color = parsed_color

    def __repr__(self):
        return f"TimeButtonPressedEvent(color={'white' if self.color == chess.WHITE else 'black'})"

    def to_json(self):
        items = super().to_json()
        items['color'] = self._color_to_str(self.color)
        return items


class ChessMoveEvent(Event):
    def __init__(self, move: chess.Move, side: chess.Color | str):
        super().__init__()
        self.move = move
        _side = self._parse_color(side)
        if _side is None:
            raise ValueError("Side cannot be None for ChessMoveEvent")
        self.side = _side

    def to_json(self):
        return {
            "from_square": chess.square_name(self.move.from_square),
            "to_square": chess.square_name(self.move.to_square),
            "promotion": chess.piece_symbol(self.move.promotion) if self.move.promotion else None
        }


class GameOverEvent(Event):
    def __init__(self, winner: chess.Color | None | str, reason: str):
        super().__init__()
        self.winner = self._parse_color(winner)
        self.reason = reason


class PlayerNotifyEvent(Event):
    def __init__(self, title: str, message: str):
        super().__init__()
        self.title = title
        self.message = message


class GameStartedEvent(Event):
    def __init__(self):
        super().__init__()


class GamePausedEvent(Event):
    def __init__(self):
        super().__init__()


class GameResumedEvent(Event):
    def __init__(self):
        super().__init__()


class SystemShutdownEvent(Event):
    def __init__(self):
        super().__init__()


class NewGameEvent(Event):
    def __init__(self, white_player: str, black_player: str, start_time_seconds: tuple[float, float], increment_seconds: tuple[float, float]):
        super().__init__()
        self.white_player = white_player
        self.black_player = black_player
        self.start_time_seconds = start_time_seconds
        self.increment_seconds = increment_seconds


class ChessClockStateChangedEvent(Event):
    def __init__(
        self,
        paused: bool,
        current_player: chess.Color | None | str,
        white_time_left: float,
        black_time_left: float
    ):
        super().__init__()
        self.paused = paused
        self.current_player = self._parse_color(current_player)
        self.white_time_left = white_time_left
        self.black_time_left = black_time_left

    def to_json(self) -> dict:
        items = super().to_json()
        items['current_player'] = self._color_to_str(self.current_player)
        return items


class GameStateChangedEvent(Event):
    def __init__(
        self,
        board: chess.Board,
        clock_paused: bool,
        white_time_left: float,
        black_time_left: float,
        white_time_elapsed: float,
        black_time_elapsed: float,
        white_start_time: float,
        black_start_time: float,
        white_player: str,
        black_player: str,
        winner: chess.Color | None | str,
        is_game_started: bool = False,
        is_game_paused: bool = False,
    ):
        super().__init__()

        self.board = board

        self.last_move = board.move_stack[-1].uci() if board.move_stack else None
        self.is_check = board.is_check()

        self.clock_paused = clock_paused
        self.turn = self._parse_color(board.turn)

        self.white_time_left = white_time_left
        self.black_time_left = black_time_left

        self.white_time_elapsed = white_time_elapsed
        self.black_time_elapsed = black_time_elapsed

        self.white_start_time = white_start_time
        self.black_start_time = black_start_time

        self.white_player = white_player
        self.black_player = black_player

        self.winner = self._parse_color(winner)

        self.is_game_started = is_game_started
        self.is_game_paused = is_game_paused

    def to_json(self) -> dict:
        items = super().to_json()
        items['turn'] = self._color_to_str(self.turn)
        items['winner'] = self._color_to_str(self.winner)
        return items


class LegalMoveDetectedEvent(Event):
    def __init__(self, move: chess.Move):
        super().__init__()
        self.move = move

    def to_json(self) -> dict:
        return {
            "from_square": chess.square_name(self.move.from_square),
            "to_square": chess.square_name(self.move.to_square),
            "promotion": chess.piece_symbol(self.move.promotion) if self.move.promotion else None
        }


class _EventManager:
    def __init__(self):
        self._subscribers: dict[type[Event],
                                list[Callable]] = {}
        for event_type in Event.__subclasses__():
            self._subscribers[event_type] = []

        self._event_queue = queue.Queue()

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

    def publish(self, event: Event, block: bool = False, timeout: float = 5.0):
        """ Publishes an event to all subscribers.

        event: The event instance to publish.
        block: If True, waits until the event has been handled by all subscribers.
        timeout: Maximum time to wait if blocking is enabled.
        """

        event.sender = inspect.getmodule(inspect.stack()[1].frame)

        if block:
            # Prevent deadlock: ensure blocking publish is not invoked from the event handling thread
            if threading.current_thread() is self._thread:
                raise RuntimeError("publish(block=True) cannot be called from the event handling thread")
            event._sync_event = threading.Event()

        if event is None:
            raise ValueError("Cannot publish None event")

        self._event_queue.put_nowait(event)

        if block and event._sync_event is not None:
            success = event._sync_event.wait(timeout=timeout)
            if not success:
                raise TimeoutError("Timeout waiting for event to be handled")

    def _handle_event(self, event: Event):
        for callback in self._subscribers.get(type(event), ()):
            try:
                callback(event)
            except Exception as e:
                log.error(f"Error in event callback: {e}")
                traceback.print_exc()
        # Signal the event is handled if blocking was requested
        if event._sync_event is not None:
            event._sync_event.set()

    def main(self):
        while True:
            event = self._event_queue.get()
            if event is None:
                break

            log.debug(f"{type(event).__name__}: {event.to_json()}")

            self._handle_event(event)
            self._event_queue.task_done()

        log.info("EventManager main loop exiting")

    def stop(self):
        self._event_queue.put(None)
        self._thread.join(timeout=2.0)


event_manager = _EventManager()
atexit.register(event_manager.stop)

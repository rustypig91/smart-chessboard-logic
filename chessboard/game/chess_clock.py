import time
import chess
from threading import Lock, Thread, Event
from typing import Callable
import chessboard.events as events


class Stopwatch:
    def __init__(self):
        self._elapsed = 0.0
        self._last_start: float | None = None
        self._lock = Lock()

    @property
    def elapsed(self):
        with self._lock:
            last_interval = time.time() - self._last_start if self._last_start is not None else 0.0
            return self._elapsed + last_interval

    @elapsed.setter
    def elapsed(self, value: float):
        with self._lock:
            self._elapsed = value

    def reset(self):
        with self._lock:
            self._elapsed = 0.0
            self._last_start = None

    def run(self):
        with self._lock:
            if self._last_start is not None:
                raise RuntimeError('Stopwatch is already unpaused.')
            self._last_start = time.time()

    def pause(self):
        with self._lock:
            if self._last_start is None:
                raise RuntimeError('Stopwatch is already paused.')
            self._elapsed += time.time() - self._last_start
            self._last_start = None

    def increment(self, seconds: float):
        with self._lock:
            self._elapsed += seconds

    def decrement(self, seconds: float):
        with self._lock:
            self._elapsed -= seconds

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._last_start is None


class ChessClock:
    def __init__(self, initial_time_seconds: float | tuple[float, float] = float('inf'), increment_seconds: float | tuple[float, float] = 0.0, timeout_callback: Callable[[chess.Color], None] | None = None):
        """Chess clock with separate timers for white and black players.
        initial_time_seconds: float or tuple(float, float)
            Initial time for each player in seconds. If a single float is provided,
            both players get the same initial time. If a tuple is provided, it should
            be in the form (white_time, black_time).
        increment_seconds: float or tuple(float, float)
            Increment added to a player's clock after they make a move, in seconds.
            If a single float is provided, both players get the same increment. If a
            tuple is provided, it should be in the form (white_increment, black_increment).
        timeout_callback: Callable[[chess.Color], None] | None
            Optional callback invoked when a player's time runs out. The callback
            receives the color of the player who ran out of time.
        """

        self.clocks = {
            chess.WHITE: Stopwatch(),
            chess.BLACK: Stopwatch()
        }
        self.current_player = chess.WHITE

        self._initial_time_seconds = {
            chess.WHITE: initial_time_seconds[0] if isinstance(initial_time_seconds, tuple) else initial_time_seconds,
            chess.BLACK: initial_time_seconds[1] if isinstance(initial_time_seconds, tuple) else initial_time_seconds
        }

        if self._initial_time_seconds[chess.WHITE] <= 0 or self._initial_time_seconds[chess.BLACK] <= 0:
            raise ValueError("Initial time for each player must be greater than zero.")

        self._increment_seconds = {
            chess.WHITE: increment_seconds[0] if isinstance(increment_seconds, tuple) else increment_seconds,
            chess.BLACK: increment_seconds[1] if isinstance(increment_seconds, tuple) else increment_seconds
        }

        self._timeout_callback = timeout_callback

        self._event = Event()
        self._stop_monitor = False
        self._thread = self._monitor_time()

    def __del__(self):
        self._stop_monitor = True
        if self._thread is not None:
            self._event.set()
            self._thread.join()

    def _monitor_time(self):
        if self._timeout_callback is None or (self._initial_time_seconds[chess.WHITE] == float('inf') and self._initial_time_seconds[chess.BLACK] == float('inf')):
            return

        self._stop_monitor = False
        self._event.clear()

        def _worker():
            white_time_left = self.get_time_left(chess.WHITE)
            black_time_left = self.get_time_left(chess.BLACK)

            while not self._stop_monitor:
                white_time_left = self.get_time_left(chess.WHITE)
                black_time_left = self.get_time_left(chess.BLACK)
                min_time_left = min(white_time_left, black_time_left)

                if min_time_left <= 0:
                    break

                self._event.wait(timeout=min_time_left)

            if self._timeout_callback is not None and self._event.is_set() is False:
                loser = chess.WHITE if white_time_left <= 0 else chess.BLACK
                self._timeout_callback(loser)

        thread = Thread(target=_worker, daemon=True)
        thread.start()
        return thread

    def get_initial_time(self, color: chess.Color) -> float:
        return self._initial_time_seconds[color]

    def get_increment(self, color: chess.Color) -> float:
        return self._increment_seconds[color]

    def start(self):
        self.clocks[self.current_player].run()

    def pause(self):
        self.clocks[self.current_player].pause()

    def reset(self):
        self.clocks[chess.WHITE].reset()
        self.clocks[chess.BLACK].reset()

        self.current_player = chess.WHITE

    def set_player(self, color: chess.Color):
        if self.current_player == color:
            return

        current_player = self.clocks[self.current_player]
        current_player.pause()
        current_player.decrement(self.get_increment(self.current_player))

        self.current_player = color
        next_player = self.clocks[self.current_player]
        next_player.run()

    def get_time_left(self, color: chess.Color) -> float:
        return max(0.0, self.get_initial_time(color) - self.clocks[color].elapsed)

    @property
    def white_time_left(self) -> float:
        return self.get_time_left(chess.WHITE)

    @property
    def black_time_left(self) -> float:
        return self.get_time_left(chess.BLACK)

    @property
    def white_time_elapsed(self) -> float:
        return self.clocks[chess.WHITE].elapsed

    @white_time_elapsed.setter
    def white_time_elapsed(self, value: float):
        self.clocks[chess.WHITE].elapsed = value

    @property
    def black_time_elapsed(self) -> float:
        return self.clocks[chess.BLACK].elapsed

    @black_time_elapsed.setter
    def black_time_elapsed(self, value: float):
        self.clocks[chess.BLACK].elapsed = value

    @property
    def paused(self) -> bool:
        return self.clocks[self.current_player].paused

    @property
    def started(self) -> bool:
        return self.clocks[chess.WHITE].elapsed > 0.0 or self.clocks[chess.BLACK].elapsed > 0.0

    @property
    def white_start_time(self) -> float:
        return self._initial_time_seconds[chess.WHITE]

    @property
    def black_start_time(self) -> float:
        return self._initial_time_seconds[chess.BLACK]

    @property
    def white_increment_time(self) -> float:
        return self._increment_seconds[chess.WHITE]

    @property
    def black_increment_time(self) -> float:
        return self._increment_seconds[chess.BLACK]


if __name__ == "__main__":
    clock = ChessClock(initial_time_seconds=300, increment_seconds=2)

    clock.start()
    import time
    time.sleep(3)
    print("White time left:", clock.white_time_left)
    clock.set_player(chess.BLACK)
    time.sleep(5)
    print("Black time left:", clock.black_time_left)
    clock.set_player(chess.WHITE)
    time.sleep(2)
    print("White time left:", clock.white_time_left)

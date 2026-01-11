import time
import chess
from threading import Lock, Thread, Event
from typing import Callable
import chessboard.events as events


class Stopwatch:
    def __init__(self, elapsed: float = 0.0):
        self._elapsed = elapsed
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

    def start(self) -> bool:
        """ Start the stopwatch

        Returns: True if the stopwatch was started, False if it was already running
        """
        with self._lock:
            if self._last_start is not None:
                return False  # Already started
            self._last_start = time.time()
        return True

    def stop(self) -> bool:
        """ Stop the stopwatch

        Returns: True if the stopwatch was stopped, False if it was already stopped
        """
        with self._lock:
            if self._last_start is None:
                return False  # Already stopped
            self._elapsed += time.time() - self._last_start
            self._last_start = None
        return True

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

    def copy(self) -> 'Stopwatch':
        with self._lock:
            stopwatch = Stopwatch()
            stopwatch._elapsed = self._elapsed
            stopwatch._last_start = self._last_start
            return stopwatch

    def __getstate__(self):
        return self.elapsed

    def __setstate__(self, state):
        self._elapsed = state
        self._last_start = None
        self._lock = Lock()


class ChessClock:
    def __init__(self,
                 initial_time_seconds: float | tuple[float, float] = float('inf'),
                 increment_seconds: float | tuple[float, float] = 0.0,
                 timeout_callback: Callable[[chess.Color], None] | None = None,
                 elapsed_times: float | tuple[float, float] = (0.0, 0.0)):
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
            chess.WHITE: Stopwatch(elapsed=elapsed_times[0] if isinstance(elapsed_times, tuple) else elapsed_times),
            chess.BLACK: Stopwatch(elapsed=elapsed_times[1] if isinstance(elapsed_times, tuple) else elapsed_times)
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

        if timeout_callback is not None:
            self.add_timeout_callback(timeout_callback)

        self._stop_event = Event()

    def add_timeout_callback(self, callback: Callable[[chess.Color], None]) -> None:
        if self._initial_time_seconds[chess.WHITE] == float('inf') and self._initial_time_seconds[chess.BLACK] == float('inf'):
            # No timeout monitoring needed for infinite time controls
            return None

        def _worker():
            while not self._stop_event.is_set():
                white_time_left = self.get_time_left(chess.WHITE)
                black_time_left = self.get_time_left(chess.BLACK)

                if white_time_left <= 0:
                    callback(chess.WHITE)
                    break
                elif black_time_left <= 0:
                    callback(chess.BLACK)
                    break

                min_time_left = min(white_time_left, black_time_left)
                self._stop_event.wait(timeout=min_time_left)

        thread = Thread(target=_worker, daemon=True)
        thread.start()

    def __del__(self):
        self._stop_event.set()

    def get_initial_time(self, color: chess.Color) -> float:
        return self._initial_time_seconds[color]

    def get_increment_time(self, color: chess.Color) -> float:
        return self._increment_seconds[color]

    def start(self) -> bool:
        return self.clocks[self.current_player].start()

    def stop(self) -> bool:
        return self.clocks[self.current_player].stop()

    def reset(self):

        self.clocks[chess.WHITE].reset()
        self.clocks[chess.BLACK].reset()

        self.current_player = chess.WHITE

    def set_player(self, color: chess.Color, increment: bool = True) -> None:
        if self.current_player == color:
            return

        current_player = self.clocks[self.current_player]
        clock_was_running = current_player.stop()
        if increment:
            current_player.decrement(self.get_increment_time(self.current_player))

        self.current_player = color
        next_player = self.clocks[self.current_player]
        if clock_was_running:
            next_player.start()

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
    def start_times(self) -> tuple[float, float]:
        return self._initial_time_seconds[chess.WHITE], self._initial_time_seconds[chess.BLACK]

    @property
    def white_increment_time(self) -> float:
        return self._increment_seconds[chess.WHITE]

    @property
    def black_increment_time(self) -> float:
        return self._increment_seconds[chess.BLACK]

    @property
    def increment_times(self) -> tuple[float, float]:
        return self._increment_seconds[chess.WHITE], self._increment_seconds[chess.BLACK]

    def copy(self) -> 'ChessClock':
        clock = ChessClock(
            initial_time_seconds=(self._initial_time_seconds[chess.WHITE], self._initial_time_seconds[chess.BLACK]),
            increment_seconds=(self._increment_seconds[chess.WHITE], self._increment_seconds[chess.BLACK])
        )
        clock.current_player = self.current_player
        clock.clocks[chess.WHITE] = self.clocks[chess.WHITE].copy()
        clock.clocks[chess.BLACK] = self.clocks[chess.BLACK].copy()

        return clock

    def __getstate__(self):
        state = self.__dict__.copy()
        # Remove the lock from the state dictionary
        del state['_stop_event']

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._stop_event = Event()


chess_clock = ChessClock()


if __name__ == "__main__":
    clock = ChessClock(initial_time_seconds=300, increment_seconds=1)

    clock.start()
    import time
    time.sleep(3)
    print("White time left:", clock.white_time_left, "should be close to 297 (300 - 3 + 0)")
    clock.set_player(chess.BLACK)
    print("White time left:", clock.white_time_left, "should be close to 298 (300 - 3 + 1)")

    time.sleep(5)

    print("White time left:", clock.white_time_left, "should be close to 298 (300 - 3 + 1)")
    print("Black time left:", clock.black_time_left, "should be close to 295 (300 - 5 + 0)")
    clock.set_player(chess.WHITE)
    print("Black time left:", clock.black_time_left, "should be close to 296 (300 - 5 + 1)")

    time.sleep(2)
    print("Black time left:", clock.black_time_left, "should be close to 296 (300 - 5 + 1)")
    print("White time left:", clock.white_time_left, "should be close to 296 (298 - 2 + 0)")

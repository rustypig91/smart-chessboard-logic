import time
import chess
from threading import Lock


class Stopwatch:
    def __init__(self):
        self._elapsed = 0.0
        self._last_start: float | None = None
        self._lock = Lock()

    def __getstate__(self):
        return (self._elapsed, self._last_start)

    def __setstate__(self, state):
        self._elapsed, self._last_start = state
        self._lock = Lock()

    @property
    def elapsed(self):
        with self._lock:
            last_interval = time.time() - self._last_start if self._last_start is not None else 0.0
            return self._elapsed + last_interval

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
            if self._elapsed < 0:
                self._elapsed = 0.0

    @property
    def running(self) -> bool:
        with self._lock:
            return self._last_start is not None


class ChessClock:
    def __init__(self, initial_time_seconds: float = float('inf'), increment_seconds: float = 0.0):

        self.clocks = {
            chess.WHITE: Stopwatch(),
            chess.BLACK: Stopwatch()
        }
        self.current_player = chess.WHITE

        self._initial_time_seconds = initial_time_seconds
        self._increment_seconds = increment_seconds

    def start(self):
        self.clocks[self.current_player].run()

    def pause(self):
        self.clocks[self.current_player].pause()

    def reset(self):
        self.clocks[chess.WHITE].reset()
        self.clocks[chess.BLACK].reset()

        self.current_player = chess.WHITE
        self.clocks[chess.WHITE].run()

    def set_player(self, color: chess.Color):
        if self.current_player == color:
            return

        current_player = self.clocks[self.current_player]
        current_player.pause()
        current_player.increment(self._increment_seconds)

        self.current_player = color
        next_player = self.clocks[self.current_player]
        next_player.run()

    def get_time_left(self, color: chess.Color) -> float:
        return max(0.0, self._initial_time_seconds - self.clocks[color].elapsed)

    @property
    def white_time_left(self) -> float:
        return self.get_time_left(chess.WHITE)

    @property
    def black_time_left(self) -> float:
        return self.get_time_left(chess.BLACK)

    @property
    def white_time_elapsed(self) -> float:
        return self.clocks[chess.WHITE].elapsed

    @property
    def black_time_elapsed(self) -> float:
        return self.clocks[chess.BLACK].elapsed

    @property
    def running(self) -> bool:
        return self.clocks[self.current_player].running


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

import time
import chess
from threading import Lock, Thread, Event
import chessboard.events as events
from chessboard.persistent_storage import PersistentClass
from chessboard.logger import log


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


class ChessClock(PersistentClass):
    def __init__(self):
        """Chess clock with separate timers for white and black players
        """
        super().__init__()

        self._clocks = {
            chess.WHITE: Stopwatch(),
            chess.BLACK: Stopwatch()
        }
        self._current_player = chess.WHITE

        self._initial_time_seconds = {
            chess.WHITE: float('inf'),
            chess.BLACK: float('inf')
        }

        self._increment_seconds = {
            chess.WHITE: 0.0,
            chess.BLACK: 0.0
        }

        self._post_init()

    def _post_init(self) -> None:
        """ Initialize attributes that are not persisted """
        self._stop_event = Event()
        self._lock = Lock()
        self._timeout_monitor_thread: Thread | None = None

        events.event_manager.subscribe(events.MoveEvent, self._handle_move_event)
        events.event_manager.subscribe(events.NewGameEvent, self._handle_new_game_event)
        events.event_manager.subscribe(events.ClockStartEvent, self._handle_clock_start_event)
        events.event_manager.subscribe(events.ClockStopEvent, self._handle_clock_stop_event)
        events.event_manager.subscribe(events.MoveRegrettedEvent, self._handle_move_regretted_event)
        events.event_manager.subscribe(events.NewSubscriberEvent, self._handle_new_subscriber_event)
        events.event_manager.subscribe(events.GameOverEvent, self._handle_game_over_event)

        self._start_timeout_monitoring()

    def _handle_game_over_event(self, event: events.GameOverEvent) -> None:
        self._clocks[self._current_player].stop()
        self._send_clock_state_event()

    def _handle_new_subscriber_event(self, event: events.NewSubscriberEvent) -> None:
        """ Handle new subscriber event to send latest clock state """
        if event.event_type == events.ClockStateEvent:
            white_time_elapsed, white_time_left = self._get_time(chess.WHITE)
            black_time_elapsed, black_time_left = self._get_time(chess.BLACK)
            events.event_manager.publish(events.ClockStateEvent(
                paused=self._clocks[self._current_player].paused,
                current_side=self._current_player,
                white_time_left=white_time_left,
                black_time_left=black_time_left,
                white_time_elapsed=white_time_elapsed,
                black_time_elapsed=black_time_elapsed
            ))

    def _handle_clock_start_event(self, event: events.ClockStartEvent):
        self._clocks[self._current_player].start()
        self._send_clock_state_event()
        log.info(f"Clock started during player {chess.COLOR_NAMES[self._current_player]} turn")

    def _handle_clock_stop_event(self, event: events.ClockStopEvent):
        self._clocks[self._current_player].stop()
        self._send_clock_state_event()

        log.info(f"Clock stopped during player {chess.COLOR_NAMES[self._current_player]} turn")

    def _send_clock_state_event(self):
        white_time_elapsed, white_time_left = self._get_time(chess.WHITE)
        black_time_elapsed, black_time_left = self._get_time(chess.BLACK)
        events.event_manager.publish(events.ClockStateEvent(
            paused=self._clocks[self._current_player].paused,
            current_side=self._current_player,
            white_time_left=white_time_left,
            black_time_left=black_time_left,
            white_time_elapsed=white_time_elapsed,
            black_time_elapsed=black_time_elapsed
        ))

    def _start_timeout_monitoring(self):
        self._stop_timeout_monitoring()

        if self._initial_time_seconds[chess.WHITE] == float('inf') and self._initial_time_seconds[chess.BLACK] == float('inf'):
            # No timeout monitoring needed for infinite time controls
            return None

        def _worker():
            while not self._stop_event.is_set():
                _, white_time_left = self._get_time(chess.WHITE)
                _, black_time_left = self._get_time(chess.BLACK)

                if white_time_left <= 0:
                    events.event_manager.publish(events.ClockTimeoutEvent(side=chess.WHITE))
                    break
                elif black_time_left <= 0:
                    events.event_manager.publish(events.ClockTimeoutEvent(side=chess.BLACK))
                    break

                min_time_left = min(white_time_left, black_time_left)
                self._stop_event.wait(timeout=min_time_left)

        self._stop_event.clear()
        thread = Thread(target=_worker, daemon=True)
        thread.start()
        self._timeout_monitor_thread = thread

    def _stop_timeout_monitoring(self):
        if self._timeout_monitor_thread is None:
            return
        self._stop_event.set()
        self._timeout_monitor_thread.join()
        self._timeout_monitor_thread = None

    def _get_time(self, side: chess.Color) -> tuple[float, float]:
        """ Get the elapsed time and time left for the given side """
        with self._lock:
            # This function is called from the thread worker so we need to lock to avoid race conditions
            elapsed = self._clocks[side].elapsed
            return elapsed, max(0.0, self._initial_time_seconds[side] - elapsed)

    def _handle_move_event(self, event: events.MoveEvent):
        self._clocks[event.side].stop()

        # Decrement elapsed time by increment i.e. add increment to time left
        self._clocks[event.side].decrement(self._increment_seconds[event.side])
        self._clocks[not event.side].start()

        self._current_player = not event.side

        self._send_clock_state_event()

    def _handle_move_regretted_event(self, event: events.MoveRegrettedEvent):
        stopped = self._clocks[self._current_player].stop()

        self._current_player = not self._current_player

        # Increment elapsed time by increment for the player whose move was regretted
        self._clocks[self._current_player].increment(self._increment_seconds[not self._current_player])
        if stopped:
            self._clocks[self._current_player].start()

        self._send_clock_state_event()

    def _handle_new_game_event(self, event: events.NewGameEvent):
        self._stop_timeout_monitoring()

        self._clocks[chess.WHITE].reset()
        self._clocks[chess.BLACK].reset()

        self._increment_seconds[chess.WHITE] = event.increment_seconds[0]
        self._increment_seconds[chess.BLACK] = event.increment_seconds[1]

        self._initial_time_seconds[chess.WHITE] = event.start_time_seconds[0]
        self._initial_time_seconds[chess.BLACK] = event.start_time_seconds[1]

        self._current_player = chess.WHITE

        self._start_timeout_monitoring()

        self._send_clock_state_event()

    def __repr__(self):
        _, white_time_left = self._get_time(chess.WHITE)
        _, black_time_left = self._get_time(chess.BLACK)
        return (f"<ChessClock white_time_left={white_time_left:.2f}s "
                f"black_time_left={black_time_left:.2f}s "
                f"current_player={'white' if self._current_player == chess.WHITE else 'black'}>")

    def __getstate__(self):
        state = self.__dict__.copy()
        # Remove the lock from the state dictionary
        del state['_stop_event']
        del state['_lock']
        del state['_timeout_monitor_thread']

        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._post_init()


chess_clock: ChessClock = ChessClock.load()

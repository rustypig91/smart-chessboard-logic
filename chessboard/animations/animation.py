
import threading
import chessboard.events as events
from chessboard.logger import log
from time import time
from chessboard.thread_safe_variable import ThreadSafeVariable
import chessboard.board.led_manager as leds


class Animation:
    def __init__(self,
                 fps: float,
                 priority: int = 10,
                 loop: bool = False):

        self._thread = None

        if fps <= 0:
            raise ValueError("FPS must be greater than 0")

        self._stop = threading.Event()
        self._loop = loop
        self._frame_index = ThreadSafeVariable(0)

        self._fps = fps

        self._led_layer = leds.LedLayer(priority=priority)

        self.start_time = 0.0
        self.frame_start_time = 0.0

    def __del__(self) -> None:
        self._stop.set()

    @property
    def frame_index(self) -> int:
        return self._frame_index.get()

    @property
    def elapsed_time(self) -> float:
        return self.frame_start_time - self.start_time

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def update(self) -> bool:
        """ Update the animation state. Shall return True if the animation is complete. """
        raise NotImplementedError()

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Animation is already running")

        self._stop.clear()

        leds.led_manager.add_layer(self._led_layer)

        self._thread = threading.Thread(target=self._animate_thread, daemon=False)

        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()

        self._thread.join()

        self._thread = None

        leds.led_manager.remove_layer(self._led_layer)

    def restart(self) -> None:
        self.stop()
        self.start()

    def _animate_thread(self) -> None:
        index = self.frame_index
        start_time = None
        is_complete = False

        frame_time = 1.0 / self._fps
        self._frame_index.set(0)
        self.start_time = time()

        while not self._stop.is_set() and not is_complete:
            if start_time is not None:
                elapsed = time() - start_time
                if elapsed < frame_time:
                    self._stop.wait(frame_time - elapsed)
                    if self._stop.is_set():
                        break
                elif elapsed > frame_time:
                    log.warning(
                        f"Animation frame took longer ({elapsed:.3f}s) than its duration ({frame_time:.3f}s)")

            self.frame_start_time = time()
            is_complete = self.update()
            self._led_layer.commit()
            start_time = time()
            index += 1
            self._frame_index.set(index)

            if is_complete:
                if not self._loop:
                    break
                self._frame_index.set(0)
                self.start_time = time()
                is_complete = False
                index = 0

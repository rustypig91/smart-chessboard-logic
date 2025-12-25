from typing import Callable
import chess
from chessboard.settings import settings
import threading
import chessboard.events as events
from chessboard.logger import log
from time import time


class AnimationFrame:
    def __init__(self, duration: float, colors: dict[chess.Square, tuple[int, int, int] | None]) -> None:
        self.duration = duration
        self.colors = colors

    def play(self):
        """ For testing: print the frame colors """
        event = events.SetSquareColorEvent(self.colors)
        events.event_manager.publish(event)


class Animation:
    def __init__(self,
                 callback: Callable[[], None] | None = None,
                 start_colors: dict[chess.Square, tuple[int, int, int] | None] | None = None,
                 overlay_colors: dict[chess.Square, tuple[int, int, int] | None] | None = None) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._animate_thread)
        self._animation_done_callback = callback
        self._start_colors = start_colors
        self._overlay_colors = overlay_colors or {}

    def next_frame(self) -> AnimationFrame | None:
        """
        Returns the next frame of the animation as a list of tuples containing
        (time the frame should be displayed in seconds, square, color). If the animation is complete, returns None.
        """
        raise NotImplementedError()

    def start(self):
        self._stop.clear()
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _animate_thread(self):
        events.event_manager.supress_other_publishers(events.SetSquareColorEvent)

        start_time = None
        while not self._stop.is_set():
            frame = self.next_frame()

            if frame is None:
                break

            event = events.SetSquareColorEvent(frame.colors)
            if start_time is not None:
                elapsed = time() - start_time
                if elapsed < frame.duration:
                    self._stop.wait(frame.duration - elapsed)
                elif elapsed > frame.duration:
                    log.warning(
                        f"Animation frame took longer ({elapsed:.3f}s) than its duration ({frame.duration:.3f}s)")

            frame.colors.update(self._overlay_colors)
            events.event_manager.publish(event, block=True)
            start_time = time()

        if self._start_colors:
            event = events.SetSquareColorEvent(self._start_colors)
            events.event_manager.publish(event)

        events.event_manager.unsupress_other_publishers(events.SetSquareColorEvent)

        if self._animation_done_callback:
            self._animation_done_callback()


class AnimationChangeSide(Animation):
    def __init__(self, current_side: chess.Color, duration: float = 0.2, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._current_side = current_side
        self._duration = duration

        self._white_max_rank = 0 if current_side == chess.WHITE else 7

        self._steps = range(71)
        self._frame_idx = 0

    def next_frame(self) -> AnimationFrame | None:
        if self._frame_idx >= len(self._steps):
            return None

        white_min = settings['game.colors.white_min']
        white_max = settings['game.colors.white_max']

        white_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1]
        black_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]

        color_map = {}
        color_map.update({sq: settings['game.colors.black'] for sq in black_squares})

        for rank in range(8):
            current_max_position = self._steps[self._frame_idx] / 10.0
            if self._current_side == chess.WHITE:
                length_from_max = abs(rank - current_max_position)
            else:
                length_from_max = abs((7 - rank) - current_max_position)

            interpolation = [0, 0, 0]
            for i in range(3):
                interpolation[i] = white_max[i] - (length_from_max * (white_max[i] - white_min[i]) / 7.0)

            color_map.update({sq: tuple(int(c) for c in interpolation)
                             for sq in white_squares if chess.square_rank(sq) == rank})

        self._frame_idx += 1

        return AnimationFrame(duration=self._duration / len(self._steps), colors=color_map)


if __name__ == "__main__":
    import tkinter as tk
    # Example usage
    root = tk.Tk()
    root.title("8x8 Chessboard")

    square_size = 40
    canvas = tk.Canvas(root, width=8*square_size, height=8*square_size)
    canvas.pack()

    rects = {}
    for row in range(8):
        for col in range(8):
            x1 = col * square_size
            y1 = row * square_size
            x2 = x1 + square_size
            y2 = y1 + square_size
            rect = canvas.create_rectangle(x1, y1, x2, y2, fill="white", outline="black")
            rects[chess.square(col, 7 - row)] = rect  # Map chess square to rectangle

    anim = AnimationChangeSide(chess.WHITE, duration=1.0)

    def rgb_to_hex(rgb):
        return "#%02x%02x%02x" % rgb

    def play_animation():
        frame = anim.next_frame()
        if frame is None:
            return
        for square, color in frame.colors.items():
            canvas.itemconfig(rects[square], fill=rgb_to_hex(color))
        root.after(int(frame.duration * 1000), play_animation)

    play_animation()
    root.mainloop()

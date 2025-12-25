from typing import Callable
import math
import random
import colorsys
import chess
from chessboard.settings import settings
import threading
import chessboard.events as events
from chessboard.logger import log
from time import time


class AnimationFrame:
    def __init__(self, duration: float, colors: dict[chess.Square, tuple[int, int, int]]) -> None:
        self.duration = duration
        self.colors = colors

    def play(self):
        """ For testing: print the frame colors """
        event = events.SetSquareColorEvent(self.colors)
        events.event_manager.publish(event)


class Animation:
    def __init__(self,
                 callback: Callable[[], None] | None = None,
                 start_colors: dict[chess.Square, tuple[int, int, int]] | None = None,
                 overlay_colors: dict[chess.Square, tuple[int, int, int]] | None = None,
                 loop: bool = False) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._animate_thread)
        self._animation_done_callback = callback
        self._start_colors = start_colors
        self._overlay_colors = overlay_colors or {}
        self._loop = loop

    def get_frame(self, index: int) -> AnimationFrame | None:
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
        with events.event_manager.supress_other_publishers(events.SetSquareColorEvent):
            idx = 0
            start_time = None
            while not self._stop.is_set():
                frame = self.get_frame(idx)
                idx += 1

                if frame is None:
                    if not self._loop:
                        break
                    idx = 0
                    continue

                event = events.SetSquareColorEvent(frame.colors)
                if start_time is not None:
                    elapsed = time() - start_time
                    if elapsed < frame.duration:
                        self._stop.wait(frame.duration - elapsed)
                        if self._stop.is_set():
                            break
                    elif elapsed > frame.duration:
                        log.warning(
                            f"Animation frame took longer ({elapsed:.3f}s) than its duration ({frame.duration:.3f}s)")

                frame.colors.update(self._overlay_colors)
                events.event_manager.publish(event, block=True)
                start_time = time()

            if self._start_colors:
                event = events.SetSquareColorEvent(self._start_colors)
                events.event_manager.publish(event)

        if self._animation_done_callback:
            self._animation_done_callback()


class AnimationChangeSide(Animation):
    def __init__(self, current_side: chess.Color, duration: float = 0.2, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._current_side = current_side
        self._duration = duration

        self._white_max_rank = 0 if current_side == chess.WHITE else 7

        self._steps = range(71)

    def get_frame(self, index: int) -> AnimationFrame | None:
        if index >= len(self._steps):
            return None

        white_min = settings['game.colors.white_min']
        white_max = settings['game.colors.white_max']

        white_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1]
        black_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]

        color_map = {}
        color_map.update({sq: settings['game.colors.black'] for sq in black_squares})

        for rank in range(8):
            current_max_position = self._steps[index] / 10.0
            if self._current_side == chess.WHITE:
                length_from_max = abs(rank - current_max_position)
            else:
                length_from_max = abs((7 - rank) - current_max_position)

            interpolation = [0, 0, 0]
            for i in range(3):
                interpolation[i] = white_max[i] - (length_from_max * (white_max[i] - white_min[i]) / 7.0)

            color_map.update({sq: tuple(int(c) for c in interpolation)
                             for sq in white_squares if chess.square_rank(sq) == rank})

        return AnimationFrame(duration=self._duration / len(self._steps), colors=color_map)


class AnimationWaveAround(Animation):
    def __init__(self,
                 center_square: chess.Square,
                 duration: float = 1.0,
                 frames: int = 50,
                 base_frame: dict[chess.Square, tuple[int, int, int]] | None = None,
                 *args,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._center = center_square
        self._duration = duration
        self._frames = max(1, frames)

        # Base frame to modulate (default frame)
        self._base_colors: dict[chess.Square, tuple[int, int, int]] = base_frame or {}

        r0 = chess.square_rank(self._center)
        f0 = chess.square_file(self._center)
        # Max Euclidean radius to any corner for smooth circular wave
        corners = [(0, 0), (0, 7), (7, 0), (7, 7)]
        self._max_radius = max(math.sqrt((r0 - r)**2 + (f0 - f)**2) for r, f in corners)

        # Wave parameters: narrow ring (sigma) and damping
        self._sigma = 0.75  # ring thickness
        self._damp = 0.12   # amplitude decay per radius unit
        self._boost = 0.9   # overall brightness boost at wavefront

    def get_frame(self, index: int) -> AnimationFrame | None:
        if index >= self._frames:
            return None

        t = index / (self._frames - 1) if self._frames > 1 else 1.0
        radius = t * self._max_radius

        r0 = chess.square_rank(self._center)
        f0 = chess.square_file(self._center)

        colors: dict[chess.Square, tuple[int, int, int]] = {}

        # Expanding circular ripple: modulate the provided base frame intensities
        for sq in chess.SQUARES:
            r = chess.square_rank(sq)
            f = chess.square_file(sq)
            dist = math.sqrt((r - r0)**2 + (f - f0)**2)
            # Gaussian window around the wavefront radius for a thin ring
            gauss = math.exp(-((dist - radius)**2) / (2 * self._sigma**2))
            # Damping with distance to emulate energy loss in water
            amplitude = gauss * math.exp(-self._damp * radius) * self._boost

            base = self._base_colors.get(sq, None)
            if base is None:
                # No base color known for this square; skip modulation
                continue

            # Scale base color upwards (brighten) at the wavefront
            scale = 1.0 + amplitude
            rC = min(255, int(base[0] * scale))
            gC = min(255, int(base[1] * scale))
            bC = min(255, int(base[2] * scale))
            # Only publish if it changes noticeably
            if (rC, gC, bC) != base:
                colors[sq] = (rC, gC, bC)

        # Highlight the center at the start by boosting base color
        if index == 0 and self._center in self._base_colors and self._base_colors[self._center] is not None:
            base = self._base_colors[self._center]
            scale = 1.5
            boosted = (min(255, int(base[0] * scale)),
                       min(255, int(base[1] * scale)),
                       min(255, int(base[2] * scale)))
            colors[self._center] = boosted

        return AnimationFrame(duration=self._duration / self._frames, colors=colors)


class AnimationRainbow(Animation):
    """Shimmering rainbow flowing across the board.

    - Uses HSV hue bands across ranks/files with a time-varying phase.
    - Adds subtle per-square noise for a shimmer effect.
    - Keeps black squares dim for contrast; white squares show bright rainbow.
    """

    def __init__(self,
                 duration: float = 3.0,
                 frames: int = 120,
                 flow_axis: str = 'file',
                 speed: float = 0.08,
                 *args,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._duration = duration
        self._frames = max(1, frames)
        self._flow_axis = flow_axis  # 'file', 'rank', or 'diag'
        self._speed = speed

        try:
            self._black_color = settings['game.colors.black']
        except KeyError:
            self._black_color = (0, 0, 0)

        # Static noise offsets per square for shimmering (stable over time)
        random.seed(42)
        self._noise: dict[chess.Square, float] = {sq: random.uniform(-0.07, 0.07) for sq in chess.SQUARES}

    def _pos_value(self, sq: chess.Square) -> float:
        r = chess.square_rank(sq)
        f = chess.square_file(sq)
        if self._flow_axis == 'rank':
            return r / 7.0
        elif self._flow_axis == 'diag':
            return (r + f) / 14.0
        # default: flow along files
        return f / 7.0

    def get_frame(self, index: int) -> AnimationFrame | None:
        if index >= self._frames:
            return None

        t = index / self._frames
        phase = (t * (1.0 + self._speed)) % 1.0

        white_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1]
        black_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]

        colors: dict[chess.Square, tuple[int, int, int]] = {}

        # White squares: vivid rainbow with shimmer
        for sq in white_squares:
            pos = self._pos_value(sq)
            hue = (phase + pos) % 1.0
            # Slight brightness pulse + per-square noise
            pulse = 0.15 * (0.5 + 0.5 * math.sin(2 * math.pi * (t * 3.0 + pos)))
            val = min(1.0, 0.85 + pulse + self._noise[sq])
            sat = min(1.0, 0.95)
            r, g, b = colorsys.hsv_to_rgb(hue, sat, max(0.0, val))
            colors[sq] = (int(r * 255), int(g * 255), int(b * 255))

        # Black squares: keep mostly dark with gentle colored glints for contrast
        for sq in black_squares:
            pos = self._pos_value(sq)
            hue = (phase + pos) % 1.0
            pulse = 0.08 * (0.5 + 0.5 * math.sin(2 * math.pi * (t * 2.0 + pos)))
            val = min(0.25, 0.10 + pulse + max(-0.02, self._noise[sq]))
            sat = 0.8
            r, g, b = colorsys.hsv_to_rgb(hue, sat, max(0.0, val))
            # Blend toward configured black for a subtle effect
            br, bg, bb = self._black_color
            colors[sq] = (
                min(255, int(br * 0.7 + r * 255 * 0.3)),
                min(255, int(bg * 0.7 + g * 255 * 0.3)),
                min(255, int(bb * 0.7 + b * 255 * 0.3)),
            )

        return AnimationFrame(duration=self._duration / self._frames, colors=colors)


if __name__ == "__main__":
    import tkinter as tk

    class TKInterBoard:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("8x8 Chessboard")

            square_size = 80
            self.canvas = tk.Canvas(self.root, width=8*square_size, height=8*square_size)
            self.canvas.pack()

            self.rects = {}
            for row in range(8):
                for col in range(8):
                    x1 = col * square_size
                    y1 = row * square_size
                    x2 = x1 + square_size
                    y2 = y1 + square_size
                    rect = self.canvas.create_rectangle(x1, y1, x2, y2, fill="white", outline="black")
                    self.rects[chess.square(col, 7 - row)] = rect  # Map chess square to rectangle

            events.event_manager.subscribe(events.SetSquareColorEvent, self._handle_set_square_color_event)

        def _handle_set_square_color_event(self, event: events.SetSquareColorEvent):
            for square, color in event.color_map.items():
                hex_color = "#%02x%02x%02x" % color
                self.canvas.itemconfig(self.rects[square], fill=hex_color)

        def run(self):
            self.root.mainloop()

    board = TKInterBoard()
    board.root.after(100, lambda: AnimationRainbow(loop=True).start())
    board.run()

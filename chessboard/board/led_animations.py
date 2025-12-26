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
from chessboard.thread_safe_variable import ThreadSafeVariable
import chessboard.board.led_manager as leds


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
                 fps: float,
                 duration: float,
                 loop: bool = False) -> None:

        if fps <= 0:
            raise ValueError("FPS must be greater than 0")

        self._stop = threading.Event()
        self._thread = None
        self._loop = loop
        self._frame_index = ThreadSafeVariable(0)

        self._fps = fps
        self._duration = duration
        self._total_frames = max(1, int(self._fps * self._duration))

        self._led_layer = leds.LedLayer()
        leds.led_manager.add_layer(self._led_layer)

        self.start_time = 0.0

    def __del__(self):
        x = 1

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def frame_index(self) -> int:
        return self._frame_index.get()

    def update(self) -> bool:
        """ Update the animation state. Returns True if the animation is complete. """
        raise NotImplementedError()

    def start(self):
        if self._thread is not None:
            raise RuntimeError("Animation is already running")

        self._stop.clear()
        self._thread = threading.Thread(target=self._animate_thread)
        self._thread.start()

    def stop(self):
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join()
        self._thread = None

    def restart(self):
        self.stop()
        self.start()

    def _animate_thread(self):
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


class AnimationChangeSide(Animation):
    def __init__(self, new_side: chess.Color, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._change_to = new_side

        self._current_position = 7.0 / 2.0  # Start in the middle

        self._movement_per_frame = 7.0 / self.total_frames

    def set_side(self, new_side: chess.Color) -> None:
        self._change_to = new_side
        self.restart()

    def update(self) -> bool:
        intensity_max = 1.0
        intensity_min = 0.5

        if self._change_to == chess.WHITE:
            self._current_position -= self._movement_per_frame
        else:
            self._current_position += self._movement_per_frame

        self._current_position = max(0.0, min(7.0, self._current_position))

        for rank in range(8):
            length_from_max = abs(rank - self._current_position)
            interpolation = intensity_max - (length_from_max * (intensity_max - intensity_min) / 7.0)
            self._led_layer.intensity.update({sq: interpolation for sq in
                                             [s for s in chess.SQUARES if chess.square_rank(s) == rank]})

        done = self._current_position <= 0.0 or self._current_position >= 7.0
        return done


class AnimationWaveAround(Animation):
    def __init__(self,
                 center_square: chess.Square,
                 *args,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._center = center_square

        r0 = chess.square_rank(self._center)
        f0 = chess.square_file(self._center)
        # Max Euclidean radius to any corner for smooth circular wave
        corners = [(0, 0), (0, 7), (7, 0), (7, 7)]
        self._max_radius = max(math.sqrt((r0 - r)**2 + (f0 - f)**2) for r, f in corners)

        # Wave parameters: narrow ring (sigma) and damping
        self._sigma = 0.75  # ring thickness
        self._damp = 0.12   # amplitude decay per radius unit
        self._boost = 1.0   # overall brightness boost at wavefront

    def update(self) -> bool:
        index = self.frame_index

        t = index / (self.total_frames - 1) if self.total_frames > 1 else 1.0
        radius = t * self._max_radius

        r0 = chess.square_rank(self._center)
        f0 = chess.square_file(self._center)

        # Expanding circular ripple: modulate the provided base frame intensities
        for sq in chess.SQUARES:
            r = chess.square_rank(sq)
            f = chess.square_file(sq)
            dist = math.sqrt((r - r0)**2 + (f - f0)**2)
            # Gaussian window around the wavefront radius for a thin ring
            gauss = math.exp(-((dist - radius)**2) / (2 * self._sigma**2))
            # Damping with distance to emulate energy loss in water
            amplitude = gauss * math.exp(-self._damp * radius) * self._boost

            # Scale base color upwards (brighten) at the wavefront
            scale = 1.0 + amplitude
            self._led_layer.intensity.update({sq: scale})

        # Highlight the center at the start by boosting base color
        # if index == 0 and self._center in self._base_colors and self._base_colors[self._center] is not None:
        #     base = self._base_colors[self._center]
        #     scale = 1.5
        #     boosted = (min(255, int(base[0] * scale)),
        #                min(255, int(base[1] * scale)),
        #                min(255, int(base[2] * scale)))
        #     colors[self._center] = boosted

        return index >= self.total_frames


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


class AnimationPulse(Animation):
    """ Simple pulse animation on one square
    """

    def __init__(self,
                 pulsating_square: chess.Square,
                 pulsating_color: tuple[int, int, int],
                 duration: float = 1.6,
                 fps: float = 15.0,
                 pulses: int = 2,
                 *args,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._pulsating_square = pulsating_square
        self._duration = duration
        # 5 fps
        self._frames = max(1, int(self._duration * fps))
        self._pulses = max(1, pulses)
        self._pulsating_color = pulsating_color

    def get_frame(self, index: int) -> AnimationFrame | None:
        if index >= self._frames:
            return None

        time_progress = index / self._frames

        colors: dict[chess.Square, tuple[int, int, int]] = {}

        k_pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(2 * math.pi * (time_progress * (2 + self._pulses))))
        kR = min(255, int(self._pulsating_color[0] * k_pulse))
        kG = min(255, int(self._pulsating_color[1] * k_pulse))
        kB = min(255, int(self._pulsating_color[2] * k_pulse))
        colors[self._pulsating_square] = (kR, kG, kB)

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
    # board.root.after(100, lambda: AnimationRainbow(loop=True).start())
    board.root.after(100, lambda: AnimationPulse(chess.E4, pulsating_color=(255, 0, 0), loop=True).start())
    board.run()

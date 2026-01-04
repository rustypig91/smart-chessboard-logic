import chess
import math
import random
import colorsys
from chessboard.animations.animation import Animation
from chessboard.settings import settings


class AnimationRainbow(Animation):
    """Shimmering rainbow flowing across the board.

    - Uses HSV hue bands across ranks/files with a time-varying phase.
    - Adds subtle per-square noise for a shimmer effect.
    - Keeps black squares dim for contrast; white squares show bright rainbow.
    """

    def __init__(self,
                 flow_axis: str = 'file',
                 speed: float = 0.08,
                 duration: float = float('inf'),
                 *args,
                 **kwargs) -> None:
        """  Rainbow animation flowing across the board.

        flow_axis: 'file', 'rank', or 'diag' for direction of rainbow flow.
        speed: Speed of rainbow flow (higher is faster).
        duration: Duration of the animation in seconds.
        """
        super().__init__(*args, **kwargs)

        self._flow_axis = flow_axis  # 'file', 'rank', or 'diag'
        self._speed = speed
        self._duration = duration

        try:
            self._black_color = settings['led.color.black']
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

    def update(self) -> bool:
        t = self.elapsed_time
        phase = (t * (1.0 + self._speed)) % 1.0

        white_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1]
        black_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]

        # White squares: vivid rainbow with shimmer
        for sq in white_squares:
            pos = self._pos_value(sq)
            hue = (phase + pos) % 1.0
            # Slight brightness pulse + per-square noise
            pulse = 0.15 * (0.5 + 0.5 * math.sin(2 * math.pi * (t * 3.0 + pos)))
            val = min(1.0, 0.85 + pulse + self._noise[sq])
            sat = min(1.0, 0.95)
            r, g, b = colorsys.hsv_to_rgb(hue, sat, max(0.0, val))
            self._led_layer.colors[sq] = (int(r * 255), int(g * 255), int(b * 255))

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
            self._led_layer.colors[sq] = (
                min(255, int(br * 0.7 + r * 255 * 0.3)),
                min(255, int(bg * 0.7 + g * 255 * 0.3)),
                min(255, int(bb * 0.7 + b * 255 * 0.3)),
            )

        return self.elapsed_time >= self._duration

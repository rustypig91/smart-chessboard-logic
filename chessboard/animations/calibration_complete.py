import chess
import math
from chessboard.animations.animation import Animation


class AnimationCalibrationComplete(Animation):
    """Celebration animation for successful sensor calibration.

    Sequence:
    1) A bright green ripple expands from the center squares.
    2) A short global pulse fades out to reinforce success.
    """

    def __init__(self,
                 color: tuple[int, int, int],
                 ripple_duration: float = 1.2,
                 pulse_duration: float = 1.0,
                 *args,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._color = color
        self._ripple_duration = ripple_duration
        self._pulse_duration = pulse_duration

        # Precompute max radius from center for smooth circular wave
        centers = [
            chess.parse_square('d4'), chess.parse_square('e4'),
            chess.parse_square('d5'), chess.parse_square('e5')
        ]
        r0 = sum(chess.square_rank(c) for c in centers) / len(centers)
        f0 = sum(chess.square_file(c) for c in centers) / len(centers)

        corners = [(0, 0), (0, 7), (7, 0), (7, 7)]
        self._max_radius = max(math.sqrt((r0 - r)**2 + (f0 - f)**2) for r, f in corners)

        # Initialize all squares to target color
        for sq in chess.SQUARES:
            self._led_layer.colors[sq] = self._color

        # Ripple params
        self._sigma = 0.65  # ring thickness
        self._damp = 0.08   # damping factor
        self._boost = 1.0   # overall brightness boost at wavefront

    def _update_ripple(self, t: float) -> bool:
        radius = (t / self._ripple_duration) * self._max_radius

        r0 = 3.5  # approx center rank index
        f0 = 3.5  # approx center file index

        all_zero = True

        for sq in chess.SQUARES:
            r = chess.square_rank(sq)
            f = chess.square_file(sq)
            dist = math.sqrt((r - r0)**2 + (f - f0)**2)
            gauss = math.exp(-((dist - radius)**2) / (2 * self._sigma**2))
            amplitude = gauss * math.exp(-self._damp * radius) * self._boost
            amplitude = min(1.0, max(0.0, amplitude))
            # self._led_layer.square_opacity[sq] = amplitude
            self._led_layer.colors[sq] = (
                int(self._color[0] * amplitude),
                int(self._color[1] * amplitude),
                int(self._color[2] * amplitude),
            )
            if amplitude > 0.01:
                all_zero = False

        return all_zero

    def _update_pulse(self, t: float) -> bool:
        # t in [0, pulse_duration]
        # A smooth fade-in/out pulse: sin^2 window
        x = max(0.0, min(1.0, t / self._pulse_duration))
        amplitude = math.sin(math.pi * x) ** 2

        if t < self._pulse_duration / 2.0:
            self._led_layer.colors = {
                sq: (
                    int(self._color[0] * amplitude),
                    int(self._color[1] * amplitude),
                    int(self._color[2] * amplitude),
                )
                for sq in chess.SQUARES
            }
        else:
            self._led_layer.colors = {
                sq: (
                    int(self._color[0]),
                    int(self._color[1]),
                    int(self._color[2]),
                )
                for sq in chess.SQUARES
            }
            self._led_layer.layer_opacity = amplitude

        return t >= self._pulse_duration

    def update(self) -> bool:
        t = self.elapsed_time
        if t <= self._ripple_duration:
            return self._update_ripple(t)
        else:
            # Switch to pulse phase; keep ripple result as base
            t2 = t - self._ripple_duration
            return self._update_pulse(t2)

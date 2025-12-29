import chess
import math
from chessboard.animations.animation import Animation
from chessboard.thread_safe_variable import ThreadSafeVariable


class AnimationPulse(Animation):
    """ Simple pulse animation on one square
    """

    def __init__(self,
                 pulsating_squares: list[chess.Square],
                 frequency_hz: float,
                 pulsating_color: tuple[int, int, int],
                 pulses: int | None = None,
                 *args,
                 **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._color = pulsating_color
        self._frequency_hz = frequency_hz
        self._period = 1.0 / frequency_hz
        self._pulses = pulses

        for self._square in pulsating_squares:
            self._led_layer.colors[self._square] = self._color

    @property
    def squares(self) -> list[chess.Square]:
        return list(self._led_layer.colors.keys())

    @squares.setter
    def squares(self, new_squares: list[chess.Square]) -> None:
        self._led_layer.reset()
        for square in new_squares:
            self._led_layer.colors[square] = self._color

    def update(self) -> bool:

        amplitude = abs(- 0.5 * math.cos(2 * math.pi * self._frequency_hz * self.elapsed_time) + 0.5)
        amplitude = min(1.0, max(0.0, amplitude))

        self._led_layer.layer_opacity = amplitude

        if self._pulses is None:
            return False  # Infinite pulses

        return self.elapsed_time >= self._period * self._pulses

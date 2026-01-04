import chess
from chessboard.animations.animation import Animation


class AnimationChangeSide(Animation):
    def __init__(self, duration: float, new_side: chess.Color, *args, **kwargs) -> None:
        """ Animation to change the side of the board being displayed.

        duration: Duration of the side change animation in seconds.
        new_side: chess.WHITE or chess.BLACK indicating the side to change to.
        """
        super().__init__(*args, **kwargs)

        self._change_to = new_side

        self._current_position = 7.0 / 2.0  # Start in the middle

        self._movement_per_frame = 7.0 / (self._fps * duration)

    def set_side(self, new_side: chess.Color) -> None:
        self._change_to = new_side
        self.restart()

    def update(self) -> bool:
        intensity_max = 1.5
        intensity_min = 0.2

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

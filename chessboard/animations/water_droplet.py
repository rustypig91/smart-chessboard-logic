import chess
import math

from chessboard.animations.animation import Animation


class AnimationWaterDroplet(Animation):
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
        # self._damp = 0.12   # amplitude decay per radius unit
        self._damp = 0.12
        self._boost = 1.0   # overall brightness boost at wavefront

    def update(self) -> bool:
        index = self.frame_index

        # t = index / (self.total_frames - 1) if self.total_frames > 1 else 1.0
        t = self.elapsed_time

        radius = t * self._max_radius

        r0 = chess.square_rank(self._center)
        f0 = chess.square_file(self._center)

        # Expanding circular ripple: modulate the provided base frame intensities
        for sq in chess.SQUARES:
            self._led_layer.colors[sq] = (150, 150, 150)

            r = chess.square_rank(sq)
            f = chess.square_file(sq)
            dist = math.sqrt((r - r0)**2 + (f - f0)**2)
            # Gaussian window around the wavefront radius for a thin ring
            gauss = math.exp(-((dist - radius)**2) / (2 * self._sigma**2))
            # Damping with distance to emulate energy loss in water
            amplitude = gauss * math.exp(-self._damp * radius) * self._boost

            # Scale base color upwards (brighten) at the wavefront
            # scale = 1.0 + amplitude
            # self._led_layer.intensity.update({sq: scale})
            self._led_layer.square_opacity[sq] = amplitude

        # Highlight the center at the start by boosting base color
        # if index == 0 and self._center in self._base_colors and self._base_colors[self._center] is not None:
        #     base = self._base_colors[self._center]
        #     scale = 1.5
        #     boosted = (min(255, int(base[0] * scale)),
        #                min(255, int(base[1] * scale)),
        #                min(255, int(base[2] * scale)))
        #     colors[self._center] = boosted

        return radius >= self._max_radius

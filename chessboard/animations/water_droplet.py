import chess
import math

from chessboard.animations.animation import Animation


class AnimationWaterDroplet(Animation):
    def __init__(self,
                 color: tuple[int, int, int],
                 center_square: chess.Square,
                 *args,
                 **kwargs) -> None:
        """ Water droplet ripple animation originating from a center square.

        color: RGB color tuple for the droplet ripple.
        center_square: chess.Square where the droplet originates.        
        """
        super().__init__(*args, **kwargs)

        self._center = center_square

        r0 = chess.square_rank(self._center)
        f0 = chess.square_file(self._center)
        # Max Euclidean radius to any corner for smooth circular wave
        corners = [(0, 0), (0, 7), (7, 0), (7, 7)]
        self._max_radius = max(math.sqrt((r0 - r)**2 + (f0 - f)**2) for r, f in corners)

        for sq in chess.SQUARES:
            self._led_layer.colors[sq] = color

        # Wave parameters: narrow ring (sigma) and damping
        self._sigma = 0.75  # ring thickness
        self._damp = 0.12   # damping factor
        self._boost = 1.0   # overall brightness boost at wavefront

    def update(self) -> bool:
        radius = self.elapsed_time * self._max_radius

        r0 = chess.square_rank(self._center)
        f0 = chess.square_file(self._center)

        for sq in chess.SQUARES:
            r = chess.square_rank(sq)
            f = chess.square_file(sq)
            dist = math.sqrt((r - r0)**2 + (f - f0)**2)
            # Gaussian window around the wavefront radius for a thin ring
            gauss = math.exp(-((dist - radius)**2) / (2 * self._sigma**2))
            # Damping with distance to emulate energy loss in water
            amplitude = gauss * math.exp(-self._damp * radius) * self._boost
            amplitude = min(1.0, max(0.0, amplitude)) * 0.2

            self._led_layer.square_opacity[sq] = amplitude

        return radius >= self._max_radius

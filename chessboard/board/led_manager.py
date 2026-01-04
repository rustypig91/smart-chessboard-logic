import chess
from enum import IntEnum
import weakref
import chessboard.events as events
from chessboard.settings import settings, ColorSetting
from chessboard.thread_safe_variable import ThreadSafeVariable
from threading import Lock


settings.register('led.color.white_square', ColorSetting((150, 150, 150)),
                  "Base color for white squares on the chessboard LEDs")
settings.register('led.color.black_square', ColorSetting((0, 0, 0)),
                  "Base color for black squares on the chessboard LEDs")


class LedLayer:
    def __init__(self, priority: int) -> None:
        self.priority: int = priority
        self.colors: dict[int, tuple[int, int, int]] = {}

        # Change intensity per square if needed i.e. make square more bright or dim 1.0 is default, no change
        self.intensity: dict[int, float] = {}

        # Opacity per square (0.0 - 1.0)
        self.square_opacity: dict[int, float] = {}

        # Default opacity if not specified per square
        self.layer_opacity: float = 1.0

        self._commited_colors: dict[int, tuple[int, int, int]] = {}
        self._commited_intensity: dict[int, float] = {}
        self._commited_square_opacity: dict[int, float] = {}
        self._commited_layer_opacity: float = 1.0

        self._lock = Lock()

    def __del__(self) -> None:
        """ Ensure the layer is removed from the LED manager on deletion. """
        led_manager.remove_layer(self)
        led_manager.apply_layers()

    def reset(self) -> None:
        """ Reset the layer to default state. """
        with self._lock:
            self.colors.clear()
            self.intensity.clear()
            self.square_opacity.clear()
            self.layer_opacity = 1.0

    def commit(self) -> None:
        """ Commit the current settings to be applied. """
        with self._lock:
            self._commited_colors = self.colors.copy()
            self._commited_intensity = self.intensity.copy()
            self._commited_square_opacity = self.square_opacity.copy()
            self._commited_layer_opacity = self.layer_opacity

        led_manager.apply_layers()

    def apply_layer(self, board_colors: dict[int, tuple[int, int, int]]):
        """ Modify the layer colors with the provided colors. """

        with self._lock:
            colors = self._commited_colors
            intensity = self._commited_intensity
            square_opacity = self._commited_square_opacity
            layer_opacity = self._commited_layer_opacity

            for square, color in colors.items():
                if square >= len(chess.SQUARES):
                    raise ValueError(f"Square {square} is out of bounds")

                r1, g1, b1 = board_colors[square]
                r2, g2, b2 = color

                opacity = square_opacity.get(square, layer_opacity)
                opacity = min(max(opacity, 0.0), 1.0)  # Clamp between 0.0 and 1.0

                r_final = int(r1 * (1 - opacity) + r2 * opacity)
                g_final = int(g1 * (1 - opacity) + g2 * opacity)
                b_final = int(b1 * (1 - opacity) + b2 * opacity)

                board_colors[square] = (r_final, g_final, b_final)

            for square, intensity_value in intensity.items():
                if square >= len(chess.SQUARES):
                    raise ValueError(f"Square {square} is out of bounds")

                r, g, b = board_colors[square]

                r = int(max(0, min(255, r * intensity_value)))
                g = int(max(0, min(255, g * intensity_value)))
                b = int(max(0, min(255, b * intensity_value)))
                board_colors[square] = (r, g, b)

        return board_colors


class _LedManager:
    def __init__(self) -> None:
        self.base_colors = {}
        white_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1]
        black_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]

        for square in white_squares:
            self.base_colors[square] = settings['led.color.white_square']
        for square in black_squares:
            self.base_colors[square] = settings['led.color.black_square']

        # Track layers weakly so they auto-remove when destroyed
        self._layers: weakref.WeakSet[LedLayer] = weakref.WeakSet()
        self._lock = Lock()

        self.apply_layers()

    @property
    def colors(self) -> dict[int, tuple[int, int, int]]:
        """ Get the current colors after applying all layers. """
        final_colors = self.base_colors.copy()

        with self._lock:
            # Apply layers in ascending priority order
            for layer in sorted(list(self._layers), key=lambda l: l.priority):
                layer.apply_layer(final_colors)

        return final_colors

    def apply_layers(self) -> None:
        """ Apply the LED layers and return the final colors for each square. """
        events.event_manager.publish(events.SetSquareColorEvent(self.colors))

    def add_layer(self, layer: LedLayer) -> None:
        with self._lock:
            if layer in self._layers:
                raise ValueError("Layer already added to LED manager")

            self._layers.add(layer)
            # Do not attempt to sort the WeakSet; ordering is applied when iterating

    def remove_layer(self, layer: LedLayer) -> None:
        """Explicitly remove a layer if present."""
        with self._lock:
            try:
                self._layers.discard(layer)
            except Exception:
                # WeakSet.discard does not raise if not present; keep silent
                pass

    def has_layer(self, layer: LedLayer) -> bool:
        with self._lock:
            return layer in self._layers


led_manager = _LedManager()

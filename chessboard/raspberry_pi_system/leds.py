import chess

from chessboard.logger import log
import chessboard.events as events
import rpi_ws281x as ws  # type: ignore


def _square_to_led_index(square: chess.Square) -> int:
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    if file % 2 != 0:
        rank = 7 - rank

    return file * 8 + rank


def _set_colors(strip: ws.PixelStrip, squares: list[chess.Square], color: tuple[int, int, int]):
    for square in squares:
        led_index = _square_to_led_index(square)
        strip.setPixelColor(led_index, ws.Color(*color))


class _BoardLeds:
    LED_COUNT = 64
    LED_PIN = 18
    LED_FREQ_HZ = 800000
    LED_DMA = 10
    LED_BRIGHTNESS = 255
    LED_INVERT = False

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(_BoardLeds, cls).__new__(cls)
            cls.instance._initialized = False

        return cls.instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        self.__strip = None
        self._powering_off = False

        events.event_manager.subscribe(
            events.SetSquareColorEvent, self._handle_set_square_color_event)

        events.event_manager.subscribe(events.SystemShutdownEvent, self._handle_shutdown_event)

    def __del__(self):
        self._turn_off_all_leds()

    def _handle_shutdown_event(self, event: events.SystemShutdownEvent):
        self._powering_off = True
        self._turn_off_all_leds()

    @property
    def _strip(self) -> ws.PixelStrip:
        if self.__strip is not None:
            return self.__strip

        self.__strip = ws.PixelStrip(self.LED_COUNT, self.LED_PIN, self.LED_FREQ_HZ,
                                     self.LED_DMA, self.LED_INVERT, self.LED_BRIGHTNESS)
        self.__strip.begin()
        log.info("LED strip initialized")

        return self.__strip

    def _turn_off_all_leds(self):
        _set_colors(self._strip, chess.SQUARES, (0, 0, 0))
        self._strip.show()

    def _handle_set_square_color_event(self, event: events.SetSquareColorEvent):
        """ Handles SetSquareColorEvent to set specific colors on squares. """
        if self._powering_off:
            return

        for square, color in event.color_map.items():
            if color is not None:
                _set_colors(self._strip, [square], color)

        self._strip.show()


board_leds = _BoardLeds()

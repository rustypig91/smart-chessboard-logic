import serial
import re
from time import sleep, time
from threading import Thread, Lock
from typing import Callable
import chess

from chessboard.settings import settings
from chessboard.logger import log
from chessboard.events import event_manager, HalSensorVoltageEvent, PieceLiftedEvent, PiecePlacedEvent, SquarePieceStateChange
import os

from RPi import GPIO  # type: ignore


settings.register('hal_sensor.offset', 0.07, description="Voltage offset in volts")
settings.register('hal_sensor.piece_detection_consecutive', 2,
                  description="Number of consecutive readings to confirm piece detection")


class _HalSensorsInterface:
    PROMPT = "chess:~$"
    BAUDRATE = 115200
    RESET_PIN = 21
    DEVICE_PATH = '/dev/ttyACM0'

    DEFAULT_SENSOR_PIECE_OFFSET_MV = 100

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(_HalSensorsInterface, cls).__new__(cls)
            cls.instance._initialized = False

        return cls.instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._port = None
        self._monitoring = False
        self._monitor_thread = None
        self._board_piece_colors: list[chess.Color | None | str] = [None] * 64
        self._board_piece_consecutive_counts: list[int] = [0] * 64

        self._monitor_start()

    def __del__(self):
        self._monitor_stop()
        if self._port is not None:
            self._port.close()

    def start(self):
        if not self._monitoring:
            self._monitor_start()

    def stop(self):
        if self._monitoring:
            self._monitor_stop()

    @property
    def port(self):
        if self._port is None:
            self._reset_device()

        return self._port

    def calibrate_sensors(self):
        """Calibrate the HAL sensors when no pieces are on the board.

        Warning: No pieces shall be on the board when this is called.
        """

        self._monitor_stop()
        self._send_command('board calibrate set')
        self._monitor_start()

    def _reset_device(self):
        if self._port is not None:
            self._port.close()
            self._port = None

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.RESET_PIN, GPIO.OUT)

        log.info("Resetting HAL sensor device via GPIO pin.")

        GPIO.output(self.RESET_PIN, GPIO.LOW)
        timeout = 5  # seconds
        start = time()
        while os.path.exists(self.DEVICE_PATH):
            if time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for {self.DEVICE_PATH} to become unavailable.")
            sleep(0.1)
        GPIO.output(self.RESET_PIN, GPIO.HIGH)
        # Wait for DEVICE_PATH to become available
        timeout = 5  # seconds
        start = time()
        while not os.path.exists(self.DEVICE_PATH):
            if time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for {self.DEVICE_PATH} to become available.")
            sleep(0.1)

        sleep(1)  # Wait for the serial connection to stabilize
        self._port = serial.Serial(
            self.DEVICE_PATH, baudrate=self.BAUDRATE, timeout=1)
        sleep(1)
        self._port.flush()

    def _monitor_start(self):
        if self._monitoring:
            raise RuntimeError("Monitor is already running.")

        self._monitoring = True
        self._monitor_thread = Thread(target=self._monitor_thread_func)
        self._monitor_thread.start()

    def _monitor_stop(self):
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_thread is not None:
            self._monitor_thread.join()
            self._monitor_thread = None

        log.info("HAL sensor monitoring stoped")

    def _monitor_thread_func(self):
        if self.port is None:
            return

        self.port.write(b'board monitor offset\n')

        log.info("HAL sensor monitoring started")

        # Regular expression to match a line with file and ranks
        exp_file = r'^(?P<file>[A-H])\|(?P<ranks>( *-?\d+ *\|){7} *-?\d+ *)$'

        first_scan_completed = False

        while self._monitoring:
            line = self.port.readline().decode('utf-8').strip()
            match = re.match(exp_file, line)
            if match:
                file_char = match.group('file').strip()
                file_index = ord(file_char) - ord('A')
                ranks = match.group('ranks').strip('|').strip()
                ranks = ranks.split('|')

                changed_squares = []
                for rank_index, value_mv in enumerate([int(x) for x in ranks]):
                    square = chess.square(file_index, rank_index)
                    voltage = value_mv * 1e-3

                    event_manager.publish(
                        HalSensorVoltageEvent(square, voltage))

                    # Require both current and previous voltage to exceed offset
                    if voltage >= settings['hal_sensor.offset']:
                        new_color = chess.BLACK
                    elif voltage <= -settings['hal_sensor.offset']:
                        new_color = chess.WHITE
                    else:
                        new_color = None

                    current_color = self._board_piece_colors[square]
                    if new_color == current_color:
                        self._board_piece_consecutive_counts[square] += 1
                    else:
                        self._board_piece_colors[square] = new_color
                        self._board_piece_consecutive_counts[square] = 1

                    if self._board_piece_consecutive_counts[square] == settings['hal_sensor.piece_detection_consecutive']:
                        changed_squares.append(square)

                if first_scan_completed:
                    if len(changed_squares) > 0:
                        event_manager.publish(SquarePieceStateChange(changed_squares, self._board_piece_colors))
                elif not first_scan_completed and all(count >= settings['hal_sensor.piece_detection_consecutive'] for count in self._board_piece_consecutive_counts):
                    first_scan_completed = True
                    event_manager.publish(SquarePieceStateChange(chess.SQUARES, self._board_piece_colors))

        self.port.write(b'q')
        self._wait_for_prompt()

    def _wait_for_prompt(self, timeout: float = 5.0) -> str:
        if self.port is None:
            return ""

        output = ""
        start_time = time()
        while True:
            if time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for prompt from Xiao.")
            if self.port.in_waiting:
                response = self.port.read(
                    self.port.in_waiting).decode('utf-8')
                output += response
                if self.PROMPT in output:
                    break
            else:
                sleep(0.01)

        return output.split(self.PROMPT)[0]

    def _send_command(self, command: str) -> str:
        if self.port is None:
            return ""

        while self.port.in_waiting > 0:
            self.port.read(self.port.in_waiting)

        self.port.write(command.encode('utf-8') + b'\n')
        self.port.flush()

        return self._wait_for_prompt()


hal_sensors = _HalSensorsInterface()

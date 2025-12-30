from RPi import GPIO  # type: ignore
import serial
import serial.tools.list_ports
import re
from time import sleep, time
from threading import Thread
import chess

from chessboard.settings import settings
from chessboard.logger import log
import chessboard.events as events
import subprocess

import os
import shutil
import tempfile


settings.register('hal_sensor.offset', 0.10, description="Voltage offset in volts")


class _XiaoInterface:
    PROMPT = "chess:~$"
    BAUDRATE = 115200
    RESET_PIN = 21
    DEVICE_DESC = 'Chessboard console'

    DEFAULT_SENSOR_PIECE_OFFSET_MV = 100
    CONSECUTIVE_READINGS_REQUIRED = 1

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(_XiaoInterface, cls).__new__(cls)
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

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.RESET_PIN, GPIO.OUT)

        events.event_manager.subscribe(events.SystemShutdownEvent, self._handle_shutdown_event)

    def _handle_shutdown_event(self, event: events.SystemShutdownEvent):
        log.info("Xiao device shutdown started")
        self._shutdown_device()
        log.info("Xiao device shutdown completed")

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

    def flash_firmware(self, firmware_path: str):
        """Flash new firmware to the Xiao device using the bootloader.

        Args:
            firmware_path (str): Path to the .bin firmware file.
        """

        self._start_bootloader()

        log.info(f"Flashing firmware {firmware_path} to Xiao device...")

        storage_device = self._find_bootloader_storage_device()
        if storage_device is None:
            log.error("Xiao bootloader storage device not found, flashing aborted")
            return

        success = False
        with tempfile.TemporaryDirectory() as mount_dir:
            try:
                subprocess.run(['mount', storage_device, mount_dir], check=True)
                firmware_filename = os.path.basename(firmware_path)
                target_path = os.path.join(mount_dir, firmware_filename)
                shutil.copyfile(firmware_path, target_path)
                success = True

            except Exception as e:
                log.error(f"Error flashing firmware: {e}")
                raise
            finally:
                subprocess.run(['umount', mount_dir], check=True)

        sleep(1)  # Wait for the device to process the new firmware

        if success:
            log.info("Firmware flashed successfully")
        else:
            log.error("Firmware flashing failed")

        self._monitor_start()

    @property
    def port(self):
        if self._port is None:
            self._reset_device()

        return self._port

    def _set_reset_pin(self, value):
        GPIO.output(self.RESET_PIN, value)

    def calibrate_sensors(self):
        """Calibrate the HAL sensors when no pieces are on the board.

        Warning: No pieces shall be on the board when this is called.
        """

        self._monitor_stop()
        self._send_command('board calibrate set')
        self._monitor_start()

    def _find_tty_device(self) -> str | None:
        """ Find the TTY device corresponding to the HAL sensor device. """
        device = None
        for port in serial.tools.list_ports.comports():
            if self.DEVICE_DESC in port.description:
                device = port.device
                break

        return device

    @staticmethod
    def _find_bootloader_storage_device(timeout: float = 5.0) -> str | None:
        """ Find the device path corresponding to the Xiao bootloader. """

        # Use lsblk to check if the device has a label or model indicating it's the Xiao bootloader
        start = time()

        while True:
            if time() - start > timeout:
                log.error("Timeout waiting for Xiao bootloader storage device")
                return None

            result = subprocess.run(['lsblk', '-no', 'PATH,LABEL'], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if 'Arduino' in line:
                    return line.split()[0]

            sleep(0.5)

    def _shutdown_device(self):
        if self._monitoring:
            self._monitor_stop()

        if self._port is not None:
            self._port.close()
            self._port = None

        self._set_reset_pin(GPIO.LOW)
        sleep(0.1)

        timeout = 5  # seconds
        start = time()

        tty_device = self._find_tty_device()

        while tty_device is not None:
            if time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for {tty_device} to become unavailable")
            sleep(0.1)
            tty_device = self._find_tty_device()

    def _start_bootloader(self):
        self._shutdown_device()

        self._set_reset_pin(GPIO.LOW)
        sleep(0.1)
        self._set_reset_pin(GPIO.HIGH)
        sleep(0.1)
        self._set_reset_pin(GPIO.LOW)
        sleep(0.1)
        self._set_reset_pin(GPIO.HIGH)
        sleep(1)
        log.info("Xiao bootloader started")

    def _reset_device(self):
        if self._port is not None:
            self._port.close()
            self._port = None

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.RESET_PIN, GPIO.OUT)

        log.info("Resetting HAL sensor device via GPIO pin")

        GPIO.output(self.RESET_PIN, GPIO.LOW)
        sleep(0.1)

        timeout = 5  # seconds
        start = time()

        tty_device = self._find_tty_device()

        while tty_device is not None:
            if time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for {tty_device} to become unavailable")
            sleep(0.1)
            tty_device = self._find_tty_device()

        GPIO.output(self.RESET_PIN, GPIO.HIGH)
        # Wait for DEVICE_PATH to become available
        timeout = 5  # seconds
        start = time()

        while tty_device is None:
            if time() - start > timeout:
                raise TimeoutError(f"Timeout waiting for {tty_device} to become available")
            sleep(0.1)
            tty_device = self._find_tty_device()

        sleep(1)  # Wait for the serial connection to stabilize
        self._port = serial.Serial(
            tty_device, baudrate=self.BAUDRATE, timeout=1)
        sleep(1)
        self._port.flush()

    def _monitor_start(self):
        if self._monitoring:
            raise RuntimeError("Monitor is already running")

        self._monitoring = True
        self._monitor_thread = Thread(target=self._monitor_thread_func, daemon=True)
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
                file_char = match.group('file')
                file_index = ord(file_char) - ord('A')
                ranks = match.group('ranks').split('|')

                changed_squares = []
                for rank_index, value_mv in enumerate(ranks):
                    square = chess.square(file_index, rank_index)
                    voltage = int(value_mv) * 1e-3
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

                    if self._board_piece_consecutive_counts[square] == self.CONSECUTIVE_READINGS_REQUIRED:
                        changed_squares.append(square)

                if first_scan_completed:
                    if len(changed_squares) > 0:
                        log.warning(f"First scan completed: {first_scan_completed}, changed squares: {changed_squares}")
                        events.event_manager.publish(events.SquarePieceStateChangeEvent(
                            changed_squares, self._board_piece_colors))
                elif not first_scan_completed and all(count >= self.CONSECUTIVE_READINGS_REQUIRED for count in self._board_piece_consecutive_counts):
                    first_scan_completed = True
                    events.event_manager.publish(events.SquarePieceStateChangeEvent(
                        chess.SQUARES, self._board_piece_colors))

        self.port.write(b'q')
        self._wait_for_prompt()

    def _wait_for_prompt(self, timeout: float = 5.0) -> str:
        if self.port is None:
            return ""

        output = ""
        start_time = time()
        while True:
            if time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for prompt from Xiao")
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


xiao_interface = _XiaoInterface()

if __name__ == "__main__":
    print("Starting Xiao bootloader...")
    xiao_interface._start_bootloader()
    xiao_interface.stop()

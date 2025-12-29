import logging
import sys


class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',    # Blue
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[95m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)

log_format = ColoredFormatter(
    '%(asctime)s %(levelname)s (%(threadName)s): %(message)s'
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(log_format)

log.addHandler(console_handler)
print("Logger initialized")

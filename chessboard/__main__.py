import os
import io
import argparse

from flask_socketio import SocketIO
from chessboard.game.board import board
import chessboard.events as events
import chessboard.api.api as api
from chessboard.logger import log

is_raspberrypi = False
if os.name != 'posix':
    is_raspberrypi = False
try:
    with io.open('/proc/cpuinfo', 'r') as cpuinfo:
        for line in cpuinfo:
            if line.startswith('Model') and 'Raspberry Pi' in line:
                is_raspberrypi = True

except Exception:
    is_raspberrypi = False


if is_raspberrypi:
    import chessboard.raspberry_pi_system


parser = argparse.ArgumentParser(description="Chessboard Web App")
parser.add_argument('--new-game', action='store_true', help='Start a new game instead of loading the old one')
args = parser.parse_args()

if args.new_game:
    board.new_game()

api.socketio.run(api.app, debug=False)

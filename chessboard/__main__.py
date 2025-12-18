import os
import io
import argparse

import chess
from chessboard.game.board import board
import chessboard.events as events
import chessboard.api.api as api

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
parser.add_argument('--engine-weight', type=str, default=None,
                    help='Engine weight file to use for the engine (if applicable)')
parser.add_argument('--engine-color', type=chess.Color, default=chess.BLACK,
                    help='Engine color to use for the engine (if applicable)')
args = parser.parse_args()

if args.new_game:
    board.new_game(engine_weight=args.engine_weight, engine_color=args.engine_color)

api.socketio.run(api.app, debug=False, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

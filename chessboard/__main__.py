import argparse
import logging

import chess
from chessboard.game.game_state import game_state
import chessboard.events as events
import chessboard.api.api as api
from chessboard import is_raspberrypi
import chessboard.animations
from chessboard.logger import log


if is_raspberrypi:
    import chessboard.raspberry_pi_system

log.info("Is Raspberry Pi: %s", is_raspberrypi)

parser = argparse.ArgumentParser(description="Chessboard Web App")
parser.add_argument('--new-game', action='store_true', help='Start a new game instead of loading the old one')
parser.add_argument('--engine-weight', type=str, default=None,
                    help='Engine weight file to use for the engine (if applicable)')
parser.add_argument('--engine-color', type=chess.Color, default=chess.BLACK,
                    help='Engine color to use for the engine (if applicable)')
parser.add_argument('--debug', action='store_true', help='Enable debug mode')
parser.add_argument('--port', type=int, default=5000, help='Port to run the web server on')

args = parser.parse_args()

if args.debug:
    log.setLevel(logging.DEBUG)

if args.new_game:
    game_state.new_game(engine_weight=args.engine_weight, engine_color=args.engine_color)

api.socketio.run(api.app, debug=False, host='0.0.0.0', port=args.port, allow_unsafe_werkzeug=True)

import argparse

import chess
from chessboard.game.board_state import board_state
import chessboard.events as events
import chessboard.api.api as api
from chessboard import is_raspberrypi

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
    board_state.new_game(engine_weight=args.engine_weight, engine_color=args.engine_color)

api.socketio.run(api.app, debug=False, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

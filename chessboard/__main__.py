from gevent import monkey
monkey.patch_all()  # noqa

import argparse
import logging
import chess

from chessboard.logger import log
from chessboard import is_raspberrypi
import chessboard.persistent_storage as persistent_storage

if is_raspberrypi:
    import chessboard.raspberry_pi_system


def main():
    parser = argparse.ArgumentParser(description="Chessboard Web App")
    parser.add_argument('--new-game', action='store_true', help='Start a new game instead of loading the old one')
    parser.add_argument('--engine-weight', type=str, default=None,
                        help='Engine weight file to use for the engine (if applicable)')
    parser.add_argument('--engine-color', type=chess.Color, default=chess.BLACK,
                        help='Engine color to use for the engine (if applicable)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the web server on')
    parser.add_argument('--persistent-storage-dir', type=str, default=persistent_storage.PERSISTENT_STORAGE_DIR,
                        help='Directory to use for caching data')

    args = parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)

    if args.persistent_storage_dir:
        persistent_storage.set_persistent_storage_dir(args.persistent_storage_dir)
        log.info(f"Persistent storage directory set to: {args.persistent_storage_dir}")

    # Initialize system by importing necessary modules
    from chessboard.game.game_state import game_state
    import chessboard.events as events
    import chessboard.api.api as api
    import chessboard.animations
    import chessboard.game.analysis

    if args.new_game:
        game_state.new_game(engine_weight=args.engine_weight, engine_color=args.engine_color)

    api.socketio.run(api.app, debug=False, host='0.0.0.0', port=args.port, allow_unsafe_werkzeug=True)


main()

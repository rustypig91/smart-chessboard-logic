import os
import chess
import chess.engine
from chessboard.logger import log
from chessboard.settings import settings
from threading import Thread
from threading import Event
from typing import Callable, Optional
from random import choice

default_weights_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../weights'))

settings.register("engine.path", "lc0", "Path to the chess engine executable")
settings.register("engine.weights_path", default_weights_path,
                  "Path to the chess engine weights file (if applicable)")


class Engine:
    def __init__(self, time_limit: float, weight: str, color: chess.Color = chess.BLACK):
        weight_path = os.path.join(settings['engine.weights_path'], weight)
        if not os.path.isfile(weight_path):
            raise FileNotFoundError(f"Engine weights file not found: {weight_path}")

        # Thread to initialize the engine process; signal readiness via event
        self.engine = chess.engine.SimpleEngine.popen_uci([settings['engine.path'], f"--weights={weight_path}"])

        self.color = color
        self.time_limit = time_limit
        self.name = weight

    @staticmethod
    def get_available_weights() -> list[str]:
        weights_dir = settings['engine.weights_path']
        if not os.path.isdir(weights_dir):
            log.warning(f"Engine weights directory not found: {weights_dir}")
            return []

        weights = [f for f in os.listdir(weights_dir) if f.endswith('.pb.gz')]
        log.info(f"Available engine weights: {weights}")
        return weights

    def get_move(self, board: chess.Board) -> chess.Move:
        log.debug(f"Getting best move for board:\n{board.fen()}")
        # Ensure engine is initialized
        result = self.engine.play(board, chess.engine.Limit(depth=2))

        if result.move is None:
            log.error("Engine did not return a valid move.")
            raise ValueError("No valid move found by the engine.")

        log.info(f"Engine selected move: {result}")
        return result.move

    def get_move_async(self, board: chess.Board, callback: Callable[[chess.engine.PlayResult], None]) -> None:
        """Run engine.play in a background thread and invoke callback with the move.

        The callback receives a `chess.Move` or `None` if no valid move was found
        or an error occurred.
        """

        def _run():
            depth = choice([2, 3, 4])  # Randomize depth for variability
            try:
                log.debug("(async) Getting best move")
                result = self.engine.play(board, chess.engine.Limit(depth=depth))
                log.info(f"(async) Engine selected move: {result}")
                callback(result)
            except Exception as e:
                log.exception(f"Error during async engine play: {e}")

        t = Thread(target=_run)
        t.start()

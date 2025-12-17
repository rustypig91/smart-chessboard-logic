import os
import chess
import chess.engine
from chessboard.logger import log
from chessboard.settings import settings


settings.register("engine.path", "lc0", "Path to the chess engine executable")
settings.register("engine.weights_path", "/usr/share/chessboard-weights/",
                  "Path to the chess engine weights file (if applicable)")


class Engine:
    def __init__(self, time_limit: float, weight: str, color: chess.Color = chess.BLACK):
        weight = os.path.join(settings['engine.weights_path'], weight)
        if not os.path.isfile(weight):
            raise FileNotFoundError(f"Engine weights file not found: {weight}")

        # command = f"{settings['engine.path']} --weights {weight}"
        self.engine = chess.engine.SimpleEngine.popen_uci([settings['engine.path']] + [f"--weights={weight}"])

        self.color = color
        self.time_limit = time_limit

        # log.info(f"Initialized engine with command: {command}")

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

        result = self.engine.play(board, chess.engine.Limit(depth=2))

        if result.move is None:
            log.error("Engine did not return a valid move.")
            raise ValueError("No valid move found by the engine.")

        log.info(f"Engine selected move: {result}")
        return result.move

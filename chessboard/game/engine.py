import os
import chess
import chess.engine
from chessboard.logger import log
from chessboard.settings import settings
from threading import Thread
from typing import Callable
from random import choice
import chessboard.persistent_storage as persistent_storage
import shutil
import requests

settings.register("engine.path", "lc0", "Path to the chess engine executable")
settings.register("engine.time_limit", 10.0, "Time limit for engine analysis in seconds")


class Engine:
    def __init__(self, weight: str, color: chess.Color = chess.BLACK):
        self._weight_path = persistent_storage.get_filename(f'weights/{weight}')
        if not os.path.isfile(self._weight_path):
            raise FileNotFoundError(f"Engine weights file not found: {self._weight_path}")

        # Thread to initialize the engine process; signal readiness via event
        self.engine = chess.engine.SimpleEngine.popen_uci([settings['engine.path'], f"--weights={self._weight_path}"])

        self.color = color
        self.name = weight

    @staticmethod
    def install_weight(weight_file: str) -> None:
        """Install a new engine weight file from the given source path."""
        dest_path = persistent_storage.get_filename(f'weights/{os.path.basename(weight_file)}')

        if not os.path.isfile(weight_file):
            raise FileNotFoundError(f"Source weight file not found: {weight_file}")

        shutil.move(weight_file, dest_path)

        log.info(f"Installed new engine weight from {weight_file} to {dest_path}")

    @staticmethod
    def delete_weight(weight_name: str) -> None:
        """Delete an existing engine weight file by name."""
        weight_path = os.path.join(Engine.weight_directory(), weight_name)

        if not os.path.isfile(weight_path):
            raise FileNotFoundError(f"Weight file not found: {weight_path}")

        os.remove(weight_path)
        log.info(f"Deleted engine weight: {weight_name}")

    @staticmethod
    def install_weight_from_url(url: str) -> None:
        """Install a new engine weight file from a URL."""

        response = requests.get(url, stream=True)
        if response.status_code != 200:
            raise ValueError(f"Failed to download weight file from URL: {url}")

        filename = os.path.basename(url)
        dest_path = os.path.join(Engine.weight_directory(), filename)

        with open(dest_path, 'wb') as f:
            shutil.copyfileobj(response.raw, f)

        log.info(f"Installed new engine weight from URL {url} to {dest_path}")

    @staticmethod
    def weight_directory() -> str:
        """Get the directory where engine weights are stored."""
        return persistent_storage.get_directory('weights')

    @staticmethod
    def get_available_weights() -> list[str]:
        weights_dir = persistent_storage.get_directory('weights')
        if not os.path.isdir(weights_dir):
            log.warning(f"Engine weights directory not found: {weights_dir}")
            return []

        weights = [f for f in os.listdir(weights_dir) if f.endswith('.pb.gz')]
        log.info(f"Available engine weights: {weights}")

        weights.sort()

        return weights

    @staticmethod
    def get_weight_filename(weight: str) -> str:
        return os.path.join(Engine.weight_directory(), weight)

    def analyze(self, board: chess.Board) -> None:
        info = self.engine.analyse(board, chess.engine.Limit(time=settings['engine.time_limit']))
        log.warning(f"Engine analysis info: {info}")

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
                result = self.engine.play(board, chess.engine.Limit(time=settings['engine.time_limit'], depth=depth))
                log.info(f"(async) Engine selected move: {result}")

                callback(result)
                self.analyze(board)

            except Exception as e:
                log.exception(f"Error during async engine play: {e}")

        t = Thread(target=_run)
        t.start()

    def __getstate__(self) -> object:
        state = self.__dict__.copy()
        # Remove the engine process from the state to avoid serialization issues
        if 'engine' in state:
            del state['engine']
        return state

    def __setstate__(self, state: object) -> None:
        self.__dict__.update(state)  # type: ignore
        # Re-initialize the engine process after deserialization
        weight_path = os.path.join(settings['engine.weights_path'], self.name)
        self.engine = chess.engine.SimpleEngine.popen_uci([settings['engine.path'], f"--weights={weight_path}"])

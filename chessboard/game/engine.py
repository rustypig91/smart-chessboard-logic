import os
import time
import chess
import chess.engine
from chessboard.logger import log
from chessboard.settings import settings
from threading import Thread, Event
from typing import Callable
from random import choice
import chessboard.persistent_storage as persistent_storage
import shutil
import requests
import queue
import math
import chessboard.events as events
from chessboard.thread_safe_variable import ThreadSafeVariable

import atexit

settings.register("engine.player.time_limit", 10.0, "Time limit for engine analysis in seconds")

settings.register("engine.analysis.time_limit", 15.0, "Time limit for analysis in seconds")
settings.register("engine.analysis.depth_limit", 25, "Depth limit for analysis")
settings.register("engine.analysis.weight", "maia-1900.pb.gz", "Default engine weight file for analysis")


DOWNLOADABLE_WEIGHTS = {
    "maia-1100.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1100.pb.gz",
    "maia-1200.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1200.pb.gz",
    "maia-1300.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1300.pb.gz",
    "maia-1400.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1400.pb.gz",
    "maia-1500.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1500.pb.gz",
    "maia-1600.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1600.pb.gz",
    "maia-1700.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1700.pb.gz",
    "maia-1800.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1800.pb.gz",
    "maia-1900.pb.gz": "https://github.com/CSSLab/maia-chess/releases/download/v1.0/maia-1900.pb.gz",
}


def _cp_to_probs(cp: float, scale: float = 400.0) -> tuple[float, float]:
    """ Convert centipawn score to win probabilities for white and black. """
    p_white = 1.0 / (1.0 + math.exp(-cp / scale))
    return p_white, 1.0 - p_white


def _estimate_material_cp(board: chess.Board) -> int:
    """ Estimate material balance in centipawns. Positive means advantage for white. """
    values = {'p': 100, 'n': 320, 'b': 330, 'r': 500, 'q': 900, 'k': 0}
    total = 0
    for _, piece in board.piece_map().items():
        v = values[piece.symbol().lower()]
        total += v if piece.color == chess.WHITE else -v
    return total


def _probability_from_material(board: chess.Board) -> tuple[float, float]:
    """ Estimate win probabilities from material balance. """
    cp = _estimate_material_cp(board)
    return _cp_to_probs(float(cp))


def _probability_from_engine_score(score: chess.engine.PovScore) -> tuple[float, float]:
    """ Convert engine score to win probabilities for white and black. """
    s_white = score.white()
    if s_white.is_mate():
        mate_score = s_white.mate()
        cp = 100000 if mate_score is not None and mate_score > 0 else -100000
    else:
        cp = s_white.score(mate_score=100000)
    return _cp_to_probs(float(cp))


class _EngineGetMoveRequest:
    def __init__(self, weight: str, board: chess.Board, callback: Callable[[chess.engine.PlayResult], None]):
        self.weight = weight
        self.board = board
        self.callback = callback


class _EngineStartAnalysisRequest:
    def __init__(self, weight: str, board: chess.Board):
        self.weight = weight
        self.board = board


def install_weight(weight_file: str) -> None:
    """Install a new engine weight file from the given source path."""
    dest_path = persistent_storage.get_filename(f'weights/{os.path.basename(weight_file)}')

    if not os.path.isfile(weight_file):
        raise FileNotFoundError(f"Source weight file not found: {weight_file}")

    shutil.move(weight_file, dest_path)

    log.info(f"Installed new engine weight from {weight_file} to {dest_path}")


def delete_weight(weight_name: str) -> None:
    """Delete an existing engine weight file by name."""
    weight_path = os.path.join(weight_directory(), weight_name)

    if not os.path.isfile(weight_path):
        raise FileNotFoundError(f"Weight file not found: {weight_path}")

    os.remove(weight_path)
    log.info(f"Deleted engine weight: {weight_name}")


def install_weight_from_url(url: str) -> None:
    """Install a new engine weight file from a URL."""

    response = requests.get(url, stream=True)
    if response.status_code != 200:
        raise ValueError(f"Failed to download weight file from URL: {url}")

    filename = os.path.basename(url)
    dest_path = os.path.join(weight_directory(), filename)

    with open(dest_path, 'wb') as f:
        shutil.copyfileobj(response.raw, f)

    log.info(f"Installed new engine weight from URL {url} to {dest_path}")


def weight_directory() -> str:
    """Get the directory where engine weights are stored."""
    return persistent_storage.get_directory('weights')


def get_available_weights() -> list[str]:
    weights_dir = persistent_storage.get_directory('weights')
    if not os.path.isdir(weights_dir):
        log.warning(f"Engine weights directory not found: {weights_dir}")
        return []

    weights = [f for f in os.listdir(weights_dir) if f.endswith('.pb.gz')]
    log.info(f"Available engine weights: {weights}")

    for weight in DOWNLOADABLE_WEIGHTS.keys():
        if weight not in weights:
            weights.append(weight)

    weights.sort()

    return weights


def get_weight_filename(weight: str) -> str:
    return os.path.join(weight_directory(), weight)


def get_weight_file(weight: str, try_download: bool = False) -> str | None:
    weight_path = persistent_storage.get_filename(f'weights/{weight}')
    if os.path.isfile(weight_path):
        return weight_path
    elif try_download:
        # Try to download the weight file
        download_url = DOWNLOADABLE_WEIGHTS.get(weight)
        if download_url is None:
            log.warning(f"No download URL found for weight: {weight}")
            return None
        install_weight_from_url(download_url)
        if os.path.isfile(weight_path):
            return weight_path
        else:
            log.warning(f"Engine weight file not found after download attempt: {weight_path}")
            return None


class _Lc0Engine:
    ENGINE_COMMAND = "lc0"

    def __init__(self):
        self._analysis_queue = queue.Queue()

        events.event_manager.subscribe(events.GameStateChangedEvent, self._handle_chess_move_event)

        self._current_weight = ThreadSafeVariable[str | None](None)

        self._engine_thread = Thread(target=self._engine_worker, daemon=True)
        self._engine_thread.start()

    def _find_weight_file(self) -> str | None:
        weight_dir = persistent_storage.get_directory('weights')
        candidates = [
            f for f in os.listdir(weight_dir)
            if os.path.isfile(os.path.join(weight_dir, f))
        ]

        if not candidates:
            return None

        latest = max(candidates, key=lambda f: os.path.getmtime(os.path.join(weight_dir, f)))
        return latest

    def _handle_chess_move_event(self, event: events.GameStateChangedEvent) -> None:
        self._analysis_queue.put(_EngineStartAnalysisRequest(
            weight=settings['engine.analysis.weight'],
            board=event.board.copy()
        ))

    def _set_weight(self, engine: chess.engine.SimpleEngine, weight: str) -> None:
        weight_path = get_weight_file(weight, try_download=True)
        if weight_path is None:
            raise FileNotFoundError(f"Engine weights file not found: {weight_path}")

        if self._current_weight.value == weight:
            return

        engine.configure({"WeightsFile": weight_path})
        self._current_weight.value = weight

        log.info(f"Engine weight set to: {weight}")

    def __del__(self):
        self.stop()

    def stop(self) -> None:
        """Stop the engine and its worker thread."""
        if not self._engine_thread.is_alive():
            self._analysis_queue.put(None)
            self._engine_thread.join(timeout=5.0)

    def start(self) -> None:
        """Start the engine worker thread."""
        if not self._engine_thread.is_alive():
            self._engine_thread = Thread(target=self._engine_worker, daemon=True)
            self._engine_thread.start()

    def get_move_async(self, weight: str, board: chess.Board, callback: Callable[[chess.engine.PlayResult], None]) -> None:
        """Request the engine to select a move for the given board position."""
        self._analysis_queue.put(_EngineGetMoveRequest(weight, board, callback))

    def _get_move(self, engine: chess.engine.SimpleEngine, enboard: chess.Board, callback: Callable[[chess.engine.PlayResult], None]) -> None:
        depth = choice([2, 3, 4])  # Randomize depth for variability
        try:
            result = engine.play(enboard, chess.engine.Limit(
                time=settings['engine.player.time_limit'], depth=depth))

            log.info(f"Engine selected move: {result}")

            callback(result)

        except Exception as e:
            log.exception(f"Error during engine play: {e}")

    def _start_analysis(self, engine: chess.engine.SimpleEngine, board: chess.Board) -> None:
        total_limit = settings['engine.analysis.time_limit']
        depth_limit = settings['engine.analysis.depth_limit']
        limit = chess.engine.Limit(time=total_limit, depth=depth_limit)

        current_weight = self._current_weight.value
        assert current_weight is not None

        analysis_event = events.EngineAnalysisEvent(board, current_weight)
        analysis_event.white_win_prob, analysis_event.black_win_prob = _probability_from_material(board)

        with engine.analysis(board, limit, info=chess.engine.INFO_ALL) as analysis:
            for info in analysis:
                score = info.get('score')
                if score is not None:
                    analysis_event.white_win_prob, analysis_event.black_win_prob = _probability_from_engine_score(score)
                    analysis_event.score = score.white().score(mate_score=100000)

                analysis_event.pv = info.get('pv', [])
                analysis_event.depth = info.get('depth', 0)

                events.event_manager.publish(analysis_event)

                # Cancel if a newer request arrived
                if not self._analysis_queue.empty():
                    break

    def _engine_worker(self) -> None:
        engine = chess.engine.SimpleEngine.popen_uci([_Lc0Engine.ENGINE_COMMAND])
        self._set_weight(engine, settings['engine.analysis.weight'])

        log.info(f"Engine '{_Lc0Engine.ENGINE_COMMAND}' initialized")

        while True:
            event = self._analysis_queue.get()
            try:
                if event is None:
                    break
                elif isinstance(event, _EngineStartAnalysisRequest):
                    self._set_weight(engine, event.weight)
                    self._start_analysis(engine, event.board)
                elif isinstance(event, _EngineGetMoveRequest):
                    self._set_weight(engine, event.weight)
                    self._get_move(engine, event.board, event.callback)
            except Exception as e:
                log.exception(f"Error in engine worker: {e}")

        engine.quit()
        engine.close()

        log.info(f"Engine '{_Lc0Engine.ENGINE_COMMAND}' shut down")


engine = _Lc0Engine()
atexit.register(engine.stop)

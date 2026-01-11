import os
import time
import chess
import chess.engine
from chessboard.logger import log
from chessboard.settings import settings
from threading import Thread, Event, current_thread, Lock
from random import choice
import chessboard.persistent_storage as persistent_storage
import shutil
import requests
import queue
import math
import chessboard.events as events
from chessboard.thread_safe_variable import ThreadSafeVariable

import atexit

settings.register("engine.player.time_limit", 20.0, "Time limit for engine analysis in seconds")

settings.register("engine.analysis.time_limit", 25.0, "Time limit for analysis in seconds")
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
    def __init__(self, weight: str, board: chess.Board, min_depth: int, max_depth: int):
        self.weight = weight
        self.board = board
        self.min_depth = min_depth
        self.max_depth = max_depth
        if self.min_depth < 1:
            self.min_depth = 1
        if self.max_depth < self.min_depth:
            self.max_depth = self.min_depth

    def __repr__(self):
        return (f"_EngineGetMoveRequest(weight={self.weight}, "
                f"board_fen={self.board.fen()}, "
                f"min_depth={self.min_depth}, max_depth={self.max_depth})")


class _EngineStartAnalysisRequest:
    ID_LOCK = Lock()
    NEXT_ID: int = 0

    def __init__(self, weight: str, board: chess.Board, stop_on_new_request: bool = True):
        self.weight = weight
        self.board = board
        self.stop_on_new_request = stop_on_new_request
        with _EngineStartAnalysisRequest.ID_LOCK:
            self.id = _EngineStartAnalysisRequest.NEXT_ID
            next_id = (self.id + 1) % 0x100000000  # Wrap around at 2^32
            _EngineStartAnalysisRequest.NEXT_ID = next_id

    def __repr__(self):
        return (f"_EngineStartAnalysisRequest("
                f"weight={self.weight}, "
                f"board_fen={self.board.fen()}, "
                f"id={self.id}), "
                f"stop_on_new_request={self.stop_on_new_request})")


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

        self.__engine = None
        self.__engine_weight: str | None = None

        self._engine_stop = Event()

        self._engine_thread = Thread(target=self._engine_worker, daemon=True)
        self._engine_thread.start()

    def _handle_chess_move_event(self, event: events.GameStateChangedEvent) -> None:
        self._analysis_queue.put(_EngineStartAnalysisRequest(
            weight=settings['engine.analysis.weight'],
            board=event.board,
            stop_on_new_request=True
        ))

    def __del__(self):
        self.stop()

    def stop(self) -> None:
        """Stop the engine and its worker thread."""
        self._engine_stop.set()
        if self._engine_thread.is_alive():
            self._analysis_queue.put(None)  # Unblock the queue
            self._engine_thread.join(timeout=5.0)

            if self.__engine is not None and not self.__engine.protocol.returncode.done():
                self.__engine.quit()
                self.__engine.close()

    def start(self) -> None:
        """Start the engine worker thread."""
        if not self._engine_thread.is_alive():
            self._engine_stop.clear()
            self._engine_thread = Thread(target=self._engine_worker, daemon=True)
            self._engine_thread.start()

    def get_move_async(self, weight: str, board: chess.Board, min_depth: int = 2, max_depth: int = 4) -> None:
        """Request the engine to select a move for the given board position."""
        self._analysis_queue.put(_EngineGetMoveRequest(weight, board, min_depth, max_depth))

    def get_analysis_async(self, weight: str, board: chess.Board) -> int:
        """Request the engine to start analysis for the given board position."""
        event = _EngineStartAnalysisRequest(weight, board, stop_on_new_request=False)
        self._analysis_queue.put(event)
        return event.id

    def _get_engine(self, weight: str) -> chess.engine.SimpleEngine:
        """Get the current engine instance or initialize it if not running.

        Note: Only allowed to be called from the engine worker thread.

        Returns:
            chess.engine.SimpleEngine: The engine instance.
        """
        if current_thread() != self._engine_thread:
            raise RuntimeError("_get_engine must be called from the engine worker thread")

        if self.__engine is None or self.__engine.protocol.returncode.done():
            self.__engine = chess.engine.SimpleEngine.popen_uci([_Lc0Engine.ENGINE_COMMAND])
            self.__engine_weight = None
            log.info(f"Engine '{_Lc0Engine.ENGINE_COMMAND}' initialized")

        if self.__engine_weight != weight:
            weight_path = get_weight_file(weight, try_download=True)
            if weight_path is None:
                raise FileNotFoundError(f"Engine weights file not found: {weight_path}")

            self.__engine.configure({"WeightsFile": weight_path})
            self.__engine_weight = weight

            log.info(f"Engine weight set to: {weight}")

        return self.__engine

    def _get_move(self, event: _EngineGetMoveRequest) -> None:
        """Get the engine move for the given request.

        Note: Only allowed to be called from the engine worker thread.
        """

        depth = choice(range(event.min_depth, event.max_depth + 1))
        result = None
        while result is None:
            if self._engine_stop.is_set():
                return

            try:
                result = self._get_engine(event.weight).play(
                    board=event.board,
                    limit=chess.engine.Limit(time=settings['engine.player.time_limit'], depth=depth),
                    info=chess.engine.INFO_BASIC)

            except KeyboardInterrupt:
                raise
            except SystemExit:
                raise
            except Exception:
                if not self._engine_stop.is_set():
                    log.exception(f"Error during engine play: (event={event})")

            if result is not None:
                if result.resigned:
                    log.info(f"Engine resigned (result={result})")
                elif result.move is not None and event.board.is_legal(result.move):
                    log.info(f"Engine selected move {result.move.uci()} (result={result})")
                else:
                    log.warning(f"Engine returned invalid move at depth {depth} for event {event}: {result}")
                    result = None

            if result is None and depth < event.max_depth:
                depth += 1
                log.info(f"Retrying engine move selection with increased depth: {depth}")
            elif result is None:
                # Max depth reached without valid move
                log.error(
                    f"Engine move selection failed for event {event} at max depth {depth}")
                result = chess.engine.PlayResult(move=None, ponder=None, info={"depth": depth}, resigned=True)

        events.event_manager.publish(events.EngineMoveEvent(result))

    def _start_analysis(self, event: _EngineStartAnalysisRequest) -> None:
        """Start engine analysis for the given request.

        Note: Only allowed to be called from the engine worker thread.
        """
        if event.stop_on_new_request and not self._analysis_queue.empty():
            # Do not even start analysis if a new request is pending and stop_on_new_request is set
            return

        total_limit = settings['engine.analysis.time_limit']
        depth_limit = settings['engine.analysis.depth_limit']
        limit = chess.engine.Limit(time=total_limit, depth=depth_limit)

        analysis_event = events.EngineAnalysisEvent(event.board, event.weight, event.id)
        analysis_event.white_win_prob, analysis_event.black_win_prob = _probability_from_material(event.board)
        try:
            with self._get_engine(event.weight).analysis(event.board, limit, info=chess.engine.INFO_ALL) as analysis:
                for info in analysis:
                    score = info.get('score')
                    if score is not None:
                        (analysis_event.white_win_prob,
                         analysis_event.black_win_prob) = _probability_from_engine_score(score)

                        analysis_event.score = score.white().score(mate_score=100000)

                    analysis_event.pv = info.get('pv', [])
                    analysis_event.depth = info.get('depth', 0)

                    events.event_manager.publish(analysis_event)

                    if (event.stop_on_new_request and not self._analysis_queue.empty()) or self._engine_stop.is_set():
                        break
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except Exception:
            if not self._engine_stop.is_set():
                log.exception("Engine terminated unexpectedly during analysis")

    def _engine_worker(self) -> None:
        while not self._engine_stop.is_set():

            event = self._analysis_queue.get()
            try:
                if isinstance(event, _EngineStartAnalysisRequest):
                    self._start_analysis(event)
                elif isinstance(event, _EngineGetMoveRequest):
                    self._get_move(event)
                elif event is None:
                    continue  # Continue to check for stop signal
                else:
                    log.error(f"Unknown engine request type: {type(event)}")
            except KeyboardInterrupt:
                break
            except SystemExit:
                break
            except Exception:
                if not self._engine_stop.is_set():
                    log.exception(f"Error in engine worker: (event={event})")

        log.info(f"Engine '{_Lc0Engine.ENGINE_COMMAND}' shut down")


engine = _Lc0Engine()
atexit.register(engine.stop)

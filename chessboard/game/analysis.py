import chess
import chess.engine
import math
import time
from chessboard.logger import log
import chessboard.events as events
from chessboard.settings import settings
from threading import Thread, Event
import queue


settings.register("analysis.enabled", True, "Enable or disable game analysis")
settings.register("analysis.time_limit", 5.0, "Time limit for analysis in seconds")
settings.register("analysis.engine", "stockfish", "Path to the analysis engine executable")


class _Analysis:
    def __init__(self) -> None:
        self.engine = chess.engine.SimpleEngine.popen_uci([settings['analysis.engine']])
        log.info(f"Analysis engine ({settings['analysis.engine']}) initialized")

        # Persistent worker: continues analysis and restarts on new board
        self._worker_thread: Thread | None = None
        self._shutdown_event: Event = Event()
        self._request_event: Event = Event()
        self._current_request_id: int = 0
        self._current_board: chess.Board | None = None

        self._analysis_queue = queue.Queue()

        events.event_manager.subscribe(
            events.GameStateChangedEvent, self._handle_chess_move_event)

    def __del__(self):
        try:
            if self._worker_thread and self._worker_thread.is_alive():
                self._shutdown_event.set()
                self._request_event.set()
                self._worker_thread.join(timeout=1.0)
        except Exception:
            pass
        if self.engine is not None:
            self.engine.quit()

    def _cp_to_probs(self, cp: float, scale: float = 400.0) -> tuple[float, float]:
        # Logistic mapping from centipawns to win probability
        p_white = 1.0 / (1.0 + math.exp(-cp / scale))
        return p_white, 1.0 - p_white

    def _estimate_material_cp(self, board: chess.Board) -> int:
        # Fallback estimate using material balance if engine eval is unavailable
        values = {'p': 100, 'n': 320, 'b': 330, 'r': 500, 'q': 900, 'k': 0}
        total = 0
        for sq, piece in board.piece_map().items():
            v = values[piece.symbol().lower()]
            total += v if piece.color == chess.WHITE else -v
        return total

    def _handle_chess_move_event(self, event: events.GameStateChangedEvent):
        if not settings['analysis.enabled']:
            return
        # Set latest board request and wake worker
        self._current_board = event.board.copy()
        self._current_request_id += 1
        self._request_event.set()

        # Start worker lazily
        if not self._worker_thread or not self._worker_thread.is_alive():
            self._worker_thread = Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()

    def _start_analysis(self, board: chess.Board, request_id: int) -> None:
        try:
            if self.engine is None:
                cp = self._estimate_material_cp(board)
                p_w, p_b = self._cp_to_probs(float(cp))
                events.event_manager.publish(events.GameWinProbabilityEvent(white_win_prob=p_w, black_win_prob=p_b))
                return

            emit_interval = 0.25
            last_emit_t = 0.0
            last_probs = None

            total_limit = float(settings['analysis.time_limit']) or 0.0
            limit = chess.engine.Limit(time=total_limit) if total_limit > 0.0 else chess.engine.Limit()

            with self.engine.analysis(board, limit, info=chess.engine.INFO_SCORE) as analysis:
                for info in analysis:
                    # Cancel if a newer request arrived
                    if request_id != self._current_request_id:
                        try:
                            analysis.stop()
                        except Exception:
                            pass
                        break
                    try:
                        score = info.get('score')
                        log.warning(f"Analysis info: {info}")
                        if score is None:
                            continue
                        s_white = score.white()
                        if s_white.is_mate():
                            cp = 100000 if (s_white.mate() or 0) > 0 else -100000
                        else:
                            cp = s_white.score(mate_score=100000)

                        p_w, p_b = self._cp_to_probs(float(cp))
                        now = time.time()
                        if (now - last_emit_t) >= emit_interval or last_probs is None or abs(p_w - last_probs[0]) >= 0.001:
                            events.event_manager.publish(
                                events.GameWinProbabilityEvent(white_win_prob=p_w, black_win_prob=p_b)
                            )
                            last_emit_t = now
                            last_probs = (p_w, p_b)
                    except Exception as inner_e:
                        log.debug(f"Analysis stream update error: {inner_e}")

            if request_id == self._current_request_id:
                if last_probs is not None:
                    events.event_manager.publish(
                        events.GameWinProbabilityEvent(white_win_prob=last_probs[0], black_win_prob=last_probs[1])
                    )
                else:
                    cp = self._estimate_material_cp(board)
                    p_w, p_b = self._cp_to_probs(float(cp))
                    events.event_manager.publish(events.GameWinProbabilityEvent(white_win_prob=p_w, black_win_prob=p_b))
        except Exception as e:
            log.warning(f"Failed to compute win probability: {e}", exc_info=True)

    def _worker_loop(self) -> None:
        while not self._shutdown_event.is_set():
            self._request_event.wait(timeout=0.1)
            if self._shutdown_event.is_set():
                break
            if not self._request_event.is_set():
                continue
            # Clear event to coalesce multiple quick updates
            self._request_event.clear()
            board = self._current_board.copy() if self._current_board is not None else None
            req_id = self._current_request_id
            if board is None:
                continue
            # Run analysis for this request; cancels itself on newer requests
            self._start_analysis(board, req_id)


_analysis = _Analysis()

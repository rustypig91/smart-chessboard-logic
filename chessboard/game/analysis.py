import chess
import chess.engine
import math
import time
from chessboard.logger import log
import chessboard.events as events
from chessboard.settings import settings
from threading import Thread, Event
import queue
import time


settings.register("analysis.enabled", True, "Enable or disable game analysis")
settings.register("analysis.time_limit", 5.0, "Time limit for analysis in seconds")
settings.register("analysis.depth_limit", 5, "Depth limit for analysis")
settings.register("analysis.engine", "stockfish", "Path to the analysis engine executable")


class _StopAnalysis(Exception):
    pass


class _Analysis:
    def __init__(self) -> None:
        self.engine = None  # chess.engine.SimpleEngine.popen_uci([settings['analysis.engine']])
        log.info(f"Analysis engine ({settings['analysis.engine']}) initialized")

        # Persistent worker: continues analysis and restarts on new board
        self._worker_thread: Thread | None = None

        self._analysis_queue = queue.Queue()

        events.event_manager.subscribe(
            events.GameStateChangedEvent, self._handle_chess_move_event)

    def __del__(self):
        try:
            if self._worker_thread and self._worker_thread.is_alive():
                self._analysis_queue.put(None)  # Signal to stop
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

        if (event.turn == chess.WHITE and event.white_player != 'Human') or \
           (event.turn == chess.BLACK and event.black_player != 'Human'):
            self._analysis_queue.put(_StopAnalysis())
            log.warning("Skipping analysis during engine's turn")
            return  # Skip analysis during engine's turn

        self._analysis_queue.put(event.board.copy())

        # Start worker lazily
        if not self._worker_thread or not self._worker_thread.is_alive():
            self._worker_thread = Thread(target=self._worker_loop, daemon=True, name="AnalysisWorker")
            self._worker_thread.start()

    def _start_analysis(self, board: chess.Board) -> None:
        if self.engine is None:
            cp = self._estimate_material_cp(board)
            p_w, p_b = self._cp_to_probs(float(cp))
            events.event_manager.publish(events.GameWinProbabilityEvent(white_win_prob=p_w, black_win_prob=p_b))
            return

        emit_interval = 0.5
        last_emit_t = 0.0
        last_probs = None

        total_limit = settings['analysis.time_limit']
        depth_limit = settings['analysis.depth_limit']
        limit = chess.engine.Limit(time=total_limit, depth=depth_limit)

        analysis_interrupted = False

        with self.engine.analysis(board, limit, info=chess.engine.INFO_SCORE) as analysis:
            for info in analysis:
                # Cancel if a newer request arrived
                if not self._analysis_queue.empty():
                    analysis_interrupted = True
                    try:
                        analysis.stop()
                    except Exception:
                        log.error("Failed to stop analysis after interruption")
                    break
                try:
                    score = info.get('score')
                    if score is None:
                        time.sleep(0.1)
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
                    log.error(f"Analysis stream update error: {inner_e}")

        if not analysis_interrupted:
            # Final publish to ensure we have the last evaluation
            if last_probs is not None:
                events.event_manager.publish(
                    events.GameWinProbabilityEvent(white_win_prob=last_probs[0], black_win_prob=last_probs[1])
                )
            else:
                cp = self._estimate_material_cp(board)
                p_w, p_b = self._cp_to_probs(float(cp))
                events.event_manager.publish(events.GameWinProbabilityEvent(white_win_prob=p_w, black_win_prob=p_b))
        else:
            log.error("Analysis interrupted due to new request")

    def _worker_loop(self) -> None:
        while True:
            board = self._analysis_queue.get()
            if board is None:
                break
            elif isinstance(board, _StopAnalysis):
                continue  # Skip analysis

            self.engine = chess.engine.SimpleEngine.popen_uci([settings['analysis.engine']])

            try:
                self._start_analysis(board)
            except Exception as e:
                log.error(f"Analysis failed: {e}", exc_info=True)

            self.engine.quit()

        if self.engine is not None:
            self.engine.quit()
            self.engine = None

        log.info("Analysis worker thread exiting")


_analysis = _Analysis()

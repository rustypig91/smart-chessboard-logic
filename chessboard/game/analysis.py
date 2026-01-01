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

        self._analysis_thread: Thread | None = None
        self._stop_event: Event | None = None

        events.event_manager.subscribe(
            events.GameStateChangedEvent, self._handle_chess_move_event)

    def __del__(self):
        try:
            if self._analysis_thread and self._analysis_thread.is_alive():
                if self._stop_event:
                    self._stop_event.set()
                self._analysis_thread.join(timeout=1.0)
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
        try:
            if self._analysis_thread and self._analysis_thread.is_alive():
                if self._stop_event:
                    self._stop_event.set()
                self._analysis_thread.join(timeout=0.5)
        except Exception:
            pass

        self._stop_event = Event()
        self._analysis_thread = Thread(target=self._start_analysis, args=(
            event.board.copy(), self._stop_event), daemon=True)
        self._analysis_thread.start()

    def _start_analysis(self, board: chess.Board, stop_event: Event) -> None:
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
            chunk = 0.4 if total_limit > 0.4 else total_limit
            elapsed = 0.0

            while not stop_event.is_set() and (total_limit == 0.0 or elapsed < total_limit):
                slice_time = chunk if total_limit == 0.0 else max(0.05, min(chunk, total_limit - elapsed))
                info = None
                try:
                    info = self.engine.analyse(
                        board,
                        chess.engine.Limit(time=slice_time),
                        info=chess.engine.INFO_SCORE,
                    )
                except Exception as inner_e:
                    log.debug(f"Analysis slice error: {inner_e}")

                elapsed += slice_time
                if stop_event.is_set():
                    break

                try:
                    score = info.get('score') if info else None
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
                    log.debug(f"Analysis update error: {inner_e}")

            if not stop_event.is_set():
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


_analysis = _Analysis()

import chess
import chess.engine
import math
from chessboard.logger import log
import chessboard.events as events
from chessboard.settings import settings
from threading import Thread
import queue


settings.register("analysis.enabled", True, "Enable or disable game analysis")
settings.register("analysis.time_limit", 5.0, "Time limit for analysis in seconds")
settings.register("analysis.engine", "stockfish", "Path to the analysis engine executable")


class _Analysis:
    def __init__(self) -> None:
        self.engine = chess.engine.SimpleEngine.popen_uci([settings['analysis.engine']])
        log.info(f"Analysis engine ({settings['analysis.engine']}) initialized")

        events.event_manager.subscribe(
            events.GameStateChangedEvent, self._handle_chess_move_event)

    def __del__(self):
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
        Thread(target=self._start_analysis, args=(event.board.copy(),), daemon=True).start()

    def _start_analysis(self, board: chess.Board) -> None:
        """ Handle ChessMoveEvent to compute and publish win probabilities. """
        try:
            # Prefer engine analysis if available
            if self.engine is not None and self.engine is not None:
                info = self.engine.analyse(
                    board,
                    chess.engine.Limit(time=settings['analysis.time_limit']),
                    # info=chess.engine.INFO_SCORE
                )
                score = info.get('score')
                if score is not None:
                    s_white = score.white()
                    if s_white.is_mate():
                        # Large cp to approximate forced mate, sign gives who is winning
                        cp = 100000 if (s_white.mate() or 0) > 0 else -100000
                    else:
                        cp = s_white.score(mate_score=100000)
                else:
                    cp = self._estimate_material_cp(board)
            else:
                cp = self._estimate_material_cp(board)

            p_w, p_b = self._cp_to_probs(float(cp))
            events.event_manager.publish(events.GameWinProbabilityEvent(white_win_prob=p_w, black_win_prob=p_b))
        except Exception as e:
            log.warning(f"Failed to compute win probability: {e}", exc_info=True)


_analysis = _Analysis()

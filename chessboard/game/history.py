import json
import time
import threading
import uuid
import chess
import chess.pgn

import chessboard.persistent_storage as persistent_storage
import chessboard.events as events
from chessboard.logger import log


class GameHistory:
    """Stores completed games for later analysis.

    Records metadata at game start, appends moves as they occur,
    and finalizes on game over. Persists all entries as PGN.
    """

    HISTORY_FILE = "history/games.pgn"

    def __init__(self):
        self._ensure_storage()

        events.event_manager.subscribe(events.GameOverEvent, self._on_game_over)

        log.info("GameHistory initialized")

    def _ensure_storage(self):
        # Ensure directory exists
        persistent_storage.get_directory("history")
        # Ensure file exists for appending PGN entries
        filename = persistent_storage.get_filename(self.HISTORY_FILE)
        try:
            open(filename, "a").close()
        except Exception:
            with open(filename, "w") as f:
                f.write("")

    # PGN storage is append-only; listing/parsing can be added later if needed

    def _on_game_over(self, event: events.GameOverEvent):
        with self._lock:
            if self._current is None:
                return

            # Winner: store as "white" / "black" / None
            winner_str = None
            if isinstance(event.winner, chess.Color):
                winner_str = "white" if event.winner == chess.WHITE else "black"

            final_fen = None
            white_elapsed = None
            black_elapsed = None
            if self._last_state is not None:
                final_fen = self._last_state.board.fen()
                white_elapsed = self._last_state.white_time_elapsed
                black_elapsed = self._last_state.black_time_elapsed

            # Update headers
            if self._pgn_game is not None:
                self._pgn_game.headers["Termination"] = event.reason
                if white_elapsed is not None and black_elapsed is not None:
                    self._pgn_game.headers["WhiteTimeElapsed"] = f"{white_elapsed:.3f}"
                    self._pgn_game.headers["BlackTimeElapsed"] = f"{black_elapsed:.3f}"
                if self._current.get("engine_weight"):
                    self._pgn_game.headers["EngineWeight"] = self._current["engine_weight"]
                if final_fen is not None:
                    self._pgn_game.headers["FinalFEN"] = final_fen

                # Result
                if winner_str == "white":
                    self._pgn_game.headers["Result"] = "1-0"
                elif winner_str == "black":
                    self._pgn_game.headers["Result"] = "0-1"
                else:
                    self._pgn_game.headers["Result"] = "1/2-1/2"

                # Append to PGN file
                filename = persistent_storage.get_filename(self.HISTORY_FILE)
                try:
                    with open(filename, "a", encoding="utf-8") as f:
                        exporter = chess.pgn.FileExporter(f)
                        self._pgn_game.accept(exporter)
                        f.write("\n\n")
                    log.info(f"GameHistory saved PGN record: {self._current['id']}")
                except Exception as e:
                    log.error(f"Failed to write PGN history: {e}")

            # Cleanup current session
            self._current = None
            self._last_state = None
            self._board = None
            self._pgn_game = None
            self._pgn_node = None


# Initialize singleton on import
history = GameHistory()

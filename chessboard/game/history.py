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
        self._lock = threading.Lock()
        self._current: dict | None = None
        self._board: chess.Board | None = None
        self._pgn_game: chess.pgn.Game | None = None
        self._pgn_node: chess.pgn.ChildNode | chess.pgn.Game | None = None
        self._last_state: events.GameStateChangedEvent | None = None
        self._ensure_storage()

        events.event_manager.subscribe(events.NewGameEvent, self._on_new_game)
        events.event_manager.subscribe(events.ChessMoveEvent, self._on_move)
        events.event_manager.subscribe(events.GameStateChangedEvent, self._on_state)
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

    def _on_new_game(self, event: events.NewGameEvent):
        with self._lock:
            # Reset current record
            self._current = {
                "id": uuid.uuid4().hex,
                "start_time": time.time(),
                "engine_weight": event.engine_weight,
                "white_player": event.white_player.value,
                "black_player": event.black_player.value,
                "white_start_time": event.start_time_seconds[0],
                "black_start_time": event.start_time_seconds[1],
                "white_increment": event.increment_seconds[0],
                "black_increment": event.increment_seconds[1],
                "result": None,
                "reason": None,
                "final_fen": None,
                "white_time_elapsed": None,
                "black_time_elapsed": None,
            }
            log.info(f"GameHistory started new record: {self._current['id']}")

            # Initialize PGN structures
            self._board = chess.Board()
            self._pgn_game = chess.pgn.Game()
            self._pgn_node = self._pgn_game

            # Header tags
            self._pgn_game.headers["Event"] = "Smart Chessboard Game"
            self._pgn_game.headers["Date"] = time.strftime("%Y.%m.%d", time.localtime(self._current["start_time"]))

            # Player names: human vs engine
            white_name = "Human" if event.white_player.value == "human" else (event.engine_weight or "Engine")
            black_name = "Human" if event.black_player.value == "human" else (event.engine_weight or "Engine")
            self._pgn_game.headers["White"] = white_name
            self._pgn_game.headers["Black"] = black_name

            # TimeControl header (seconds + increment)
            ws, bs = event.start_time_seconds
            wi, bi = event.increment_seconds
            if ws == bs and wi == bi:
                self._pgn_game.headers["TimeControl"] = f"{int(ws) if ws != float('inf') else 0}+{int(bi)}"
            else:
                # Non-standard per-side controls as custom tags
                self._pgn_game.headers["WhiteTimeControl"] = f"{int(ws) if ws != float('inf') else 0}+{int(wi)}"
                self._pgn_game.headers["BlackTimeControl"] = f"{int(bs) if bs != float('inf') else 0}+{int(bi)}"

    def _on_move(self, event: events.ChessMoveEvent):
        with self._lock:
            if self._current is None:
                return
            if self._board is None or self._pgn_node is None:
                return
            # Apply move to local board and PGN game
            try:
                self._board.push(event.move)
                self._pgn_node = self._pgn_node.add_variation(event.move)
            except Exception as e:
                log.warning(f"Failed to record move in PGN: {e}")

    def _on_state(self, event: events.GameStateChangedEvent):
        # Keep last state to capture final stats (elapsed times, FEN)
        self._last_state = event

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

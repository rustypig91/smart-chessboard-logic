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

    def __init__(self):
        self._white_player = "Human"
        self._black_player = "Human"

        events.event_manager.subscribe(events.GameOverEvent, self._on_game_over)
        events.event_manager.subscribe(events.EngineWeightChangedEvent, self._on_engine_weight_changed)

        log.info("GameHistory initialized")

    # PGN storage is append-only; listing/parsing can be added later if needed

    def _on_engine_weight_changed(self, event: events.EngineWeightChangedEvent):
        """Handle engine weight change events to record player types."""
        self._white_player = event.white_weight if event.white_weight else "Human"
        self._black_player = event.black_weight if event.black_weight else "Human"

    def _on_game_over(self, event: events.GameOverEvent):
        """Handle game over event to save the completed game."""
        game = chess.pgn.Game()
        game.headers["Event"] = "Smart Chessboard Game"
        game.headers["Site"] = "Smart Chessboard"
        game.headers["Date"] = time.strftime("%Y.%m.%d")
        game.headers["White"] = self._white_player
        game.headers["Black"] = self._black_player
        game.headers["Result"] = event.board.result()

        node = game
        for move in event.board.move_stack:
            node = node.add_variation(move)

        time_str = time.strftime("%Y-%m-%d_%H:%M:%S")
        filename = persistent_storage.get_filename(f"history/{time_str}.pgn")
        with open(filename, "w") as f:
            f.write(str(game))

        log.info(f"Game saved to history as {filename}")


# Initialize singleton on import
history = GameHistory()

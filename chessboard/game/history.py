import os
import time
import chess
import chess.pgn

import chessboard.persistent_storage as persistent_storage
import chessboard.events as events
from chessboard.logger import log
from chessboard.settings import settings


settings.register('history.max_games', 100, "Maximum number of games to keep in history before deleting oldest ones")


class GameHistory:
    """Stores completed games for later analysis.

    Records metadata at game start, appends moves as they occur,
    and finalizes on game over. Persists all entries as PGN.
    """

    DIRECTORY = persistent_storage.get_directory("history")

    def __init__(self):
        self._white_player = "Human"
        self._black_player = "Human"

        self.cleanup_temporary_files()
        self.check_max_files()

        events.event_manager.subscribe(events.GameOverEvent, self._on_game_over)
        events.event_manager.subscribe(events.EngineWeightChangedEvent, self._on_engine_weight_changed)

        log.info(f"GameHistory initialized, number of saved games: {self.get_number_of_saved_games()}")

    def cleanup_temporary_files(self) -> None:
        # Remove any leftover .pgn-tmp files in the history directory
        for fname in os.listdir(GameHistory.DIRECTORY):
            if fname.endswith('.pgn-tmp'):
                try:
                    os.remove(os.path.join(GameHistory.DIRECTORY, fname))
                    log.info(f"Removed leftover temporary file: {fname}")
                except Exception as e:
                    log.warning(f"Failed to remove temporary file {fname}: {e}")

    def check_max_files(self) -> None:
        """Ensure the number of saved games does not exceed the maximum limit."""
        max_games = settings['history.max_games']
        files = self.get_game_filenames_sorted()

        while len(files) > max_games:
            oldest_file = files.pop()
            try:
                os.remove(os.path.join(GameHistory.DIRECTORY, oldest_file))
                log.info(f"Removed oldest game file to maintain history limit: {oldest_file}")
            except Exception as e:
                log.warning(f"Failed to remove oldest game file {oldest_file}: {e}")

    @staticmethod
    def get_number_of_saved_games() -> int:
        """Get the number of saved games in the history directory."""
        return len(GameHistory.get_game_filenames_sorted())

    @staticmethod
    def get_game_filenames_sorted() -> list[str]:
        """Get a list of saved game filenames sorted by creation time."""
        try:
            files = []
            for name in os.listdir(GameHistory.DIRECTORY):
                path = os.path.join(GameHistory.DIRECTORY, name)
                if not name.endswith('.pgn'):
                    continue
                if not os.path.isfile(path):
                    continue
                files.append(path)

            files.sort(key=lambda name: os.path.getctime(name), reverse=True)
            return files
        except FileNotFoundError:
            return []

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
        with open(f"{filename}-tmp", "w") as f:
            f.write(str(game))

        os.rename(f"{filename}-tmp", filename)

        log.info(f"Game saved to history as {filename}")


# Initialize singleton on import
history = GameHistory()

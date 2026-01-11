import chess

import pickle
from chessboard.game.engine import engine
from chessboard.logger import log
import chessboard.events as events
import chessboard.persistent_storage as persistent_storage
from chessboard.thread_safe_variable import ThreadSafeVariable
from chessboard.board_wrapper import Board
from threading import Lock


class GameState:
    SAVE_FILE = "saved_game.pkl"

    def __init__(self):
        self._board_lock = Lock()
        self._board = Board()

        self._players: dict[chess.Color, events.PlayerType] = {
            chess.WHITE: events.PlayerType.HUMAN,
            chess.BLACK: events.PlayerType.HUMAN
        }
        self._engine_play_weight: str | None = None
        self._engine_depth_range: tuple[int, int] = (3, 5)

        self._latest_analysis: ThreadSafeVariable[events.EngineAnalysisEvent | None] = ThreadSafeVariable(None)

        self._event_listeners_setup = False
        self._setup_event_listeners()

        log.info("GameState initialized")
        with self._board_lock:
            self._publish_game_state()

    def _setup_event_listeners(self):
        if not self._event_listeners_setup:
            self._event_listeners_setup = True
            events.event_manager.subscribe(events.ChessMoveEvent, self._handle_move)
            events.event_manager.subscribe(events.GameOverEvent, self._handle_game_over)
            events.event_manager.subscribe(events.SquarePieceStateChangeEvent, self._handle_piece_move)
            events.event_manager.subscribe(events.EngineAnalysisEvent, self._handle_engine_analysis)
            events.event_manager.subscribe(events.EngineMoveEvent, self._handle_engine_move)

    def _handle_engine_analysis(self, event: events.EngineAnalysisEvent):
        self._latest_analysis.set(event)

    def get_hint(self) -> chess.Move | None:
        """ Get a hint move from the engine for the current position """
        latest_analysis = self._latest_analysis.get()
        with self._board_lock:
            if latest_analysis is None or latest_analysis.board.fen() != self._board.fen():
                return None  # Analysis is for a different position

        best_move = latest_analysis.pv[0] if len(latest_analysis.pv) > 0 else None

        if best_move is not None:
            events.event_manager.publish(events.HintEvent(move=best_move))

        return best_move

    def get_board(self) -> chess.Board:
        with self._board_lock:
            return self._board.copy()

    @property
    def engine_color(self) -> chess.Color | None:
        if self._players[chess.WHITE] == events.PlayerType.ENGINE:
            return chess.WHITE

        if self._players[chess.BLACK] == events.PlayerType.ENGINE:
            return chess.BLACK

        return None

    def _start_game(self):
        assert self._board_lock.locked(), "Must hold board lock to start game"

        game_started = self._board.is_game_started()
        started = self._board.start_clock()
        if not started:
            return  # Already started

        if not game_started:
            log.info("Game started")
            events.event_manager.publish(events.GameStartedEvent())
        else:
            log.info("Game resumed")
            events.event_manager.publish(events.GameResumedEvent())

        self._publish_game_state()
        self._engine_play_if_needed()

    def start_game(self):
        """ Start or resume the game """
        with self._board_lock:
            self._start_game()

    def _pause_game(self):
        assert self._board_lock.locked(), "Must hold board lock to pause game"

        stopped = self._board.stop_clock()
        if not stopped:
            return  # Already paused
        log.info("Game paused")
        events.event_manager.publish(events.GamePausedEvent())
        self._publish_game_state()

    def pause_game(self):
        """ Pause the game """
        with self._board_lock:
            self._pause_game()

    def _engine_play_if_needed(self):
        assert self._board_lock.locked(), "Must hold board lock to check for engine move"

        engine_color = self.engine_color
        if engine_color is not None and engine_color == self._board.turn:
            assert self._engine_play_weight is not None
            engine.get_move_async(weight=self._engine_play_weight,
                                  board=self._board.copy(),
                                  min_depth=self._engine_depth_range[0],
                                  max_depth=self._engine_depth_range[1])

    def resign_game(self):
        """ Resign the current game """
        with self._board_lock:
            turn = self._board.resign()

            if turn is None:
                log.warning("Failed to resign the game it is already over")
                return

            log.info(f"{'White' if turn == chess.WHITE else 'Black'} resigned the game")
            events.event_manager.publish(events.GameOverEvent(
                winner=self._board.winner, reason="Resignation", board=self._board.copy()))

    def regret_last_move(self):
        """ Regret the last move """
        with self._board_lock:
            if len(self._board.move_stack) == 0:
                log.warning("No moves to regret")
                return

            if self._players[not self._board.turn] != events.PlayerType.HUMAN:
                log.warning("Cannot regret last move during engine turn")
                return

            pops = 1
            if self._players[not self._board.turn] != events.PlayerType.HUMAN:
                pops = 2  # Also regret engine move

            moves = self._board.pop(pops)
            log.info(f"Regretted last {pops} move(s): {[move.uci() for move in moves]}")

            self._publish_game_state()

    def _save(self) -> None:
        assert self._board_lock.locked(), "Must hold board lock to save game state"

        savefile = persistent_storage.get_filename(GameState.SAVE_FILE)
        new_bytes = pickle.dumps(self)

        try:
            with open(savefile, "rb") as f:
                old_bytes = f.read()
            if old_bytes == new_bytes:
                return  # No changes, skip writing and logging
        except FileNotFoundError:
            pass

        with open(savefile, "wb") as f:
            f.write(new_bytes)

        log.debug(
            f"Saved game state to {savefile}:\n"
            f"  FEN: {self._board.fen()}\n"
            f"  White time left: {self._board.clock.white_time_left}\n"
            f"  Black time left: {self._board.clock.black_time_left}\n"
            f"  White player increment: {self._board.clock.get_increment_time(chess.WHITE)}\n"
            f"  Black player increment: {self._board.clock.get_increment_time(chess.BLACK)}\n"
            f"  Clock paused: {self._board.clock.paused}\n"
            f"  Black player: {self._players[chess.BLACK]}\n"
            f"  White player: {self._players[chess.WHITE]}"
        )

    @staticmethod
    def load() -> 'GameState':
        try:
            savefile = persistent_storage.get_filename(GameState.SAVE_FILE)
            with open(savefile, "rb") as f:
                loaded_game: GameState = pickle.load(f)

            with loaded_game._board_lock:
                if loaded_game._board.is_game_over():
                    loaded_game._board.reset()

                log.info(
                    f"Loaded game state from {savefile}:\n"
                    f"  FEN: {loaded_game._board.fen()}\n"
                    f"  White time left: {loaded_game._board.clock.white_time_left}\n"
                    f"  Black time left: {loaded_game._board.clock.black_time_left}\n"
                    f"  White player increment: {loaded_game._board.clock.get_increment_time(chess.WHITE)}\n"
                    f"  Black player increment: {loaded_game._board.clock.get_increment_time(chess.BLACK)}\n"
                    f"  Clock paused: {loaded_game._board.clock.paused}\n"
                    f"  Black player: {loaded_game._players[chess.BLACK]}\n"
                    f"  White player: {loaded_game._players[chess.WHITE]}"
                )

                loaded_game._event_listeners_setup = False
                loaded_game._publish_game_state()

            return loaded_game
        except Exception as e:
            log.warning(f"No saved game found, starting a new game: {e}", exc_info=True)
            game_state = GameState()

            return game_state

    def _clock_timeout_callback(self, color: chess.Color):
        with self._board_lock:
            log.info(f"Time out for {'white' if color == chess.WHITE else 'black'}")
            self._board.is_game_over()
            with self._board_lock:
                events.event_manager.publish(events.GameOverEvent(
                    winner=not color,
                    reason="Time Out",
                    board=self._board.copy()
                ))

    def new_game(self,
                 start_time_seconds: float | tuple[float, float] = float('inf'),
                 increment_seconds: float | tuple[float, float] = 0.0,
                 engine_weight: str | None = None,
                 engine_color: chess.Color | None = None,
                 engine_min_depth: int = 3,
                 engine_max_depth: int = 5
                 ) -> None:
        """ Start a new game

        start_time_seconds: Initial time for each player in seconds (or tuple for white and black)
        increment_seconds: Increment time per move in seconds (or tuple for white and black)
        engine_weight: Name of the engine weight to use for the engine player (None for no engine)
        engine_color: Color for the engine player (None for no engine)
        engine_min_depth: Minimum search depth for the engine
        engine_max_depth: Maximum search depth for the engine
        """
        with self._board_lock:

            self._engine_depth_range = (engine_min_depth, engine_max_depth)

            self._board.stop_clock()  # Ensure clock is paused before setting up new game

            self._board = Board(
                clock_start_time_seconds=start_time_seconds,
                clock_increment_seconds=increment_seconds,
            )
            self._board.set_clock_timeout_callback(self._clock_timeout_callback)

            if engine_color is not None and engine_weight is None:
                log.warning("Engine color specified but no engine weight provided; engine will not play")
                engine_color = None

            self._players[chess.WHITE] = events.PlayerType.HUMAN if engine_color != chess.WHITE else events.PlayerType.ENGINE
            self._players[chess.BLACK] = events.PlayerType.HUMAN if engine_color != chess.BLACK else events.PlayerType.ENGINE

            self._engine_play_weight = engine_weight

            log.info(
                f"New game started\n"
                f"  Time control: {start_time_seconds}+{increment_seconds} seconds\n"
                f"  White player: {self._players[chess.WHITE]}\n"
                f"  Black player: {self._players[chess.BLACK]}"
            )

            events.event_manager.publish(events.NewGameEvent(
                white_player=self._players[chess.WHITE],
                black_player=self._players[chess.BLACK],
                engine_weight=engine_weight,
                start_time_seconds=self._board.clock.start_times,
                increment_seconds=self._board.clock.increment_times,
            ))

            self._publish_game_state()

    def reset(self) -> None:
        """ Reset the game state to initial conditions """
        with self._board_lock:
            self._board.reset()

    def _publish_game_state(self):
        assert self._board_lock.locked(), "Must hold board lock to publish game state"

        events.event_manager.publish(
            events.GameStateChangedEvent(
                board=self._board.copy(),
                clock_paused=self._board.is_game_paused(),
                white_time_left=self._board.clock.white_time_left,
                black_time_left=self._board.clock.black_time_left,
                white_time_elapsed=self._board.clock.white_time_elapsed,
                black_time_elapsed=self._board.clock.black_time_elapsed,
                white_start_time=self._board.clock.white_start_time,
                black_start_time=self._board.clock.black_start_time,
                white_player=self._players[chess.WHITE],
                black_player=self._players[chess.BLACK],
                winner=self._board.winner,
                is_game_started=self._board.is_game_started(),
                is_game_paused=self._board.is_game_paused()
            )
        )
        self._save()

    def publish_game_state(self):
        """ Publish the current game state to subscribers """
        with self._board_lock:
            self._publish_game_state()

    def _handle_piece_move(self, event: events.SquarePieceStateChangeEvent):
        with self._board_lock:
            if self._board.is_game_over():
                return

            is_legal_move = False
            for move in self._board.legal_moves:
                if move.from_square in event.squares or move.to_square in event.squares:
                    is_legal_move = True
                    break

            if not is_legal_move:
                return

            self._start_game()

    def _handle_engine_move(self, event: events.EngineMoveEvent) -> None:
        assert self.engine_color is not None  # Engine must be playing
        assert self._engine_play_weight is not None

        if self.turn != self.engine_color:
            log.warning("It's not the engine's turn to move, ignoring engine move")
            return

        if event.result.draw_offered:
            log.info("Engine offered a draw")
            events.event_manager.publish(events.PlayerNotifyEvent(
                title="Draw Offered",
                message="The engine has offered a draw."
            ))

        if event.result.resigned:
            log.info("Engine resigned the game")
            self.resign_game()
        elif event.result.move is not None and self._board.is_legal(event.result.move):
            events.event_manager.publish(events.ChessMoveEvent(move=event.result.move, side=self.engine_color))
        else:
            log.error(f"Engine did not return a valid move, resigning the game (result={event.result})")
            self.resign_game()

    def _handle_move(self, event: events.ChessMoveEvent):
        with self._board_lock:
            self._board.push(event.move)

            log.info(f"Move {event.move.uci()} registered")

            outcome = self._board.outcome()
            if outcome is not None:
                log.info(f"Game over: {self._board.result()}")
                events.event_manager.publish(events.GameOverEvent(
                    winner=outcome.winner,
                    reason=outcome.termination.name.capitalize().replace('_', ' '),
                    board=self._board.copy()))
                return

            self._start_game()

            self._publish_game_state()
            self._engine_play_if_needed()

    def _handle_game_over(self, event: events.GameOverEvent):
        with self._board_lock:
            self._board.stop_clock()

            winner = 'Draw' if event.winner is None else ('White wins' if event.winner == chess.WHITE else 'Black wins')
            events.event_manager.publish(events.PlayerNotifyEvent(
                title="Game Over",
                message=f"Game over! {winner} by {event.reason.lower()}."
            ))

            self._publish_game_state()

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['_board_lock']

    def __setstate__(self, state):
        self.__dict__.update(state)

        self._board_lock = Lock()

        self._event_listeners_setup = False
        self._setup_event_listeners()

        with self._board_lock:
            self._publish_game_state()


game_state = GameState.load()

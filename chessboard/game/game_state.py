import chess
import chess.engine

import pickle
from chessboard.game.engine import engine
from chessboard.game.chess_clock import ChessClock
from chessboard.logger import log
import chessboard.events as events
import chessboard.persistent_storage as persistent_storage
from chessboard.thread_safe_variable import ThreadSafeVariable


class GameState:
    SAVE_FILE = "saved_game.pkl"

    def __init__(self):
        self.board = chess.Board()
        self.chess_clock = ChessClock()

        self._event_listeners_setup = False
        self._setup_event_listeners()
        log.info("GameState initialized")

        self._resigned = {
            chess.WHITE: False,
            chess.BLACK: False
        }

        self._players: dict[chess.Color, events.PlayerType] = {
            chess.WHITE: events.PlayerType.HUMAN,
            chess.BLACK: events.PlayerType.HUMAN
        }
        self._engine_play_weight: str | None = None
        self._engine_depth_range: tuple[int, int] = (3, 5)

        self._latest_analysis: ThreadSafeVariable[events.EngineAnalysisEvent | None] = ThreadSafeVariable(None)

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
        if latest_analysis is None or latest_analysis.board.fen() != self.board.fen():
            return None  # Analysis is for a different position

        best_move = latest_analysis.pv[0] if len(latest_analysis.pv) > 0 else None

        if best_move is not None:
            events.event_manager.publish(events.HintEvent(move=best_move))

        return best_move

    @property
    def engine_color(self) -> chess.Color | None:
        if self._players[chess.WHITE] == events.PlayerType.ENGINE:
            return chess.WHITE

        if self._players[chess.BLACK] == events.PlayerType.ENGINE:
            return chess.BLACK

        return None

    def pause_game(self):
        """ Pause the game """
        if not self.is_game_started:
            log.warning("Cannot pause a game that hasn't started")
        elif self.is_game_paused:
            log.warning("Game is already paused")
        else:
            self.chess_clock.pause()
            log.info("Game paused")
            events.event_manager.publish(events.GamePausedEvent())
            self.publish_game_state()

    def _engine_play_if_needed(self):
        engine_color = self.engine_color
        if engine_color is not None and engine_color == self.board.turn:
            assert self._engine_play_weight is not None
            engine.get_move_async(self._engine_play_weight, self.board,
                                  min_depth=self._engine_depth_range[0], max_depth=self._engine_depth_range[1])

    def resume_game(self):
        """ Continue a paused game """
        if not self.is_game_started:
            self.start_game()
        elif not self.is_game_paused:
            log.warning("Game is not paused")
        else:
            self.chess_clock.start()
            log.info("Game continued")
            events.event_manager.publish(events.GameResumedEvent())
            self.publish_game_state()
            self._engine_play_if_needed()

    def start_game(self):
        """ Start the game """
        self.chess_clock.start()
        events.event_manager.publish(events.GameStartedEvent())
        log.info("Game started")
        self.publish_game_state()
        self._engine_play_if_needed()

    def resign_game(self):
        """ Resign the current game """
        if self.is_game_over:
            log.warning("Cannot resign a game that is already over")
            return

        self._resigned[self.board.turn] = True

        log.info(f"{'White' if self.board.turn == chess.WHITE else 'Black'} resigned the game")
        events.event_manager.publish(events.GameOverEvent(winner=self.winner, reason="Resignation"))

    def regret_last_move(self):
        """ Regret the last move """
        if len(self.board.move_stack) == 0:
            log.warning("No moves to regret")
            return

        self.board.pop()

        if self._players[self.board.turn] != events.PlayerType.HUMAN and len(self.board.move_stack) > 0:
            self.board.pop()

        self.chess_clock.set_player(self.board.turn)

        self.publish_game_state()

    @property
    def is_game_over(self) -> bool:
        return self.winner is not None

    @property
    def winner(self) -> chess.Color | None:
        outcome = self.board.outcome()
        if outcome is not None:
            return outcome.winner
        if self.chess_clock.white_time_left <= 0:
            return chess.BLACK
        if self.chess_clock.black_time_left <= 0:
            return chess.WHITE
        if self._resigned[chess.WHITE]:
            return chess.BLACK
        if self._resigned[chess.BLACK]:
            return chess.WHITE

        return None

    @property
    def is_game_started(self) -> bool:
        return (not self.chess_clock.paused or len(self.board.move_stack) > 0) and not self.is_game_over

    @property
    def is_game_paused(self) -> bool:
        return self.chess_clock.paused and self.is_game_started

    def save(self) -> None:
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
            f"  FEN: {self.board.fen()}\n"
            f"  White time left: {self.chess_clock.white_time_left}\n"
            f"  Black time left: {self.chess_clock.black_time_left}\n"
            f"  White player increment: {self.chess_clock.get_increment(chess.WHITE)}\n"
            f"  Black player increment: {self.chess_clock.get_increment(chess.BLACK)}\n"
            f"  Clock paused: {self.chess_clock.paused}\n"
            f"  Black player: {self._players[chess.BLACK]}\n"
            f"  White player: {self._players[chess.WHITE]}"
        )

    @staticmethod
    def load() -> 'GameState':
        try:
            savefile = persistent_storage.get_filename(GameState.SAVE_FILE)
            with open(savefile, "rb") as f:
                loaded_game: GameState = pickle.load(f)

            if loaded_game.is_game_over:
                loaded_game.reset()

            log.info(
                f"Loaded game state from {savefile}:\n"
                f"  FEN: {loaded_game.board.fen()}\n"
                f"  White time left: {loaded_game.chess_clock.white_time_left}\n"
                f"  Black time left: {loaded_game.chess_clock.black_time_left}\n"
                f"  White player increment: {loaded_game.chess_clock.get_increment(chess.WHITE)}\n"
                f"  Black player increment: {loaded_game.chess_clock.get_increment(chess.BLACK)}\n"
                f"  Clock paused: {loaded_game.chess_clock.paused}\n"
                f"  Black player: {loaded_game._players[chess.BLACK]}\n"
                f"  White player: {loaded_game._players[chess.WHITE]}"
            )

            loaded_game._event_listeners_setup = False
            loaded_game.publish_game_state()

            return loaded_game
        except Exception as e:
            log.warning(f"No saved game found, starting a new game: {e}", exc_info=True)
            game_state = GameState()
            game_state.save()

            return game_state

    def _clock_timeout_callback(self, color: chess.Color):
        log.info(f"Time out for {'white' if color == chess.WHITE else 'black'}")
        self.board.is_game_over()

        events.event_manager.publish(events.GameOverEvent(
            winner=not color,
            reason="Time Out"
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
        self.reset()

        self._engine_depth_range = (engine_min_depth, engine_max_depth)

        self.chess_clock = ChessClock(
            initial_time_seconds=start_time_seconds,
            increment_seconds=increment_seconds,
            timeout_callback=self._clock_timeout_callback)

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

        # new_game_event =
        events.event_manager.publish(events.NewGameEvent(
            white_player=self._players[chess.WHITE],
            black_player=self._players[chess.BLACK],
            engine_weight=engine_weight,
            start_time_seconds=(
                self.chess_clock.white_start_time,
                self.chess_clock.black_start_time
            ),
            increment_seconds=(
                self.chess_clock.white_increment_time,
                self.chess_clock.black_increment_time
            )
        ))

        self.publish_game_state()

    def reset(self) -> None:
        self._resigned = {
            chess.WHITE: False,
            chess.BLACK: False
        }

        self.board.reset()
        self.chess_clock.reset()

    def publish_game_state(self):
        events.event_manager.publish(
            events.GameStateChangedEvent(
                board=self.board,
                clock_paused=self.chess_clock.paused,
                white_time_left=self.chess_clock.white_time_left,
                black_time_left=self.chess_clock.black_time_left,
                white_time_elapsed=self.chess_clock.white_time_elapsed,
                black_time_elapsed=self.chess_clock.black_time_elapsed,
                white_start_time=self.chess_clock.white_start_time,
                black_start_time=self.chess_clock.black_start_time,
                white_player=self._players[chess.WHITE],
                black_player=self._players[chess.BLACK],
                winner=self.winner,
                is_game_started=self.is_game_started,
                is_game_paused=self.is_game_paused
            )
        )
        self.save()

    def _handle_piece_move(self, event: events.SquarePieceStateChangeEvent):
        if self.is_game_over:
            return

        is_legal_move = False
        for move in self.board.legal_moves:
            if move.from_square in event.squares or move.to_square in event.squares:
                is_legal_move = True
                break

        if not is_legal_move:
            return

        if self.is_game_paused:
            self.resume_game()
        elif not self.is_game_started:
            self.start_game()

    def _handle_engine_move(self, event: events.EngineMoveEvent) -> None:
        assert self.engine_color is not None  # Engine must be playing
        assert self._engine_play_weight is not None

        if self.board.turn != self.engine_color:
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
        elif event.result.move is not None and self.board.is_legal(event.result.move):
            events.event_manager.publish(events.ChessMoveEvent(move=event.result.move, side=self.engine_color))
        else:
            log.error(f"Engine did not return a valid move, resigning the game (result={event.result})")
            self.resign_game()

    def _handle_move(self, event: events.ChessMoveEvent):
        self.board.push(event.move)

        log.info(f"Move {event.move.uci()} registered")

        outcome = self.board.outcome()
        if outcome is not None:
            log.info(f"Game over: {self.board.result()}")
            events.event_manager.publish(events.GameOverEvent(
                winner=outcome.winner,
                reason=outcome.termination.name.capitalize().replace('_', ' '))
            )
            return

        if self.is_game_paused:
            self.resume_game()

        self.chess_clock.set_player(self.board.turn)
        self.publish_game_state()
        self._engine_play_if_needed()

    def _handle_game_over(self, event: events.GameOverEvent):
        self.chess_clock.pause()

        winner = 'Draw' if event.winner is None else ('White wins' if event.winner == chess.WHITE else 'Black wins')
        events.event_manager.publish(events.PlayerNotifyEvent(
            title="Game Over",
            message=f"Game over! {winner} by {event.reason.lower()}."
        ))

        self.publish_game_state()

    def __getstate__(self):
        return (
            self.board,
            self._resigned,
            self.chess_clock.white_time_elapsed,
            self.chess_clock.black_time_elapsed,
            self.chess_clock.white_start_time,
            self.chess_clock.black_start_time,
            self.chess_clock.get_increment(chess.WHITE),
            self.chess_clock.get_increment(chess.BLACK),
            self._players,
            self._engine_play_weight,
            self._engine_depth_range
        )

    def __setstate__(self, state):
        (
            self.board,
            self._resigned,
            white_time_elapsed,
            black_time_elapsed,
            white_start_time,
            black_start_time,
            white_increment,
            black_increment,
            self._players,
            self._engine_play_weight,
            self._engine_depth_range
        ) = state

        self.chess_clock = ChessClock(
            initial_time_seconds=(white_start_time, black_start_time),
            increment_seconds=(white_increment, black_increment),
            timeout_callback=self._clock_timeout_callback
        )
        self.chess_clock.white_time_elapsed = white_time_elapsed
        self.chess_clock.black_time_elapsed = black_time_elapsed
        self.chess_clock.current_player = self.board.turn

        self._latest_analysis = ThreadSafeVariable(None)

        self._event_listeners_setup = False
        self._setup_event_listeners()


game_state = GameState.load()

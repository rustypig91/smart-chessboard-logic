import chess

from chessboard.logger import log
import chessboard.events as events
from chessboard.persistent_storage import PersistentClass


class GameState(PersistentClass):
    """Manages the current state of the chess game, including the board, players, and clocks."""

    def __init__(self):
        super().__init__()

        self._board = chess.Board()
        self._resigned = {
            chess.WHITE: False,
            chess.BLACK: False
        }
        self._is_game_over = False

        self._post_init()

    def _post_init(self):
        events.event_manager.subscribe(events.NewGameEvent, self._handle_new_game_event)
        events.event_manager.subscribe(events.RegretMoveEvent, self._handle_regret_move_event)
        events.event_manager.subscribe(events.ResignEvent, self._handle_resign_event)
        events.event_manager.subscribe(events.ClockTimeoutEvent, self._handle_clock_timeout_event)
        events.event_manager.subscribe(events.NewSubscriberEvent, self._handle_new_subscriber_event)
        events.event_manager.subscribe(events.MoveEvent, self._handle_move_event)

        log.info("GameState initialized")

    def _handle_new_subscriber_event(self, event: events.NewSubscriberEvent) -> None:
        """ Handle new subscriber event to send latest board state """
        if event.event_type == events.BoardStateEvent:
            event.callback(events.BoardStateEvent(board=self._board, is_game_over=self._is_game_over))

    def _handle_new_game_event(self, event: events.NewGameEvent):
        self._board.reset()
        self._resigned = {
            chess.WHITE: False,
            chess.BLACK: False
        }
        self._is_game_over = False
        events.event_manager.publish(events.BoardStateEvent(board=self._board, is_game_over=self._is_game_over))

    def _handle_clock_timeout_event(self, event: events.ClockTimeoutEvent):
        if self._is_game_over:
            log.warning("Clock timeout event received but game is already over")
            return

        loser = event.side
        winner = chess.BLACK if loser == chess.WHITE else chess.WHITE
        log.info(f"Player {'White' if loser == chess.WHITE else 'Black'} ran out of time. "
                 f"Winner: {'White' if winner == chess.WHITE else 'Black'}")

        events.event_manager.publish(events.GameOverEvent(
            winner=winner,
            reason="Time Forfeit",
            board=self._board))

        self._is_game_over = True

    def _handle_resign_event(self, event: events.ResignEvent):
        if self._is_game_over:
            log.warning("Resign event received but game is already over")
            return

        winner = chess.BLACK if self._board.turn == chess.WHITE else chess.WHITE
        log.info(f"Player {'White' if self._board.turn == chess.WHITE else 'Black'} resigned. "
                 f"Winner: {'White' if winner == chess.WHITE else 'Black'}")

        events.event_manager.publish(events.GameOverEvent(
            winner=winner,
            reason="Resignation",
            board=self._board.copy()))

        self._is_game_over = True

    def _handle_move_event(self, event: events.MoveEvent):
        if self._is_game_over:
            log.warning("Move event received but game is already over")
            return

        if not self._board.is_legal(event.move):
            log.error(f"Illegal move attempted: {event.move.uci()}")
            return

        self._board.push(event.move)

        outcome = self._board.outcome()
        if outcome is not None:
            log.info(f"Game over: {self._board.result()}")
            events.event_manager.publish(events.GameOverEvent(
                winner=outcome.winner,
                reason=outcome.termination.name.capitalize().replace('_', ' '),
                board=self._board.copy()))
            self._is_game_over = True

        events.event_manager.publish(events.BoardStateEvent(board=self._board, is_game_over=self._is_game_over))

    def _handle_regret_move_event(self, event: events.RegretMoveEvent):
        if self._board.move_stack:
            if self._is_game_over:
                self._is_game_over = False
                log.info("Game resumed due to move regret after game over")

            move = self._board.pop()
            events.event_manager.publish(events.MoveRegrettedEvent(move=move))
            events.event_manager.publish(events.BoardStateEvent(board=self._board, is_game_over=self._is_game_over))

    def __getstate__(self):
        return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._post_init()


game_state: GameState = GameState.load()

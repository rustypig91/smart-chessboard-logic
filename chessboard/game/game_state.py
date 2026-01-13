import typing
from typing import Optional, Union
if typing.TYPE_CHECKING:
    from typing_extensions import Self

import chess

from chessboard.logger import log
import chessboard.events as events
from chessboard.persistent_storage import PersistentClass


class VariantBoard(chess.Board):
    """A chess.Board subclass that includes clock information for each player."""

    def __init__(self, fen: Optional[str] = chess.STARTING_FEN, chess960: bool = False) -> None:
        self.resigned = {
            chess.WHITE: False,
            chess.BLACK: False
        }
        self.is_clock_timeout = {
            chess.WHITE: False,
            chess.BLACK: False
        }
        self.is_draw_offer = {
            chess.WHITE: False,
            chess.BLACK: False
        }
        super().__init__(fen, chess960=chess960)

    def pop(self) -> chess.Move:
        move = super().pop()

        for color in chess.COLORS:
            self.resigned[color] = False
            self.is_clock_timeout[color] = False
            self.is_draw_offer[color] = False

        return move

    def offer_draw(self, side: chess.Color) -> None:
        self.is_draw_offer[side] = True

    def retract_draw_offer(self, side: chess.Color) -> None:
        self.is_draw_offer[side] = False

    def clock_timedout(self, side: chess.Color) -> None:
        self.is_clock_timeout[side] = True

    def resign(self, side: chess.Color) -> None:
        self.resigned[side] = True

    def is_variant_end(self) -> bool:
        return self.is_variant_draw() or self.is_variant_loss() or self.is_variant_win()

    def is_variant_draw(self) -> bool:
        draw = self.is_draw_offer[chess.WHITE] and self.is_draw_offer[chess.BLACK]
        return draw

    def is_variant_loss(self) -> bool:
        resigned = self.resigned[self.turn]
        timeout = self.is_clock_timeout[self.turn]
        return resigned or timeout

    def is_variant_win(self) -> bool:
        resigned = self.resigned[not self.turn]
        timeout = self.is_clock_timeout[not self.turn]
        return resigned or timeout

    def reset(self) -> None:
        for color in chess.COLORS:
            self.resigned[color] = False
            self.is_clock_timeout[color] = False
            self.is_draw_offer[color] = False

        return super().reset()

    def copy(self, *, stack: Union[bool, int] = True) -> 'Self':
        board = super().copy(stack=stack)

        assert isinstance(board, VariantBoard)

        board.resigned = self.resigned.copy()
        board.is_clock_timeout = self.is_clock_timeout.copy()
        board.is_draw_offer = self.is_draw_offer.copy()

        return board


class GameState(PersistentClass):
    """Manages the current state of the chess game, including the board, players, and clocks."""

    def __init__(self):
        super().__init__()
        self._board = VariantBoard()

        self._post_init()

    def _post_init(self):
        events.event_manager.subscribe(events.NewGameEvent, self._handle_new_game_event)
        events.event_manager.subscribe(events.RegretMoveEvent, self._handle_regret_move_event)
        events.event_manager.subscribe(events.ResignEvent, self._handle_resign_event)
        events.event_manager.subscribe(events.ClockTimeoutEvent, self._handle_clock_timeout_event)
        events.event_manager.subscribe(events.NewSubscriberEvent, self._handle_new_subscriber_event)
        events.event_manager.subscribe(events.MoveEvent, self._handle_move_event)
        events.event_manager.subscribe(events.DrawOfferEvent, self._handle_move_event)

        log.info("GameState initialized")

    def _handle_new_subscriber_event(self, event: events.NewSubscriberEvent) -> None:
        """ Handle new subscriber event to send latest board state """
        if event.event_type == events.BoardStateEvent:
            event.callback(events.BoardStateEvent(board=self._board))

    def _handle_new_game_event(self, event: events.NewGameEvent):
        self._board.reset()
        events.event_manager.publish(events.BoardStateEvent(board=self._board))

    def _handle_clock_timeout_event(self, event: events.ClockTimeoutEvent):
        if self._board.is_game_over():
            log.warning("Clock timeout event received but game is already over")
            return

        loser = event.side
        self._board.clock_timedout(loser)

        log.info(f"Player {chess.COLOR_NAMES[loser]} ran out of time. "
                 f"Winner: {chess.COLOR_NAMES[not loser]}")

        events.event_manager.publish(events.GameOverEvent(
            winner=not loser,
            reason="Time forfeit",
            board=self._board))

    def _handle_resign_event(self, event: events.ResignEvent):
        if self._board.is_game_over():
            log.warning("Resign event received but game is already over")
            return

        winner = not self._board.turn
        self._board.resign(self._board.turn)

        log.info(f"Player {chess.COLOR_NAMES[self._board.turn]} resigned. "
                 f"Winner: {chess.COLOR_NAMES[winner]}")

        events.event_manager.publish(events.GameOverEvent(
            winner=winner,
            reason="Resignation",
            board=self._board.copy()))

    def _handle_move_event(self, event: events.MoveEvent):
        if self._board.is_game_over():
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
                reason=outcome.termination.name.lower().replace('_', ' '),
                board=self._board.copy()))

        events.event_manager.publish(events.BoardStateEvent(board=self._board))

    def _handle_regret_move_event(self, event: events.RegretMoveEvent):
        if self._board.move_stack:
            if self._board.is_game_over():
                log.info("Game resumed due to move regret after game over")

            move = self._board.pop()
            events.event_manager.publish(events.MoveRegrettedEvent(move=move))
            events.event_manager.publish(events.BoardStateEvent(board=self._board))

    def __getstate__(self):
        return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._post_init()


game_state: GameState = GameState.load()

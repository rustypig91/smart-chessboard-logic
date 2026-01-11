from threading import Lock
from typing import Callable, List, Optional, Union
import chess
from chessboard.game.chess_clock import ChessClock
import enum
import dataclasses


class Termination(enum.Enum):
    RESIGNED = enum.auto()
    TIME_FORFEIT = enum.auto()


@dataclasses.dataclass
class Outcome(chess.Outcome):
    variant_termination: Optional[Termination] = None


class Board:
    """ chess.Board wrapper with additional game state management
    """

    def __init__(self,
                 board: chess.Board = chess.Board(),
                 clock_start_time_seconds: float | tuple[float, float] = float('inf'),
                 clock_increment_seconds: float | tuple[float, float] = 0.0):

        self._board = board

        self.clock = ChessClock(
            initial_time_seconds=clock_start_time_seconds,
            increment_seconds=clock_increment_seconds
        )

        self._resigned = {
            chess.WHITE: False,
            chess.BLACK: False
        }

    def set_clock_timeout_callback(self, callback: Callable[[chess.Color], None]):
        self.clock.add_timeout_callback(callback)

    @property
    def clock_start_time_seconds(self) -> tuple[float, float]:
        return self.clock.get_initial_time(chess.WHITE), self.clock.get_initial_time(chess.BLACK)

    @property
    def clock_increment_seconds(self) -> tuple[float, float]:
        return self.clock.get_increment_time(chess.WHITE), self.clock.get_increment_time(chess.BLACK)

    def is_game_paused(self) -> bool:
        return self.clock.paused

    def is_game_started(self) -> bool:
        return self.clock.started

    def is_game_over(self, *, claim_draw: bool = False) -> bool:
        return self.outcome(claim_draw=claim_draw) is not None

    def resign(self) -> Optional[chess.Color]:
        if self.is_game_over():
            return None

        self._resigned[self.turn] = True
        return self.turn

    def outcome(self, *, claim_draw: bool = False) -> Optional[Outcome]:
        # Check for standard chess outcomes
        outcome = self._board.outcome(claim_draw=claim_draw)
        if outcome is not None:
            return Outcome(winner=outcome.winner, termination=outcome.termination, variant_termination=None) if outcome else None

        # Check for resignation
        if self._resigned[chess.WHITE]:
            return Outcome(winner=chess.BLACK, termination=chess.Termination.VARIANT_WIN, variant_termination=Termination.RESIGNED)
        if self._resigned[chess.BLACK]:
            return Outcome(winner=chess.WHITE, termination=chess.Termination.VARIANT_WIN, variant_termination=Termination.RESIGNED)

        # Check for time forfeiture
        if self.clock.white_time_left <= 0:
            return Outcome(winner=chess.BLACK, termination=chess.Termination.VARIANT_WIN, variant_termination=Termination.TIME_FORFEIT)
        if self.clock.black_time_left <= 0:
            return Outcome(winner=chess.WHITE, termination=chess.Termination.VARIANT_WIN, variant_termination=Termination.TIME_FORFEIT)

        return None

    @property
    def winner(self) -> Optional[chess.Color]:
        outcome = self.outcome()
        return outcome.winner if outcome else None

    def push(self, move):
        self._board.push(move)
        self.clock.set_player(self._board.turn)

    def stop_clock(self):
        self.clock.stop()

    def start_clock(self) -> bool:
        return self.clock.start()

    def pop(self, number_of_moves=1) -> List[chess.Move]:
        stopped = self.clock.stop()
        moves = []

        for _ in range(number_of_moves):
            if self._board.move_stack:
                moves.append(self._board.pop())

        self.clock.set_player(self._board.turn, increment=False)

        if stopped:
            self.clock.start()

        return moves

    @property
    def legal_moves(self) -> chess.LegalMoveGenerator:
        return self._board.legal_moves

    def fen(self) -> str:
        return self._board.fen()

    def reset(self):
        self._board.reset()
        self.clock.reset()
        self._resigned = {
            chess.WHITE: False,
            chess.BLACK: False
        }

    @property
    def turn(self):
        return self._board.turn

    @property
    def move_stack(self) -> list[chess.Move]:
        return self._board.move_stack

    def result(self):
        return self._board.result()

    def __str__(self):
        return str(self._board)

    def copy(self, *, stack: Union[bool, int] = True) -> 'Board':
        board_wrapper = Board(board=self._board.copy(stack=stack))
        board_wrapper.clock = self.clock.copy()
        board_wrapper._resigned = self._resigned.copy()

        return board_wrapper

    def __getstate__(self):
        state = self.__dict__.copy()
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

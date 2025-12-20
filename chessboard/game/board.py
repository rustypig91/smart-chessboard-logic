import os
import pickle
from time import time
from typing import Iterable as iterable
import chess
import chess.engine

from chessboard.game.chess_clock import ChessClock
import chessboard.events as events
from chessboard.logger import log
from chessboard.settings import settings, ColorSetting
from chessboard.game.engine import Engine

settings.register("game.colors.invalid_piece_placement",
                  ColorSetting(255, 0, 0),
                  "Color to indicate invalid piece placement")
settings.register("game.colors.move_to",
                  ColorSetting(0, 255, 50),
                  "Color to indicate legal move destinations")
settings.register("game.colors.move_from",
                  ColorSetting(20, 50, 255),
                  "Color to indicate the piece being moved")
settings.register("game.colors.white_max",
                  ColorSetting(150, 150, 150),
                  "Maximum brightness for white squares")
settings.register("game.colors.white_min",
                  ColorSetting(70, 70, 70),
                  "Minimum brightness for white squares")
settings.register("game.colors.black",
                  ColorSetting(0, 0, 0),
                  "Color for black squares")
settings.register("game.colors.capture",
                  ColorSetting(255, 100, 0),
                  "Color to indicate a capture move")
settings.register('game.colors.previous_move',
                  ColorSetting(170, 188, 14),
                  "Color to indicate the squares involved in the previous move")


class _Game:
    SAVE_FILE = os.path.join(os.path.dirname(__file__), ".saved_game.pkl")

    def __init__(self):
        self.board = chess.Board()
        self.chess_clock = ChessClock()

    def save(self) -> None:
        with open(_Game.SAVE_FILE, "wb") as f:
            log.info(f"Saving game state to {_Game.SAVE_FILE}")
            pickle.dump(self, f)

    @staticmethod
    def load() -> '_Game':
        try:
            with open(_Game.SAVE_FILE, "rb") as f:
                loaded_game: _Game = pickle.load(f)

            if loaded_game.board.is_game_over():
                return _Game()  # Return a new game if the loaded game is over

            return loaded_game
        except Exception as e:
            log.warning(f"No saved game found, starting a new game: {e}")
            return _Game()


class Board:
    def __init__(self) -> None:
        self._game = _Game.load()

        events.event_manager.subscribe(events.PieceLiftedEvent, self._handle_piece_lifted)
        events.event_manager.subscribe(events.PiecePlacedEvent, self._handle_piece_placed)
        events.event_manager.subscribe(events.SquarePieceStateChange, self._handle_piece_state_change)
        events.event_manager.subscribe(events.TimeButtonPressedEvent, self._handle_time_button_pressed)
        events.event_manager.subscribe(events.ChessMoveEvent, self._handle_move)
        events.event_manager.subscribe(events.GameOverEvent, self._handle_game_over)

        self._board_square_color_map: dict[chess.Square, tuple[int, int, int]] = {}

        # Current realtime state of pieces on board
        self._board_piece_color_map: list[chess.Color | None] = [None] * 64
        for square in chess.SQUARES:
            # Start of assuming board matches game state
            self._board_piece_color_map[square] = self.board.color_at(square)

        self._reset_color(chess.SQUARES)
        self._engine: Engine | None = None

    @property
    def board(self) -> chess.Board:
        return self._game.board

    @property
    def chess_clock(self) -> ChessClock:
        return self._game.chess_clock

    @property
    def square_colors(self) -> dict[chess.Square, tuple[int, int, int]]:
        return self._board_square_color_map

    @property
    def pieces(self) -> dict[chess.Square, chess.Piece]:
        """ Get the current pieces on the board according to game state """
        return self.board.piece_map()

    def new_game(self, start_time_seconds: int = 0,
                 increment_seconds: int = 0,
                 engine_weight: str | None = None,
                 engine_color: chess.Color = chess.BLACK) -> None:
        """ Start a new game """
        self.board.reset()
        self._game.chess_clock = ChessClock(start_time_seconds, increment_seconds)
        self._reset_color(chess.SQUARES)

        if engine_weight is not None:
            self._engine = Engine(time_limit=1.0, weight=engine_weight, color=engine_color)

        self._game.save()
        self.chess_clock.start()
        log.info(
            f"New game started\n"
            f"  Time control: {start_time_seconds}+{increment_seconds} seconds\n"
            f"  Engine: {engine_weight if engine_weight is not None else 'None'} as {'black' if engine_color == chess.BLACK else 'white'}"
        )

    def start(self):
        """ Start the game """
        self.chess_clock.start()

    def reset(self):
        """ Reset the board to the starting position """
        self.board.reset()
        self.chess_clock.set_player(self.board.turn)
        self._reset_color(chess.SQUARES)
        self._game.save()

    def _handle_piece_lifted(self, event: events.PieceLiftedEvent):
        if self._board_piece_color_map[event.square] is None:
            return

        self._board_piece_color_map[event.square] = None
        self._scan_board()

        if not self.chess_clock.running:
            self.start()

    def _handle_piece_placed(self, event: events.PiecePlacedEvent):
        if self._board_piece_color_map[event.square] == event.color:
            return

        self._board_piece_color_map[event.square] = event.color
        self._scan_board()

    def _handle_piece_state_change(self, event: events.SquarePieceStateChange):
        self._board_piece_color_map = event.colors
        self._scan_board()

    def _handle_time_button_pressed(self, event: events.TimeButtonPressedEvent):
        if event.color != self.board.turn:
            log.warning(f"Time button pressed for {'white' if event.color == chess.WHITE else 'black'} out of turn")
            return

        if self._engine is not None and self._engine.color == event.color:
            log.warning("Time button pressed for engine color, ignoring")
            return

        move = self._scan_board()
        if move is None:
            log.error("No valid move detected on time button press")
            return

        log.info(f"Move {move.uci()} registered")
        self._reset_color(chess.SQUARES)

        self._game.save()
        events.event_manager.publish(events.ChessMoveEvent(move=move))

    def _handle_engine_move(self, result: chess.engine.PlayResult):
        assert self._engine is not None

        if result.resigned:
            log.info("Engine resigned the game")
            events.event_manager.publish(events.GameOverEvent(winner=not self._engine.color, reason="Resignation"))
            return

        if result.draw_offered:
            log.info("Engine offered a draw")
            # For simplicity, we accept all draw offers from the engine
            events.event_manager.publish(events.PlayerNotifyEvent(
                title="Draw Offered",
                message="The engine has offered a draw. The draw is accepted."
            ))

        if result.move is None:
            log.error("Engine did not return a valid move")
            return

        events.event_manager.publish(events.ChessMoveEvent(move=result.move))

    def _handle_game_over(self, event: events.GameOverEvent):
        self.chess_clock.pause()

        self._reset_color(chess.SQUARES)
        winner = 'Draw' if event.winner is None else ('White wins' if event.winner == chess.WHITE else 'Black wins')
        events.event_manager.publish(events.PlayerNotifyEvent(
            title="Game Over",
            message=f"Game over! {winner} by {event.reason.lower()}."
        ))

    def _handle_move(self, event: events.ChessMoveEvent):
        self.board.push(event.move)

        self.chess_clock.set_player(self.board.turn)

        self._scan_board()
        self._game.save()

        outcome = self.board.outcome()
        if outcome is not None:
            log.info(f"Game over: {self.board.result()}")
            events.event_manager.publish(events.GameOverEvent(
                winner=outcome.winner,
                reason=outcome.termination.name.capitalize().replace('_', ' '))
            )
            return

        if self._engine is not None and self._engine.color == self.board.turn:
            self._engine.get_move_async(self.board, self._handle_engine_move)

    def _apply_color_map(self, color_map: dict[chess.Square, tuple[int, int, int] | None]):
        for square, color in color_map.items():
            if color is not None:
                self._board_square_color_map[square] = color

        events.event_manager.publish(events.SetSquareColorEvent(color_map))

    def _get_reset_color_map(self, squares: iterable[chess.Square]):
        white_squares = [sq for sq in squares if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1]
        black_squares = [sq for sq in squares if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]

        # Add gradient to white squares: brighter closer to the player whose turn it is
        white_min = settings['game.colors.white_min']
        white_max = settings['game.colors.white_max']

        color_map = {}

        for rank in range(8):
            squares_in_rank = [sq for sq in white_squares if chess.square_rank(sq) == rank]
            gradient = rank / 7 if self.board.turn == chess.BLACK else (7 - rank) / 7
            color = (
                int(white_min[0] + (white_max[0] - white_min[0]) * gradient),
                int(white_min[1] + (white_max[1] - white_min[1]) * gradient),
                int(white_min[2] + (white_max[2] - white_min[2]) * gradient),
            )

            for sq in squares_in_rank:
                color_map[sq] = color

        for sq in black_squares:
            color_map[sq] = settings['game.colors.black']

        # Light up the last move if available
        if self.board.move_stack:
            last_move = self.board.peek()
            for sq in [last_move.from_square, last_move.to_square]:
                color_map[sq] = settings['game.colors.previous_move']

        # Light up check
        checkers = self.board.checkers()
        king_square = self.board.king(self.board.turn)
        if checkers and king_square is not None:
            color_map[king_square] = settings['game.colors.invalid_piece_placement']
            for sq in checkers:
                color_map[sq] = settings['game.colors.capture']

        return color_map

    def _reset_color(self, squares: iterable[chess.Square]):
        color_map = self._get_reset_color_map(squares)
        self._apply_color_map(color_map)

    def _scan_board(self) -> chess.Move | None:
        # Update self._pieces to match the current board_state

        log.debug("Scanning board for piece changes...")

        legal_move = None
        missing_friendly_pieces = []
        missing_opponent_pieces = []

        extra_friendly_pieces = []
        extra_opponent_pieces = []

        for square in chess.SQUARES:
            color_board = self._board_piece_color_map[square]
            piece_game = self.board.piece_at(square)

            if color_board is None and piece_game is not None:
                # Piece removed
                if piece_game.color == self.board.turn:
                    missing_friendly_pieces.append(square)
                else:
                    missing_opponent_pieces.append(square)
            elif color_board is not None and piece_game is None:
                # Piece added
                if color_board == self.board.turn:
                    extra_friendly_pieces.append(square)
                else:
                    extra_opponent_pieces.append(square)
            elif color_board is not None and piece_game is not None and color_board != piece_game.color:
                # Piece changed
                if color_board == self.board.turn:
                    extra_friendly_pieces.append(square)
                    missing_opponent_pieces.append(square)
                else:
                    extra_opponent_pieces.append(square)
                    missing_friendly_pieces.append(square)

        color_map = self._get_reset_color_map(chess.SQUARES)

        log.debug(f"Missing friendly pieces at {[chess.square_name(sq) for sq in missing_friendly_pieces]}")
        log.debug(f"Missing opponent pieces at {[chess.square_name(sq) for sq in missing_opponent_pieces]}")

        log.debug(f"Extra friendly pieces at {[chess.square_name(sq) for sq in extra_friendly_pieces]}")
        log.debug(f"Extra opponent pieces at {[chess.square_name(sq) for sq in extra_opponent_pieces]}")

        if len(extra_opponent_pieces) > 0 or len(missing_opponent_pieces) > 1:
            color_map.update({sq: settings['game.colors.invalid_piece_placement']
                             for sq in extra_opponent_pieces + missing_opponent_pieces})

        if len(missing_opponent_pieces) == 1 and len(extra_opponent_pieces) == 0:
            # Check if the missing opponent piece can be captured by any friendly piece
            missing_sq = missing_opponent_pieces[0]
            can_be_captured = False
            for move in self.board.legal_moves:
                can_be_captured = move.to_square == missing_sq
                if can_be_captured:
                    break

            if can_be_captured:
                color_map[missing_sq] = settings['game.colors.capture']
            else:
                color_map[missing_sq] = settings['game.colors.invalid_piece_placement']

        if self.board.has_castling_rights(self.board.turn) and len(missing_friendly_pieces) and len(extra_friendly_pieces) == 2:
            # Possible castling finished
            castling_moves = []
            for move in self.board.legal_moves:
                if self.board.is_castling(move):
                    from_sq = move.from_square
                    to_sq = move.to_square
                    if from_sq in missing_friendly_pieces and to_sq in extra_friendly_pieces:
                        castling_moves.append(move)

            if len(castling_moves) == 1:
                move = castling_moves[0]
                legal_move = move
            else:
                color_map.update({sq: settings['game.colors.invalid_piece_placement']
                                 for sq in missing_friendly_pieces + extra_friendly_pieces})

        elif len(missing_friendly_pieces) >= 2 or len(extra_friendly_pieces) >= 2:
            color_map.update({sq: settings['game.colors.invalid_piece_placement']
                             for sq in missing_friendly_pieces + extra_friendly_pieces})

        if len(extra_friendly_pieces) > len(missing_friendly_pieces):
            color_map.update({sq: settings['game.colors.invalid_piece_placement']
                             for sq in extra_friendly_pieces + missing_friendly_pieces})

        if len(missing_friendly_pieces) == 1 and len(extra_friendly_pieces) == 0:
            # Friendly piece lifted, mark legal moves
            legal_moves = [move for move in self.board.legal_moves if move.from_square == missing_friendly_pieces[0]]
            if len(legal_moves) == 0:
                color_map.update({sq: settings['game.colors.invalid_piece_placement']
                                 for sq in missing_friendly_pieces})

            else:
                destination_squares = [move.to_square for move in legal_moves]

                color_map.update({sq: settings['game.colors.move_to'] for sq in destination_squares})
                color_map.update({sq: settings['game.colors.move_from'] for sq in missing_friendly_pieces})

                for move in legal_moves:
                    if self.board.is_capture(move):
                        color_map[move.to_square] = settings['game.colors.capture']

        if len(missing_friendly_pieces) == 1 and len(extra_friendly_pieces) == 1:
            for move in self.board.legal_moves:
                if {move.from_square, move.to_square} == {missing_friendly_pieces[0], extra_friendly_pieces[0]}:
                    legal_move = move
                    break
            if legal_move is None:
                color_map.update({sq: settings['game.colors.invalid_piece_placement']
                                 for sq in missing_friendly_pieces + extra_friendly_pieces})

        if legal_move is not None:
            color_map.update({sq: settings['game.colors.move_from'] for sq in missing_friendly_pieces})

            if self.board.is_capture(legal_move):
                color_map[legal_move.to_square] = settings['game.colors.capture']
            else:
                color_map.update({sq: settings['game.colors.move_to'] for sq in extra_friendly_pieces})

        self._apply_color_map(color_map)

        if legal_move is not None:
            log.info(f"Detected legal move: {legal_move.uci()}")

        return legal_move


board = Board()

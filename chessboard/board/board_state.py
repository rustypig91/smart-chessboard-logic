from time import time
from typing import Iterable as iterable
import chess
import chess.engine


import chessboard.events as events
from chessboard.logger import log
from chessboard.settings import settings, ColorSetting
from chessboard.game.game_state import game_state
import chessboard.board.led_animations as animations
import chessboard.board.led_manager as leds

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


class BoardState:
    def __init__(self) -> None:
        events.event_manager.subscribe(events.SquarePieceStateChangeEvent, self._handle_piece_state_change)
        events.event_manager.subscribe(events.TimeButtonPressedEvent, self._handle_time_button_pressed)
        events.event_manager.subscribe(events.NewGameEvent, self._handle_new_game_event)
        events.event_manager.subscribe(events.ChessMoveEvent, self._handle_move)
        events.event_manager.subscribe(events.GameOverEvent, self._handle_game_over)
        events.event_manager.subscribe(events.GameStateChangedEvent, self._handle_game_state_changed)

        self._was_check = False

        # Current realtime state of pieces on board
        self._board_piece_color_map: list[chess.Color | None] = [None] * 64
        for square in chess.SQUARES:
            # Start of assuming board matches game state
            self._board_piece_color_map[square] = game_state.board.color_at(square)

        self._led_layer = leds.LedLayer()
        leds.led_manager.add_layer(self._led_layer)

        self._change_side_animation = animations.AnimationChangeSide(
            fps=15.0,
            new_side=game_state.board.turn,
            duration=0.5,
        )
        self._change_side_animation.start()

        log.info("BoardState initialized")

    def _handle_piece_state_change(self, event: events.SquarePieceStateChangeEvent):
        self._board_piece_color_map = event.colors
        self._scan_board()

        # Trigger a ripple around newly dropped friendly pieces (None -> turn)
        try:
            dropped_squares = [sq for sq in event.squares if event.colors[sq] is not None]

            for sq in dropped_squares:
                anim = animations.AnimationWaveAround(
                    fps=15.0,
                    duration=1.0,
                    center_square=sq)
                anim.start()
        except Exception as e:
            log.error(f"Error starting wave animation: {e}")

    def _handle_time_button_pressed(self, event: events.TimeButtonPressedEvent):
        if event.color != game_state.board.turn:
            log.warning(
                f"Time button pressed for {'white' if event.color == chess.WHITE else 'black'} out of turn ({event.color}, expected {game_state.board.turn}), ignoring")
            return

        if game_state.engine is not None and game_state.engine.color == event.color:
            log.warning("Time button pressed for engine color, ignoring")
            return

        move = self._scan_board()
        if move is None:
            log.error("No valid move detected on time button press")
            return

        log.info(f"Time button pressed, registering move: {move.uci()}")

        events.event_manager.publish(events.ChessMoveEvent(move=move))

    def _handle_move(self, event: events.ChessMoveEvent):
        self._change_side_animation.set_side(game_state.board.turn)
        # animation = animations.AnimationChangeSide(
        #     fps=15.0,
        #     duration=2.0,
        #     current_side=not game_state.board.turn)

        # animation.start()
        self._scan_board()

    def _handle_game_over(self, event: events.GameOverEvent):
        # Build a stable base to restore after the celebration
        # self._ongoing_animation = animations.AnimationRainbow(start_colors=self._board_square_color_map,
        #                                                       callback=self._scan_board, loop=True)
        # self._ongoing_animation.start()
        pass

    def _handle_game_state_changed(self, event: events.GameStateChangedEvent):
        # Trigger check animation only on transition into check

        # if is_check and not self._was_check:
        #     base_map = self._get_reset_color_map(chess.SQUARES)
        #     board = game_state.board
        #     king_square = board.king(board.turn)
        #     checkers = list(board.checkers())
        #     overlay = {}
        #     if king_square is not None:
        #         overlay[king_square] = settings['game.colors.invalid_piece_placement']
        #     for sq in checkers:
        #         overlay[sq] = settings['game.colors.capture']

        # anim = animations.AnimationKingCheck(
        #     king_square=king_square if king_square is not None else chess.E4,
        #     base_frame=base_map,
        #     start_colors=base_map,
        #     overlay_colors=overlay,
        #     callback=self._scan_board,
        # )
        # anim.start()

        self._scan_board()

    def _handle_new_game_event(self, event: events.NewGameEvent):
        self._scan_board()

    def _reset_led_layer(self):
        # white_squares = [sq for sq in squares if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1]
        # black_squares = [sq for sq in squares if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]

        # # Add gradient to white squares: brighter closer to the player whose turn it is
        # white_min = settings['game.colors.white_min']
        # white_max = settings['game.colors.white_max']

        # color_map = {}

        # for rank in range(8):
        #     squares_in_rank = [sq for sq in white_squares if chess.square_rank(sq) == rank]
        #     gradient = rank / 7 if game_state.board.turn == chess.BLACK else (7 - rank) / 7
        #     color = (
        #         int(white_min[0] + (white_max[0] - white_min[0]) * gradient),
        #         int(white_min[1] + (white_max[1] - white_min[1]) * gradient),
        #         int(white_min[2] + (white_max[2] - white_min[2]) * gradient),
        #     )

        #     for sq in squares_in_rank:
        #         color_map[sq] = color

        # for sq in black_squares:
        #     color_map[sq] = settings['game.colors.black']

        # Light up the last move if available
        self._led_layer.reset()

        if game_state.board.move_stack:
            last_move = game_state.board.peek()
            for sq in [last_move.from_square, last_move.to_square]:
                self._led_layer.colors[sq] = settings['game.colors.previous_move']

        # Light up check
        checkers = game_state.board.checkers()
        king_square = game_state.board.king(game_state.board.turn)
        if checkers and king_square is not None:
            self._led_layer.colors[king_square] = settings['game.colors.invalid_piece_placement']
            for sq in checkers:
                self._led_layer.colors[sq] = settings['game.colors.capture']

    def _scan_board(self) -> chess.Move | None:
        """Scan the board for piece changes and determine if a legal move has been made.

        Also updates the LED colors to reflect the current state.

        returns: The detected legal move, or None if no legal move is detected.
        """
        self._reset_led_layer()

        log.debug("Scanning board for piece changes...")

        legal_move = None
        missing_friendly_pieces = []
        missing_opponent_pieces = []

        extra_friendly_pieces = []
        extra_opponent_pieces = []

        color_map = self._led_layer.colors

        for square in chess.SQUARES:
            color_board = self._board_piece_color_map[square]
            piece_game = game_state.board.piece_at(square)

            if color_board is None and piece_game is not None:
                # Piece removed
                if piece_game.color == game_state.board.turn:
                    missing_friendly_pieces.append(square)
                else:
                    missing_opponent_pieces.append(square)
            elif color_board is not None and piece_game is None:
                # Piece added
                if color_board == game_state.board.turn:
                    extra_friendly_pieces.append(square)
                else:
                    extra_opponent_pieces.append(square)
            elif color_board is not None and piece_game is not None and color_board != piece_game.color:
                # Piece changed
                if color_board == game_state.board.turn:
                    extra_friendly_pieces.append(square)
                    missing_opponent_pieces.append(square)
                else:
                    extra_opponent_pieces.append(square)
                    missing_friendly_pieces.append(square)

        if game_state.is_game_over:
            color_map.update({sq: settings['game.colors.invalid_piece_placement']
                              for sq in missing_friendly_pieces + extra_friendly_pieces + missing_opponent_pieces + extra_opponent_pieces})

            self._led_layer.commit()
            return None

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
            for move in game_state.board.legal_moves:
                can_be_captured = move.to_square == missing_sq
                if can_be_captured:
                    break

            if can_be_captured:
                color_map[missing_sq] = settings['game.colors.capture']
            else:
                color_map[missing_sq] = settings['game.colors.invalid_piece_placement']

        if game_state.board.has_castling_rights(game_state.board.turn) and len(missing_friendly_pieces) and len(extra_friendly_pieces) == 2:
            # Possible castling finished
            castling_moves = []
            for move in game_state.board.legal_moves:
                if game_state.board.is_castling(move):
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
            legal_moves = [move for move in game_state.board.legal_moves if move.from_square == missing_friendly_pieces[0]]
            if len(legal_moves) == 0:
                color_map.update({sq: settings['game.colors.invalid_piece_placement']
                                 for sq in missing_friendly_pieces})

            else:
                destination_squares = [move.to_square for move in legal_moves]

                color_map.update({sq: settings['game.colors.move_to'] for sq in destination_squares})
                color_map.update({sq: settings['game.colors.move_from'] for sq in missing_friendly_pieces})

                for move in legal_moves:
                    if game_state.board.is_capture(move):
                        color_map[move.to_square] = settings['game.colors.capture']

        if len(missing_friendly_pieces) == 1 and len(extra_friendly_pieces) == 1:
            for move in game_state.board.legal_moves:
                if {move.from_square, move.to_square} == {missing_friendly_pieces[0], extra_friendly_pieces[0]}:
                    legal_move = move
                    break
            if legal_move is None:
                color_map.update({sq: settings['game.colors.invalid_piece_placement']
                                 for sq in missing_friendly_pieces + extra_friendly_pieces})

        if legal_move is not None:
            color_map.update({sq: settings['game.colors.move_from'] for sq in missing_friendly_pieces})

            if game_state.board.is_capture(legal_move):
                color_map[legal_move.to_square] = settings['game.colors.capture']
            else:
                color_map.update({sq: settings['game.colors.move_to'] for sq in extra_friendly_pieces})

        self._led_layer.commit()

        if legal_move is not None:
            log.info(f"Detected legal move: {legal_move.uci()}")

        return legal_move


board_state = BoardState()

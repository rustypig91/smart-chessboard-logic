import chess


import chessboard.events as events
from chessboard.logger import log
from chessboard.settings import settings, ColorSetting
from chessboard.game.game_state import game_state
import chessboard.board.led_manager as leds

settings.register('led.color.invalid_piece_placement',
                  ColorSetting((255, 0, 0)),
                  'Color to indicate invalid piece placement')
settings.register('led.color.move_to',
                  ColorSetting((0, 255, 50)),
                  'Color to indicate legal move destinations')
settings.register('led.color.move_from',
                  ColorSetting((20, 50, 255)),
                  'Color to indicate the piece being moved')
settings.register('led.color.capture',
                  ColorSetting((255, 100, 0)),
                  'Color to indicate a capture move')
settings.register('led.color.previous_move',
                  ColorSetting((170, 188, 14)),
                  'Color to indicate the squares involved in the previous move')


class BoardState:
    def __init__(self) -> None:
        events.event_manager.subscribe(events.SquarePieceStateChangeEvent, self._handle_piece_state_change_event)
        events.event_manager.subscribe(events.TimeButtonPressedEvent, self._handle_time_button_pressed_event)
        events.event_manager.subscribe(events.BoardStateEvent, self._handle_board_state_change_event)

        # Current realtime state of pieces on board
        self._board_piece_color_map: list[chess.Color | None] = [None] * 64

        self._led_layer = leds.LedLayer(priority=0)
        leds.led_manager.add_layer(self._led_layer)

        self._latest_board: chess.Board = chess.Board()
        for square, piece in self._latest_board.piece_map().items():
            self._board_piece_color_map[square] = piece.color if piece else None

        log.info("BoardState initialized")

    def _handle_board_state_change_event(self, event: events.BoardStateEvent):
        self._latest_board = event.board.copy()
        self._scan_board(self._latest_board)

    def _handle_piece_state_change_event(self, event: events.SquarePieceStateChangeEvent):
        self._board_piece_color_map = event.colors
        move = self._scan_board(self._latest_board)
        if move is not None and move.to_square in event.squares:
            events.event_manager.publish(events.LegalMoveDetectedEvent(move=move))

    def _handle_time_button_pressed_event(self, event: events.TimeButtonPressedEvent):
        if event.color != self._latest_board.turn:
            log.warning(
                f"Time button pressed for {'white' if event.color == chess.WHITE else 'black'} out of turn ({event.color}, expected {self._latest_board.turn}), ignoring")
            return

        move = self._scan_board(self._latest_board)
        if move is None:
            log.warning("No valid move detected on time button press")
            return

        log.info(f"Time button pressed, registering move: {move.uci()}")

        events.event_manager.publish(events.MoveEvent(move=move, side=event.color))

    def _reset_led_layer(self):
        self._led_layer.reset()

        if self._latest_board.move_stack:
            last_move = self._latest_board.peek()
            for sq in [last_move.from_square, last_move.to_square]:
                self._led_layer.colors[sq] = settings['led.color.previous_move']

    def _scan_board(self, board: chess.Board) -> chess.Move | None:
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
            piece_game = board.piece_at(square)

            if color_board is None and piece_game is not None:
                # Piece removed
                if piece_game.color == board.turn:
                    missing_friendly_pieces.append(square)
                else:
                    missing_opponent_pieces.append(square)
            elif color_board is not None and piece_game is None:
                # Piece added
                if color_board == board.turn:
                    extra_friendly_pieces.append(square)
                else:
                    extra_opponent_pieces.append(square)
            elif color_board is not None and piece_game is not None and color_board != piece_game.color:
                # Piece changed
                if color_board == board.turn:
                    extra_friendly_pieces.append(square)
                    missing_opponent_pieces.append(square)
                else:
                    extra_opponent_pieces.append(square)
                    missing_friendly_pieces.append(square)

        if self._latest_board.is_game_over():
            color_map.update({sq: settings['led.color.invalid_piece_placement']
                              for sq in missing_friendly_pieces + extra_friendly_pieces + missing_opponent_pieces + extra_opponent_pieces})

            self._led_layer.commit()
            return None

        log.debug(f"Missing friendly pieces at {[chess.square_name(sq) for sq in missing_friendly_pieces]}")
        log.debug(f"Missing opponent pieces at {[chess.square_name(sq) for sq in missing_opponent_pieces]}")

        log.debug(f"Extra friendly pieces at {[chess.square_name(sq) for sq in extra_friendly_pieces]}")
        log.debug(f"Extra opponent pieces at {[chess.square_name(sq) for sq in extra_opponent_pieces]}")

        if len(extra_opponent_pieces) > 0 or len(missing_opponent_pieces) > 1:
            color_map.update({sq: settings['led.color.invalid_piece_placement']
                             for sq in extra_opponent_pieces + missing_opponent_pieces})

        if len(missing_opponent_pieces) == 1 and len(extra_opponent_pieces) == 0:
            # Check if the missing opponent piece can be captured by any friendly piece
            missing_sq = missing_opponent_pieces[0]
            can_be_captured = False
            for move in board.legal_moves:
                can_be_captured = move.to_square == missing_sq
                if can_be_captured:
                    break

            if can_be_captured:
                color_map[missing_sq] = settings['led.color.capture']
            else:
                color_map[missing_sq] = settings['led.color.invalid_piece_placement']

        if board.has_castling_rights(board.turn) and len(missing_friendly_pieces) and len(extra_friendly_pieces) == 2:
            # Possible castling finished
            castling_moves = []
            for move in board.legal_moves:
                if board.is_castling(move):
                    from_sq = move.from_square
                    to_sq = move.to_square
                    if from_sq in missing_friendly_pieces and to_sq in extra_friendly_pieces:
                        castling_moves.append(move)

            if len(castling_moves) == 1:
                move = castling_moves[0]
                legal_move = move
            else:
                color_map.update({sq: settings['led.color.invalid_piece_placement']
                                 for sq in missing_friendly_pieces + extra_friendly_pieces})

        elif len(missing_friendly_pieces) >= 2 or len(extra_friendly_pieces) >= 2:
            color_map.update({sq: settings['led.color.invalid_piece_placement']
                             for sq in missing_friendly_pieces + extra_friendly_pieces})

        if len(extra_friendly_pieces) > len(missing_friendly_pieces):
            color_map.update({sq: settings['led.color.invalid_piece_placement']
                             for sq in extra_friendly_pieces + missing_friendly_pieces})

        if len(missing_friendly_pieces) == 1 and len(extra_friendly_pieces) == 0:
            # Friendly piece lifted, mark legal moves
            legal_moves = [move for move in board.legal_moves if move.from_square == missing_friendly_pieces[0]]
            if len(legal_moves) == 0:
                color_map.update({sq: settings['led.color.invalid_piece_placement']
                                 for sq in missing_friendly_pieces})

            else:
                destination_squares = [move.to_square for move in legal_moves]

                color_map.update({sq: settings['led.color.move_to'] for sq in destination_squares})
                color_map.update({sq: settings['led.color.move_from'] for sq in missing_friendly_pieces})

                for move in legal_moves:
                    if board.is_capture(move):
                        color_map[move.to_square] = settings['led.color.capture']

        if len(missing_friendly_pieces) == 1 and len(extra_friendly_pieces) == 1:
            for move in board.legal_moves:
                if {move.from_square, move.to_square} == {missing_friendly_pieces[0], extra_friendly_pieces[0]}:
                    legal_move = move
                    break
            if legal_move is None:
                color_map.update({sq: settings['led.color.invalid_piece_placement']
                                 for sq in missing_friendly_pieces + extra_friendly_pieces})

        if legal_move is not None:
            color_map.update({sq: settings['led.color.move_from'] for sq in missing_friendly_pieces})

            if board.is_capture(legal_move):
                color_map[legal_move.to_square] = settings['led.color.capture']
            else:
                color_map.update({sq: settings['led.color.move_to'] for sq in extra_friendly_pieces})

        self._led_layer.commit()

        if legal_move is not None:
            log.info(f"Detected legal move: {legal_move.uci()}")

        return legal_move


board_state = BoardState()

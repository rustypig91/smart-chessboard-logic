import chess
from flask import Blueprint, jsonify, request, render_template, Response
from chessboard.board.board_state import board_state
from chessboard.game.game_state import game_state
from chessboard.board.led_manager import led_manager, LedLayer

api = Blueprint('api', __name__, template_folder='templates')

_color_preview_layer = LedLayer(priority=100)


@api.route('/square/colors', methods=['GET'])
def get_led_status() -> Response:
    """API endpoint to get the current LED status of the board"""
    return jsonify({'success': True, 'colors': led_manager.colors})


@api.route('/square/color_preview', methods=['POST'])
def preview_square_color() -> Response | tuple[Response, int]:
    """API endpoint to preview a color on a specific square"""
    data = request.get_json()
    color = data.get('color')  # Expecting [R, G, B]

    # Color must be provided in POST; use DELETE to clear preview
    if color is None:
        return jsonify({'success': False, 'error': 'Missing color, use DELETE to clear preview'}), 400

    if (not isinstance(color, list) or len(color) != 3 or
            not all(isinstance(c, int) and 0 <= c <= 255 for c in color)):
        return jsonify({'success': False, 'error': 'Invalid color value'}), 400

    _color_preview_layer.reset()
    middle_squares = [chess.E4, chess.E5, chess.D4, chess.D5]
    for square in middle_squares:
        _color_preview_layer.colors[square] = tuple(color)

    if not led_manager.has_layer(_color_preview_layer):
        led_manager.add_layer(_color_preview_layer)
    _color_preview_layer.commit()

    return jsonify({'success': True})


@api.route('/square/color_preview', methods=['DELETE'])
def clear_square_color_preview() -> Response:
    """API endpoint to clear the color preview layer"""
    led_manager.remove_layer(_color_preview_layer)
    # Ensure clients get an immediate update
    led_manager.apply_layers()
    return jsonify({'success': True})


@api.route('/square/pieces', methods=['GET'])
def get_board_state() -> Response:
    """API endpoint to get the current board state"""

    pieces = {}
    board = game_state.get_board()

    for square, piece in board.piece_map().items():
        pieces[square] = piece.unicode_symbol()

    return jsonify({'success': True, 'board_state': pieces})


@api.route('/game/reset', methods=['POST'])
def reset_game() -> Response:
    """API endpoint to reset the game"""
    game_state.reset()
    return jsonify({'success': True})


@api.route('/game/start', methods=['POST'])
def start_game() -> Response:
    """API endpoint to start a new game"""
    data = request.get_json()
    start_time = data.get('start_time', None)
    increment = data.get('increment', None)

    game_state.new_game(start_time_seconds=start_time, increment_seconds=increment)

    return jsonify({'success': True})

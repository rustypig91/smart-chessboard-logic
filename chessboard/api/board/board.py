import chess
from chessboard.events import event_manager, PieceLiftedEvent, PiecePlacedEvent
from flask import Blueprint, jsonify, request, render_template
from chessboard.game.board import board


api = Blueprint('api', __name__, template_folder='templates')


@api.route('/square/colors', methods=['GET'])
def get_led_status():
    """API endpoint to get the current LED status of the board"""

    colors = {}
    for square in chess.SQUARES:
        colors[square] = board.square_colors.get(square, None)

    return jsonify({'success': True, 'colors': colors})


@api.route('/square/pieces', methods=['GET'])
def get_board_state():
    """API endpoint to get the current board state"""

    pieces = {}
    for square, piece in board.pieces.items():
        pieces[square] = piece.unicode_symbol()

    return jsonify({'success': True, 'board_state': pieces})


@api.route('/game/reset', methods=['POST'])
def reset_game():
    """API endpoint to reset the game"""
    board.reset()
    return jsonify({'success': True})


@api.route('/game/start', methods=['POST'])
def start_game():
    """API endpoint to start a new game"""
    data = request.get_json()
    start_time = data.get('start_time', None)
    increment = data.get('increment', None)

    board.new_game(start_time_seconds=start_time, increment_seconds=increment)

    return jsonify({'success': True})

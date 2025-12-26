import chess
from flask import Blueprint, jsonify, request, render_template
from chessboard.board.board_state import board_state
from chessboard.game.game_state import game_state
from chessboard.board.led_manager import led_manager

api = Blueprint('api', __name__, template_folder='templates')


@api.route('/square/colors', methods=['GET'])
def get_led_status():
    """API endpoint to get the current LED status of the board"""
    return jsonify({'success': True, 'colors': led_manager.colors})


@api.route('/square/pieces', methods=['GET'])
def get_board_state():
    """API endpoint to get the current board state"""

    pieces = {}
    for square, piece in game_state.board.piece_map().items():
        pieces[square] = piece.unicode_symbol()

    return jsonify({'success': True, 'board_state': pieces})


@api.route('/game/reset', methods=['POST'])
def reset_game():
    """API endpoint to reset the game"""
    game_state.reset()
    return jsonify({'success': True})


@api.route('/game/start', methods=['POST'])
def start_game():
    """API endpoint to start a new game"""
    data = request.get_json()
    start_time = data.get('start_time', None)
    increment = data.get('increment', None)

    game_state.new_game(start_time_seconds=start_time, increment_seconds=increment)

    return jsonify({'success': True})

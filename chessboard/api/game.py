import chess
from flask import Blueprint, jsonify, request
from chessboard.game.engine import Engine
from chessboard.game.board import board


api = Blueprint('api', __name__, template_folder='templates')


@api.route('/bots', methods=['GET'])
def get_available_bots():
    """API endpoint to get a list of available computer opponents"""

    available_bots = Engine.get_available_weights()

    return jsonify({'success': True, 'bots': available_bots})


@api.route('/new', methods=['POST'])
def start_new_game():
    """API endpoint to start a new game against a computer opponent"""
    data = request.get_json()
    opponent = data.get('opponent', 'Human')
    start_time_seconds = data.get('start_time_seconds', 0.0)  # Default to 5 seconds per move
    increment_seconds = data.get('increment_seconds', 0.0)

    engine_weight = None
    if opponent != 'Human':
        engine_weight = opponent

    if engine_weight is not None and engine_weight not in Engine.get_available_weights():
        return jsonify({'success': False, 'error': 'Selected opponent not available'}), 400

    if type(start_time_seconds) not in (float, int) or start_time_seconds < 0:
        return jsonify({'success': False, 'error': f'Invalid start time specified'}), 400

    if type(increment_seconds) not in (float, int) or increment_seconds < 0:
        return jsonify({'success': False, 'error': 'Invalid increment specified'}), 400

    try:
        board.new_game(
            start_time_seconds=data.get('start_time_seconds', 0.0),
            increment_seconds=data.get('increment_seconds', 0.0),
            engine_weight=engine_weight,
            engine_color=chess.BLACK)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    # Here you would typically set up the game state with the engine
    # For this example, we'll just return success
    return jsonify({'success': True, 'message': f'Game started against {opponent} with {start_time_seconds}s per move'})

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


@api.route('/clock', methods=['GET'])
def get_clocks():
    """API endpoint to set the chess clock times"""
    return jsonify({
        'success': True,
        'white_time_left': board.chess_clock.white_time_left,
        'black_time_left': board.chess_clock.black_time_left,
        'white_time_elapsed': board.chess_clock.white_time_elapsed,
        'black_time_elapsed': board.chess_clock.black_time_elapsed,
        'running': board.chess_clock.running,
        'current_player': 'white' if board.chess_clock.current_player == chess.WHITE else 'black'
    })


@api.route('/state', methods=['GET'])
def get_game_state():
    """API endpoint to get the current game state"""
    return jsonify({
        'success': True,
        'fen': board.board.fen(),
        'turn': 'white' if board.board.turn == chess.WHITE else 'black',
        'is_check': board.board.is_check(),
        'is_checkmate': board.board.is_checkmate(),
        'is_stalemate': board.board.is_stalemate(),
        'is_insufficient_material': board.board.is_insufficient_material(),
        'is_game_over': board.board.is_game_over(),
        'last_move': board.board.move_stack[-1].uci() if board.board.move_stack else None,
        'clocks': {
            'white_time_left': board.chess_clock.white_time_left,
            'black_time_left': board.chess_clock.black_time_left,
        }
    })

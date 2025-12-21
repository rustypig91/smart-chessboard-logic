import chess
from flask import Blueprint, jsonify, request
from chessboard.game.engine import Engine
from chessboard.game.game_state import game_state


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

    game_state.new_game(
        start_time_seconds=data.get('start_time_seconds', 0.0),
        increment_seconds=data.get('increment_seconds', 0.0),
        engine_weight=engine_weight,
        engine_color=chess.BLACK)

    # Here you would typically set up the game state with the engine
    # For this example, we'll just return success
    return jsonify({'success': True, 'message': f'Game started against {opponent} with {start_time_seconds}s per move'})


@api.route('/pause', methods=['POST'])
def pause_game():
    """API endpoint to pause the current game"""
    game_state.pause_game()
    return jsonify({'success': True})


@api.route('/resume', methods=['POST'])
def resume_game():
    """API endpoint to resume the current game"""
    game_state.resume_game()
    return jsonify({'success': True})


@api.route('/clock', methods=['GET'])
def get_clocks():
    """API endpoint to set the chess clock times"""
    return jsonify({
        'success': True,
        'white_time_left': game_state.chess_clock.white_time_left,
        'black_time_left': game_state.chess_clock.black_time_left,
        'white_time_elapsed': game_state.chess_clock.white_time_elapsed,
        'black_time_elapsed': game_state.chess_clock.black_time_elapsed,
        'running': game_state.chess_clock.running,
        'current_player': 'white' if game_state.chess_clock.current_player == chess.WHITE else 'black'
    })


@api.route('/state', methods=['GET'])
def get_game_state():
    """API endpoint to get the current game state"""
    return jsonify({
        'success': True,
        'fen': game_state.board.fen(),
        'turn': 'white' if game_state.board.turn == chess.WHITE else 'black',
        'is_check': game_state.board.is_check(),
        'is_checkmate': game_state.board.is_checkmate(),
        'is_stalemate': game_state.board.is_stalemate(),
        'is_insufficient_material': game_state.board.is_insufficient_material(),
        'is_game_over': game_state.board.is_game_over(),
        'last_move': game_state.board.move_stack[-1].uci() if game_state.board.move_stack else None,
        'started': game_state.is_game_started,
        'paused': game_state.is_game_paused,
        'clocks': {
            'white_time_left': game_state.chess_clock.white_time_left if game_state.chess_clock.white_time_left != float('inf') else None,
            'black_time_left': game_state.chess_clock.black_time_left if game_state.chess_clock.black_time_left != float('inf') else None,
            'running': game_state.chess_clock.running,
        },
        'white_player': game_state.players[chess.WHITE],
        'black_player': game_state.players[chess.BLACK],
    })

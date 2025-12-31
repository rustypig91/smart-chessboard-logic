import chess
from flask import Blueprint, jsonify, request
from chessboard.game.engine import Engine
from chessboard.game.game_state import game_state
from chessboard.logger import log

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
    engine_name = data.get('engine_name', None)
    engine_color = data.get('engine_color', None)
    start_time_seconds = data.get('start_time_seconds', float('inf'))
    increment_seconds = data.get('increment_seconds', 0.0)

    if not engine_color:
        engine_name = None
        engine_color = None
    elif engine_color.lower() in ('white', 'black'):
        engine_color = chess.WHITE if engine_color.lower() == 'white' else chess.BLACK
    else:
        log.warning(f"Invalid engine color specified: {engine_color}")
        return jsonify({'success': False, 'error': 'Invalid engine color specified'}), 400

    if engine_name and engine_name not in Engine.get_available_weights():
        log.warning(f"Attempted to start game with unavailable opponent: '{engine_name}'")
        return jsonify({'success': False, 'error': 'Selected opponent not available'}), 400

    if type(start_time_seconds) not in (float, int) or start_time_seconds < 0:
        log.warning(f"Invalid start time specified: {start_time_seconds}")
        return jsonify({'success': False, 'error': f'Invalid start time specified'}), 400

    if type(increment_seconds) not in (float, int) or increment_seconds < 0:
        log.warning(f"Invalid increment specified: {increment_seconds}")
        return jsonify({'success': False, 'error': 'Invalid increment specified'}), 400

    if start_time_seconds == 0.0:
        start_time_seconds = float('inf')  # Represent unlimited time

    game_state.new_game(
        start_time_seconds=start_time_seconds,
        increment_seconds=increment_seconds,
        engine_weight=engine_name,
        engine_color=engine_color)

    # Here you would typically set up the game state with the engine
    # For this example, we'll just return success
    return jsonify({'success': True, 'message': f'Game started'})


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


@api.route('/resign', methods=['POST'])
def resign_game():
    """API endpoint to resign the current game"""
    game_state.resign_game()
    return jsonify({'success': True})


@api.route('/regret_last_move', methods=['POST'])
def regret_last_move():
    """API endpoint to regret the last move"""
    game_state.regret_last_move()
    return jsonify({'success': True})


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
            'paused': game_state.chess_clock.paused
        },
        'white_player': game_state.players[chess.WHITE],
        'black_player': game_state.players[chess.BLACK],
    })

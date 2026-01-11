import chess
from flask import Blueprint, jsonify, request
from chessboard.game.game_state import game_state
from chessboard.logger import log
import chessboard.game.engine as engine
import chessboard.events as events
api = Blueprint('api', __name__, template_folder='templates')


@api.route('/bots', methods=['GET'])
def get_available_bots():
    """API endpoint to get a list of available computer opponents"""

    available_bots = engine.get_available_weights()

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

    if engine_name and engine_name not in engine.get_available_weights():
        log.warning(f"Attempted to start game with unavailable opponent: '{engine_name}'")
        return jsonify({'success': False, 'error': 'Selected opponent not available'}), 400
    elif engine_name and engine.get_weight_file(engine_name, try_download=True) is None:
        log.warning(f"Engine weight file for '{engine_name}' not found")
        return jsonify({'success': False, 'error': 'Selected opponent weight file not found'}), 400

    if type(start_time_seconds) not in (float, int) or start_time_seconds < 0:
        log.warning(f"Invalid start time specified: {start_time_seconds}")
        return jsonify({'success': False, 'error': f'Invalid start time specified'}), 400

    if type(increment_seconds) not in (float, int) or increment_seconds < 0:
        log.warning(f"Invalid increment specified: {increment_seconds}")
        return jsonify({'success': False, 'error': 'Invalid increment specified'}), 400

    if start_time_seconds == 0.0:
        start_time_seconds = float('inf')  # Represent unlimited time

    event = events.NewGameEvent(
        white_engine_weight=engine_name if engine_color == chess.WHITE else None,
        black_engine_weight=engine_name if engine_color == chess.BLACK else None,
        start_time_seconds=start_time_seconds,
        increment_seconds=increment_seconds
    )
    events.event_manager.publish(event)

    # Here you would typically set up the game state with the engine
    # For this example, we'll just return success
    return jsonify({'success': True, 'message': f'Game started'})


@api.route('/pause', methods=['POST'])
def pause_game():
    """API endpoint to pause the current game"""
    events.event_manager.publish(events.ClockStopEvent())
    return jsonify({'success': True})


@api.route('/resume', methods=['POST'])
def resume_game():
    """API endpoint to resume the current game"""
    events.event_manager.publish(events.ClockStartEvent())
    return jsonify({'success': True})


@api.route('/resign', methods=['POST'])
def resign_game():
    """API endpoint to resign the current game"""
    events.event_manager.publish(events.ResignEvent())
    return jsonify({'success': True})


@api.route('/regret_last_move', methods=['POST'])
def regret_last_move():
    """API endpoint to regret the last move"""
    events.event_manager.publish(events.RegretMoveEvent())
    return jsonify({'success': True})


@api.route('/hint', methods=['POST'])
def get_hint():
    """API endpoint to get a hint for the next move from the engine"""
    events.event_manager.publish(events.HintRequestedEvent())
    return jsonify({'success': True})

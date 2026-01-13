import chess
import chess.svg
from flask import Blueprint, jsonify, request
from chessboard.game.game_state import game_state
from chessboard.logger import log
import chessboard.game.engine as engine
import chessboard.events as events
from chessboard.game.history import history
from flask import send_from_directory
import os
from flask import Response
import chessboard.persistent_storage as persistent_storage
import chess.pgn
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


@api.route('/history', methods=['GET'])
def get_game_history():
    """API endpoint to get the game history"""
    data = []
    for file in history.get_game_filenames_sorted():
        with open(file) as f:
            game = chess.pgn.read_game(f)

        if game is None:
            log.warning(f"Failed to read game from history file: {file}")
            continue

        data.append({
            'filename': os.path.basename(file),
            'created_time': os.path.getctime(file),
            'white_player': game.headers.get('White', 'Unknown'),
            'black_player': game.headers.get('Black', 'Unknown'),
            'result': game.headers.get('Result', '*'),
            'date': game.headers.get('Date', 'Unknown'),
            'moves': ' '.join(str(move) for move in game.mainline_moves())
        })

    return jsonify({'success': True, 'games': data, 'total_games': len(data)})


@api.route('/svg_board', methods=['POST'])
def get_svg_board():
    """API endpoint to get the current board state as an SVG image.

    Accepts JSON body with:
    - board_fen: optional FEN string to render
    - lastmove_uci: optional UCI string (e.g. "e2e4") to highlight last move
    """
    data = request.get_json()
    board_fen = data.get('board_fen', None)
    lastmove_uci = data.get('lastmove_uci')
    size = data.get('size', None)

    if board_fen:
        try:
            board = chess.Board(board_fen)
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid FEN string provided'}), 400
    else:
        board = chess.Board()

    lastmove = None
    if lastmove_uci:
        try:
            lastmove = chess.Move.from_uci(lastmove_uci)
        except ValueError:
            lastmove = None

    svg_data = chess.svg.board(board=board, size=size, lastmove=lastmove)

    return Response(svg_data, mimetype='image/svg+xml')


@api.route('/history/latest', methods=['GET'])
def get_latest_game_history():
    history_files = history.get_game_filenames_sorted()
    history_dir = persistent_storage.get_directory("history")
    if not history_files:
        return 'No games in history', 404

    filename = os.path.basename(history_files[0])
    return send_from_directory(history_dir, filename, as_attachment=False)


@api.route('/history/<path:filename>', methods=['GET'])
def serve_history_file(filename):
    """Serve a file from the history directory"""
    history_dir = persistent_storage.get_directory("history")
    return send_from_directory(history_dir, filename, as_attachment=True)


@api.route('/history/<path:filename>/positions', methods=['GET'])
def get_game_positions(filename):
    """Return move list and FEN sequence for a saved PGN."""
    history_dir = persistent_storage.get_directory("history")
    safe_dir = os.path.realpath(history_dir)
    requested = os.path.realpath(os.path.join(history_dir, filename))
    if not requested.startswith(safe_dir):
        return jsonify({'success': False, 'error': 'Invalid path'}), 400
    if not os.path.isfile(requested):
        return jsonify({'success': False, 'error': 'File not found'}), 404

    with open(requested, 'r') as f:
        game = chess.pgn.read_game(f)

    if game is None:
        return jsonify({'success': False, 'error': 'Invalid PGN'}), 400

    board = chess.Board()
    fens = [board.fen()]
    moves = []
    for mv in game.mainline_moves():
        moves.append(mv.uci())
        board.push(mv)
        fens.append(board.fen())

    return jsonify({'success': True, 'filename': os.path.basename(filename), 'moves': moves, 'fens': fens})


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

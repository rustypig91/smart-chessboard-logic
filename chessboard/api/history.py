import chess
from flask import Blueprint, jsonify
from chessboard.logger import log
from chessboard.game.history import history
from flask import send_from_directory
import os
import chessboard.persistent_storage as persistent_storage
import chess.pgn
api = Blueprint('api', __name__, template_folder='templates')


@api.route('/', methods=['GET'])
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


@api.route('/latest', methods=['GET'])
def get_latest_game_history():
    history_files = history.get_game_filenames_sorted()
    history_dir = persistent_storage.get_directory("history")
    if not history_files:
        return 'No games in history', 404

    filename = os.path.basename(history_files[0])
    return send_from_directory(history_dir, filename, as_attachment=False)


@api.route('/<path:filename>', methods=['GET'])
def serve_history_file(filename):
    """Serve a file from the history directory"""
    history_dir = persistent_storage.get_directory("history")
    return send_from_directory(history_dir, filename, as_attachment=True)


@api.route('/<path:filename>/positions', methods=['GET'])
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

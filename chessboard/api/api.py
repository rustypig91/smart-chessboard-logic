import os
import chess
import chess.svg
from typing import Any
from flask import Flask, render_template, send_from_directory, request, Response, url_for, jsonify
from flask_socketio import SocketIO


import chessboard.events
from chessboard.api.system.wifi import api as api_board_wifi
from chessboard.api.system.system import api as api_board_system
from chessboard.api.board.board import api as api_board
from chessboard.api.settings import api as api_settings
from chessboard.api.game import api as api_game
from chessboard.api.system.xiao import api as api_system_xiao
from chessboard.api.engine import api as api_engine
from chessboard import is_raspberrypi
from chessboard.game.game_state import game_state
from chessboard.api.history import api as api_history

from chessboard.logger import log
import traceback

app = Flask(__name__, template_folder='templates', static_url_path='/static')
app.register_blueprint(api_board_wifi, url_prefix='/api/system/wifi', name='wifi')
app.register_blueprint(api_board_system, url_prefix='/api/system', name='system')
app.register_blueprint(api_board, url_prefix='/api/board', name='board')
app.register_blueprint(api_settings, url_prefix='/api/settings', name='settings')
app.register_blueprint(api_game, url_prefix='/api/game', name='game')
app.register_blueprint(api_system_xiao, url_prefix='/api/system/xiao/', name='xiao')
app.register_blueprint(api_engine, url_prefix='/api/engine', name='engine')
app.register_blueprint(api_history, url_prefix='/api/history', name='history')

# eventlet.monkey_patch()  # noqa

socketio = SocketIO(app, async_mode='threading')


def has_no_empty_params(rule):
    defaults = rule.defaults if rule.defaults is not None else ()
    arguments = rule.arguments if rule.arguments is not None else ()
    return len(defaults) >= len(arguments)


@app.route('/')
def index() -> str:
    # Provide routes so index.html can render links to all pages
    links = []
    for rule in app.url_map.iter_rules():
        # Filter out rules we can't navigate to in a browser
        # and rules that require parameters
        methods = rule.methods or set()
        if "GET" in methods and has_no_empty_params(rule):
            url = url_for(rule.endpoint, **(rule.defaults or {}))
            links.append(url)

    return render_template('index.html', pages=links)


@app.route('/display/240x320')
def display() -> str:
    return render_template('display-240x320.html')


@app.route('/install_weight')
def install_weight() -> str:
    """API endpoint to get the weight installation page"""
    return render_template('install_weight.html')


@app.route('/favicon.ico')
def favicon() -> Response:
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/overview')
def overview() -> str:
    """API endpoint to get board overview status"""
    return render_template('overview.html')


@app.route('/simulator')
def simulator() -> str:
    """API endpoint to get the board simulator page"""
    return render_template('simulator.html')


@app.route('/analyse')
def analyse() -> str:
    """API endpoint to get the board analyser page"""
    return render_template('analyse.html')


@app.route('/analyzer')
def analyzer() -> Response:
    """Client-side analyzer page using Stockfish WASM"""
    resp = Response(render_template('analyzer.html'))
    resp.headers['cross-origin-opener-policy'] = 'same-origin'
    resp.headers['cross-origin-embedder-policy'] = 'require-corp'
    resp.headers['cross-origin-resource-policy'] = 'same-origin'
    resp.headers['content-security-policy'] = "frame-ancestors 'self'"
    return resp


@app.route('/xiao_firmware')
def xiao_firmware() -> str:
    """Firmware updater page"""
    return render_template('xiao_firmware.html')


@app.route('/svg_board', methods=['POST'])
def get_svg_board():
    """API endpoint to get the current board state as an SVG image.

    Accepts JSON body with:
    - board_fen: optional FEN string to render
    - lastmove_uci: optional UCI string (e.g. "e2e4") to highlight last move
    """
    data = request.get_json()
    board_fen = data.get('board_fen')
    lastmove_uci = data.get('lastmove_uci')
    bestmove_uci = data.get('bestmove_uci')
    nextmove_uci = data.get('nextmove_uci')
    size = data.get('size')

    arrows = []

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

    if bestmove_uci:
        try:
            bestmove = chess.Move.from_uci(bestmove_uci)
            arrow = chess.svg.Arrow(bestmove.from_square, bestmove.to_square, color="green")
            arrows.append(arrow)
        except ValueError:
            log.warning(f"Invalid bestmove UCI provided: {bestmove_uci}")
            return jsonify({'success': False, 'error': 'Invalid bestmove UCI string provided'}), 400

    if nextmove_uci:
        try:
            nextmove = chess.Move.from_uci(nextmove_uci)
            arrow = chess.svg.Arrow(nextmove.from_square, nextmove.to_square, color="blue")
            arrows.append(arrow)
        except ValueError:
            log.warning(f"Invalid nextmove UCI provided: {nextmove_uci}")
            return jsonify({'success': False, 'error': 'Invalid nextmove UCI string provided'}), 400

    log.info(
        f"Generating SVG board: FEN={board_fen}, lastmove={lastmove_uci}, bestmove={bestmove_uci} nextmove={nextmove_uci}")
    svg_data = chess.svg.board(board=board, size=size, lastmove=lastmove, arrows=arrows)

    return Response(svg_data, mimetype='image/svg+xml')


@app.route('/static/node_modules/stockfish/src/<path:filename>')
def static_with_coep(filename: str):
    resp = send_from_directory(
        os.path.join(app.root_path, 'static', 'node_modules', 'stockfish', 'src'),
        filename
    )
    resp.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    resp.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
    return resp


@socketio.on('publish_event')
def handle_publish_event(data: dict[str, Any]) -> None:
    """
    Handle events published by clients.
    Expects 'event_type' and 'event_data' in data.
    """
    event_type = data.get('event_type')
    event_data = data.get('event_data', {})
    if not event_type:
        log.error("publish_event missing 'event_type'")
        return

    try:
        event_class = getattr(chessboard.events, event_type)
        log.debug(f"publish_event: {event_type}; {event_data}")

        event_instance = event_class(**event_data)
        chessboard.events.event_manager.publish(event_instance)
    except Exception as e:
        traceback_lines = "\n    ".join(traceback.format_exc().splitlines())
        log.error(f"Error handling publish_event: {e}: \n    {traceback_lines}")
        return


_subscriptions = {}


@socketio.on('subscribe')
def handle_subscribe(data: dict[str, Any]) -> None:
    """
    Handle event subscription requests from clients.
    Expects 'event_type' in data.
    """
    event_type = data.get('event_type')
    if not event_type:
        log.error("subscribe missing 'event_type'")
        return

    try:
        event_class = getattr(chessboard.events, event_type)
        log.debug(f"subscribe to event: {event_type}")

        sid = request.sid  # type: ignore

        def emit_event_callback(event: chessboard.events.Event) -> None:
            socketio.emit(
                f'board_event.{type(event).__name__}',
                event.to_json(),
                room=sid  # type: ignore
            )

        log.info(f"Subscribing SID {sid} to event {event_type}")
        chessboard.events.event_manager.subscribe(event_class, emit_event_callback)
        if sid not in _subscriptions:
            _subscriptions[sid] = []
        _subscriptions[sid].append((emit_event_callback, event_class))
    except Exception as e:
        traceback_lines = "\n    ".join(traceback.format_exc().splitlines())
        log.info(f"Error handling subscribe: {e}: \n    {traceback_lines}")
        return


@socketio.on('unsubscribe')
def handle_unsubscribe(data: dict[str, Any]) -> None:
    """
    Handle event unsubscription requests from clients.
    Expects 'event_type' in data.
    """
    event_type = data.get('event_type')
    if not event_type:
        log.error("unsubscribe missing 'event_type'")
        return

    try:
        event_class = getattr(chessboard.events, event_type)
        log.debug(f"unsubscribe from event: {event_type}")

        sid = request.sid  # type: ignore

        if sid not in _subscriptions:
            return

        to_remove = []
        for callback, subscribed_event_class in _subscriptions[sid]:
            if subscribed_event_class == event_class:
                chessboard.events.event_manager.unsubscribe(event_class, callback)
                to_remove.append((callback, subscribed_event_class))
        for item in to_remove:
            _subscriptions[sid].remove(item)

        if not _subscriptions[sid]:
            del _subscriptions[sid]
    except Exception as e:
        traceback_lines = "\n    ".join(traceback.format_exc().splitlines())
        log.error(f"Error handling unsubscribe: {e}: \n    {traceback_lines}")
        return


@socketio.on('disconnect')
def handle_disconnect() -> None:
    """Handle client disconnection and clean up subscriptions."""
    sid = request.sid  # type: ignore
    if sid in _subscriptions:
        for callback, event_class in _subscriptions[sid]:
            chessboard.events.event_manager.unsubscribe(event_class, callback)
        del _subscriptions[sid]


if __name__ == '__main__':
    socketio.run(app)

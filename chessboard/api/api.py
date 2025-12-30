import os

from flask import Flask, render_template, send_from_directory, request
from flask_socketio import SocketIO


import chessboard.events
from chessboard.api.system.wifi import api as api_board_wifi
from chessboard.api.system.system import api as api_board_system
from chessboard.api.board.board import api as api_board
from chessboard.api.settings import api as api_settings
from chessboard.api.game import api as api_game
from chessboard import is_raspberrypi

from chessboard.logger import log
import traceback

app = Flask(__name__, template_folder="templates", static_url_path='/static')
app.register_blueprint(api_board_wifi, url_prefix='/api/system/wifi', name='wifi')
app.register_blueprint(api_board_system, url_prefix='/api/system', name='system')
app.register_blueprint(api_board, url_prefix='/api/board', name='board')
app.register_blueprint(api_settings, url_prefix='/api/settings', name='settings')
app.register_blueprint(api_game, url_prefix='/api/game', name='game')

# if is_raspberrypi:
#     from chessboard.api.system.raspberry_pi import api as api_board_raspberry_pi
#     app.register_blueprint(api_board_raspberry_pi, url_prefix='/api/system', name='raspberry_pi')

socketio = SocketIO(app, async_mode="threading")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/display/240x320')
def home():
    return render_template('display-240x320.html')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/overview')
def overview():
    """API endpoint to get board overview status"""
    return render_template('overview.html')


@app.route('/simulator')
def simulator():
    """API endpoint to get the board simulator page"""
    return render_template('simulator.html')


@app.route('/firmware')
def firmware_updater():
    """Firmware updater page"""
    return render_template('firmware_updater.html')


@socketio.on('publish_event')
def handle_publish_event(data):
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


@socketio.on('request_last_event')
def handle_request_last_event(data):
    """
    Handle client request for the last event of a specific type.
    Expects 'event_type' in data.
    """
    event_type = data.get('event_type')
    if not event_type:
        log.error("request_last_event missing 'event_type'")
        return

    try:
        event_class = getattr(chessboard.events, event_type)
        last_event = chessboard.events.event_manager.get_last_event(event_class)
        if last_event:
            log.debug(f"request_last_event: {event_type}; {last_event.to_json()}")
            socketio.emit(f'board_event.{event_type}', last_event.to_json(), to=request.sid)  # type: ignore

        else:
            log.debug(f"request_last_event: {event_type}; no last event found")
    except Exception as e:
        traceback_lines = "\n    ".join(traceback.format_exc().splitlines())
        log.error(f"Error handling request_last_event: {e}: \n    {traceback_lines}")
        return


chessboard.events.event_manager.subscribe_all_events(lambda event: emit_event(event))


def emit_event(event: chessboard.events.Event):
    socketio.emit(f'board_event.{type(event).__name__}', event.to_json())


if __name__ == '__main__':
    socketio.run(app)

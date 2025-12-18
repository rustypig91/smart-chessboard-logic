import os

from flask import Flask, render_template, send_from_directory, request
from flask_socketio import SocketIO


import chessboard.events
from chessboard.api.system.wifi import api as api_board_wifi
from chessboard.api.system.system import api as api_board_system
from chessboard.api.board.board import api as api_board
from chessboard.api.settings import api as api_settings

from chessboard.logger import log
import traceback


app = Flask(__name__, template_folder="templates", static_url_path='/static')
app.register_blueprint(api_board_wifi, url_prefix='/api/board/wifi', name='wifi')
app.register_blueprint(api_board_system, url_prefix='/api/board/system', name='system')
app.register_blueprint(api_board, url_prefix='/api/board', name='board')
app.register_blueprint(api_settings, url_prefix='/api/settings', name='settings')

socketio = SocketIO(app, async_mode="threading")


@app.route('/')
def home():
    return render_template('index.html')


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


chessboard.events.event_manager.subscribe_all_events(lambda event: emit_event(event))


def emit_event(event):
    socketio.emit(f'board_event.{type(event).__name__}', event.to_json())


if __name__ == '__main__':
    socketio.run(app)

from chessboard.settings import settings as chessboard_settings
from flask import Blueprint, jsonify, request, render_template
from chessboard.logger import log

api = Blueprint('api', __name__, template_folder='templates')


@api.route('/')
def settings():
    """API endpoint to get the settings page"""
    _settings = {}
    for key, setting in chessboard_settings.all_settings.items():

        _settings[key] = {
            'value': setting.value,
            'default': setting.default,
            'description': setting.description
        }

    log.debug(f"Settings retrieved: {_settings}")
    return jsonify(success=True, settings=_settings)


@api.route('/<key>', methods=['GET'])
def get_setting(key):
    """API endpoint to get a specific setting"""
    try:
        setting = chessboard_settings.get(key)
        log.debug(f"Setting '{key}' retrieved: {setting}")
        return jsonify(success=True, setting=setting.to_json())
    except KeyError:
        log.error(f"Setting '{key}' not found")
        return jsonify(success=False, error="Setting not found"), 404


@api.route('/<key>', methods=['POST'])
def update_setting(key):
    """API endpoint to update a specific setting"""
    data = request.get_json()
    if not data or 'value' not in data:
        return jsonify(success=False, error="Missing 'value' in request"), 400
    try:
        setting = chessboard_settings.get(key)
        old_value = setting.value
        setting.value = data['value']
        log.debug(f"Setting '{key}' changed from {old_value} to {setting.value}")
        return jsonify(success=True, setting=setting.to_json())
    except KeyError:
        log.error(f"Setting '{key}' not found")
        return jsonify(success=False, error="Setting not found"), 404

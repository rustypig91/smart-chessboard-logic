import os
from flask import Blueprint, jsonify, request
import chessboard.game.engine as engine
from werkzeug.utils import secure_filename
from chessboard.logger import log
import tempfile

api = Blueprint('api', __name__, template_folder='templates')


@api.route('/weights', methods=['GET'])
def get_available_weights():
    """API endpoint to get a list of available engine weights"""
    try:
        weights = []
        available_weights = engine.get_available_weights()

        for weight in available_weights:
            filename = engine.get_weight_filename(weight)
            weights.append({
                'name': weight,
                'size': os.path.getsize(filename),
                'last_modified': os.path.getmtime(filename),
                'filename': engine.get_weight_filename(weight)
            })

        return jsonify({'success': True, 'weights': weights})
    except Exception as e:
        log.error(f"Error retrieving weights: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api.route('/weights/<weight_name>', methods=['DELETE'])
def delete_weight(weight_name):
    """API endpoint to delete an engine weight"""
    try:
        weight_name = secure_filename(weight_name)
        engine.delete_weight(weight_name)
        log.info(f"Deleted engine weight: {weight_name}")
        return jsonify({'success': True, 'deleted': weight_name})
    except FileNotFoundError:
        log.warning(f"Attempted to delete non-existent weight: {weight_name}")
        return jsonify({'success': False, 'error': 'Weight not found'}), 404
    except Exception as e:
        log.error(f"Error deleting weight '{weight_name}': {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api.route('/weights/url', methods=['POST'])
def install_weight_from_url():
    """API endpoint to install a new engine weight file from a URL"""
    url = None
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'success': False, 'error': "Missing 'url' in request"}), 400

        url = data['url']
        engine.install_weight_from_url(url)

        return jsonify({'success': True, 'installed_from': url})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Internal server error installing weight from URL '{url}': {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@api.route('/weights', methods=['POST'])
def install_weight():
    """API endpoint to install a new engine weight file"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        uploaded = request.files['file']
        if not uploaded or uploaded.filename == '':
            return jsonify({'success': False, 'error': 'Empty filename'}), 400

        name = request.form.get('name') or uploaded.filename
        if not name:
            return jsonify({'success': False, 'error': 'Empty weight name'}), 400

        name = secure_filename(name)

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = os.path.join(tmpdir, name)
            uploaded.save(temp_path)
            engine.install_weight(temp_path)

        return jsonify({'success': True, 'installed': name})
    except FileExistsError:
        return jsonify({'success': False, 'error': 'Weight already exists'}), 409
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        log.error(f"Internal server error installing weight: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

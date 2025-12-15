
from flask import Blueprint, jsonify, request, render_template
import tempfile
from chessboard.raspberry_pi_system.xiao_interface import xiao_interface

api = Blueprint('api', __name__, template_folder='templates')


@api.route('/firmware_updater')
def firmware_updater():
    """API endpoint to get the firmware updater page"""
    return render_template('firmware_updater.html')


@api.route('/update_xiao_firmware', methods=['POST'])
def update_xiao_firmware():
    """API endpoint to update the Xiao firmware"""
    # This is a placeholder implementation. Actual implementation would depend on the specific update process.
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part in the request'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400

    with tempfile.NamedTemporaryFile() as firmware:
        file.save(firmware.name)
        xiao_interface.flash_firmware(firmware.name)

    # Placeholder for actual firmware flashing logic
    # Example: os.system(f'flash-xiao {firmware_path}')

    return jsonify({'success': True, 'message': 'Firmware uploaded and flashing initiated.'})

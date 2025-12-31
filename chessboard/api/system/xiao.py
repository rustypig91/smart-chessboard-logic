
import os
from flask import Blueprint, jsonify, request, render_template
import tempfile
from chessboard import is_raspberrypi
from chessboard.logger import log
import shutil

api = Blueprint('api', __name__, template_folder='templates')


@api.route('/update_firmware', methods=['POST'])
def update_firmware():
    """API endpoint to update the Xiao firmware"""
    # This is a placeholder implementation. Actual implementation would depend on the specific update process.
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part in the request'}), 400

    try:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'}), 400

        with tempfile.NamedTemporaryFile() as firmware:
            file.save(firmware.name)

            log.info(
                f"Firmware file '{file.filename}' uploaded successfully to {firmware.name} with size {os.path.getsize(firmware.name)} bytes")

            if is_raspberrypi:
                from chessboard.raspberry_pi_system.xiao_interface import xiao_interface
                xiao_interface.flash_firmware(firmware.name)
            else:
                log.warning("Firmware update attempted on non-Raspberry Pi system")

            log.info("Firmware flashing completed successfully")

        return jsonify({'success': True, 'message': 'Firmware uploaded and flashing initiated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

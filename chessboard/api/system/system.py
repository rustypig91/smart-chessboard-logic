import os
from flask import Blueprint, jsonify

api = Blueprint('api', __name__, template_folder='templates')


@api.route('/shutdown', methods=['POST'])
def shutdown():
    """API endpoint to shut down the system"""
    os.system('shutdown -h now')

    return jsonify({'success': True})

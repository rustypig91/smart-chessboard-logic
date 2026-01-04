import os
from flask import Blueprint, jsonify, request
import psutil
import time
import chessboard.events as events
import threading
api = Blueprint('api', __name__, template_folder='templates')


@api.route('/shutdown', methods=['POST'])
def shutdown():
    """API endpoint to shut down the system"""
    events.event_manager.publish(events.SystemShutdownEvent(), block=True)
    os.system('(sleep 1; shutdown -h now) >/dev/null 2>&1 &')
    return jsonify({'success': True})


@api.route('/reboot', methods=['POST'])
def reboot():
    """API endpoint to reboot the system"""
    # Schedule reboot in background after a short delay so the response is returned first
    events.event_manager.publish(events.SystemShutdownEvent(), block=True)
    os.system('(sleep 1; reboot) >/dev/null 2>&1 &')
    return jsonify({'success': True})


@api.route('/info', methods=['GET'])
def info():
    """API endpoint to get system information"""

    loadavg = os.getloadavg()
    disk_usage = psutil.disk_usage('/')
    memory = psutil.virtual_memory()

    return jsonify({
        'kernel': f"{os.uname().sysname} {os.uname().release}",
        'architecture': os.uname().machine,
        'hostname': os.popen('hostname').read().strip(),
        'system_uptime': time.time() - psutil.boot_time(),
        'load_average': {
            '1min': loadavg[0],
            '5min': loadavg[1],
            '15min': loadavg[2],
        },
        'cpu_percent_percpu': psutil.cpu_percent(percpu=True),
        'cpu_percent': psutil.cpu_percent(),
        'memory': {
            'total': memory.total,
            'used': memory.used,
            'free': memory.available,
            'percent_used_%': memory.percent,
            'percent_free_%': 100 - memory.percent
        },
        'disk_usage': {
            'total': disk_usage.total,
            'used': disk_usage.used,
            'free': disk_usage.free,
            'used_%': disk_usage.percent,
            'free_%': 100 - disk_usage.percent
        },
        'threads': [{'name': t.name, 'id': t.ident} for t in threading.enumerate()],
        'process': {
            'pid': os.getpid(),
            'memory_info': psutil.Process().memory_info()._asdict(),
            'cpu_times': psutil.Process().cpu_times()._asdict(),
            'process_uptime': time.time() - psutil.Process().create_time(),
            'num_threads': psutil.Process().num_threads(),
            'threads': [t._asdict() for t in psutil.Process().threads()],
        },
    })


@api.route('/hostname', methods=['GET', 'POST'])
def hostname():
    """API endpoint to get or set the system hostname"""
    if request.method == 'GET':
        hostname = os.popen('hostname').read().strip()
        return jsonify({'success': True, 'hostname': hostname})

    elif request.method == 'POST':
        data = request.get_json()
        new_hostname = data.get('hostname', '').strip()

        if not new_hostname:
            return jsonify({'success': False, 'error': 'Hostname cannot be empty'}), 400

        os.system(f'hostnamectl set-hostname {new_hostname}')
        return jsonify({'success': True, 'hostname': new_hostname})

    return jsonify({'success': False, 'error': 'Invalid request method'}), 405

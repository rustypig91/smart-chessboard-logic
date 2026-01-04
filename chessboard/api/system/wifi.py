from flask import Blueprint, jsonify, request, Response
import subprocess
from chessboard.logger import log
from typing import Any, Optional

api = Blueprint('api', __name__, template_folder='templates')


@api.route('/info')
def info() -> Response:
    """API endpoint to get WiFi status"""
    wifi_info = get_wifi_info()
    return jsonify(wifi_info)


@api.route('/connect', methods=['POST'])
def connect() -> Response | tuple[Response, int]:
    """API endpoint to connect to a WiFi network"""
    data = request.get_json()
    ssid = data.get('ssid', '').strip()
    password = data.get('password', '')

    log.info(f"Request to connect to SSID: '{ssid}'")

    if not ssid:
        return jsonify({'success': False, 'error': 'SSID is required'}), 400

    success = add_new_wifi_network(ssid, password)

    if success:
        return jsonify({'success': True, 'message': f'Connected to {ssid}'})
    else:
        return jsonify({'success': False, 'error': 'Failed to connect to network'}), 500


@api.route('/scan')
def scan() -> Response:
    """API endpoint to scan for available WiFi networks"""
    networks: list[dict[str, str]] = []
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                parts = line.split(':')
                if len(parts) >= 3:
                    ssid = parts[0]
                    signal = parts[1]
                    security = parts[2]
                    networks.append({
                        'ssid': ssid,
                        'signal': signal,
                        'security': security
                    })

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        log.error(f"Error scanning WiFi networks: {e}")

    return jsonify({'success': True, 'networks': networks})


def add_new_wifi_network(ssid: str, password: str) -> bool:
    """Add a new WiFi network using nmcli"""
    try:
        # Add the new WiFi connection
        result = subprocess.run(
            ['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            log.error(f"ERROR: nmcli output: {result.stdout}, error: {result.stderr}")
        return result.returncode == 0

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        log.error(f"Error adding WiFi network: {e}")
        return False


def get_default_interface() -> str:
    """Get the default gateway IP address"""
    try:
        result = subprocess.run(
            ['ip', 'route', 'show', 'default'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            line = result.stdout.strip()
            parts = line.split()
            if 'dev' in parts:
                dev_index = parts.index('dev')
                if dev_index + 1 < len(parts):
                    return parts[dev_index + 1]
        else:
            log.error(f"ERROR: ip command output: {result.stdout}, error: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        log.error(f"Error getting default interface: {e}")

    return 'N/A'


def get_ip_address() -> str:
    """Get the current IP address of the default interface interface"""
    try:

        result = subprocess.run(
            ['ip', 'addr', 'show', get_default_interface()],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('inet '):
                    ip = line.split()[1].split('/')[0]
                    return ip
        else:
            log.error(f"ERROR: ip command output: {result.stdout}, error: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        log.error(f"Error getting IP address: {e}")

    return 'N/A'


def get_wifi_info() -> dict[str, Any]:
    """Get current WiFi connection information"""
    try:
        # Try using nmcli (NetworkManager command line)
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'active,ssid,signal', 'dev', 'wifi'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line.startswith('yes:'):
                    parts = line.split(':')
                    if len(parts) >= 3:
                        ssid = parts[1]
                        signal = parts[2] if len(parts) > 2 else '0'

                        # Determine signal strength
                        try:
                            signal_int = int(signal)
                            if signal_int >= 70:
                                strength = 'Strong'
                            elif signal_int >= 50:
                                strength = 'Medium'
                            else:
                                strength = 'Weak'
                        except ValueError:
                            strength = 'Unknown'

                        return {
                            'connected': True,
                            'ssid': ssid,
                            'signal': f"{strength} ({signal}%)",
                            'signal_strength': signal,
                            'ip': get_ip_address()
                        }

        # If nmcli didn't work, try iwgetid
        result = subprocess.run(
            ['iwgetid', '-r'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and result.stdout.strip():
            ssid = result.stdout.strip()
            return {
                'connected': True,
                'ssid': ssid,
                'signal': 'Unknown',
                'signal_strength': '0'
            }

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        log.error(f"Error getting WiFi info: {e}")

    return {
        'connected': False,
        'ssid': 'Not Connected',
        'signal': 'N/A',
        'signal_strength': '0'
    }


if __name__ == '__main__':
    default_gw = get_default_interface()
    print(f"Default interface: {default_gw}")
    ip_addr = get_ip_address()
    print(f"IP Address: {ip_addr}")
    wifi_info = get_wifi_info()
    print(f"WiFi Info: {wifi_info}")

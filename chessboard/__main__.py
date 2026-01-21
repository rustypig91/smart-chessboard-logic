# from gevent import monkey
# monkey.patch_all()  # noqa
import os
import argparse
import logging
import chess

from chessboard.logger import log
from chessboard import is_raspberrypi
import chessboard.persistent_storage as persistent_storage

if is_raspberrypi:
    import chessboard.raspberry_pi_system


def create_certs() -> tuple[str, str]:
    """ Create self-signed SSL certificates if they do not exist. """
    key_path = persistent_storage.get_filename("certs", "key.pem")
    cert_path = persistent_storage.get_filename("certs", "cert.pem")
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    from datetime import datetime, timedelta, UTC
    from ipaddress import ip_address
    from socket import gethostname
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, gethostname() or "localhost"),
    ])

    alt_names = [
        x509.DNSName("localhost"),
        x509.DNSName(gethostname() or "localhost"),
        x509.IPAddress(ip_address("127.0.0.1")),
    ]
    try:
        alt_names.append(x509.IPAddress(ip_address("::1")))
    except ValueError:
        pass

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return cert_path, key_path


def main():
    parser = argparse.ArgumentParser(description="Chessboard Web App")
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the web server on')
    parser.add_argument('--persistent-storage-dir', type=str, default=persistent_storage.PERSISTENT_STORAGE_DIR,
                        help='Directory to use for caching data')

    args = parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)

    if args.persistent_storage_dir:
        persistent_storage.set_persistent_storage_dir(args.persistent_storage_dir)
        log.info(f"Persistent storage directory set to: {args.persistent_storage_dir}")

    # Initialize system by importing necessary modules
    import chessboard.events as events
    from chessboard.game.game_state import game_state
    import chessboard.api.api as api
    import chessboard.animations
    import chessboard.game

    cert_path, key_path = create_certs()

    api.socketio.run(api.app, debug=False, host='0.0.0.0', port=args.port,
                     allow_unsafe_werkzeug=True, ssl_context=(cert_path, key_path))


main()

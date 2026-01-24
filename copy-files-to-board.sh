#!/usr/bin/env bash
set -euo pipefail

# Usage: ./copy-files-to-board.sh <target-ip> [remote-path]
# Copies all files in ./chessboard/ to the remote host via SSH.

if [ $# -lt 1 ]; then
    echo "Usage: $0 <target-ip> [remote-path]" >&2
    exit 1
fi

HOST="$1"
REMOTE_PATH="${2:-~/chessboard}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="$SCRIPT_DIR/chessboard"

if [ ! -d "$LOCAL_DIR" ]; then
    echo "Local directory not found: $LOCAL_DIR" >&2
    exit 1
fi

rsync -az --info=progress2 --exclude '.git/' --exclude 'node_modules/' "$LOCAL_DIR/" "$HOST:$REMOTE_PATH/"
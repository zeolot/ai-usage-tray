#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# On UOS 20 Deepin Wayland, XWayland (xcb) allows accurate bottom-right
# popup positioning above dde-dock while keeping native SNI system tray support.
if [ -z "${QT_QPA_PLATFORM:-}" ] && [ -n "${DISPLAY:-}" ]; then
    export QT_QPA_PLATFORM=xcb
fi

exec /usr/bin/python3 "${SCRIPT_DIR}/run.py" "$@"

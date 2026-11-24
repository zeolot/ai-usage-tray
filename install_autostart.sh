#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART_DIR="${HOME}/.config/autostart"
AUTOSTART_FILE="${AUTOSTART_DIR}/ai-usage-tray.desktop"
APP_DIR="${HOME}/.local/share/applications"
APP_FILE="${APP_DIR}/ai-usage-tray.desktop"

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "${AUTOSTART_FILE}" "${APP_FILE}"
    echo "已移除开机自启与启动器快捷方式。"
    exit 0
fi

mkdir -p "${AUTOSTART_DIR}" "${APP_DIR}"

ICON_PATH="${SCRIPT_DIR}/assets/icon.png"

DESKTOP_CONTENT="[Desktop Entry]
Type=Application
Name=AI 用量统计
Name[en]=AI Usage Monitor
Comment=统计 Codex 与 Antigravity 的模型、Token 数与生成速度
Icon=${ICON_PATH}
Exec=/bin/bash \"${SCRIPT_DIR}/launch.sh\" --show
Terminal=false
Categories=Utility;Development;
X-GNOME-Autostart-enabled=true
X-Deepin-Autostart=true
"

# Autostart launches silently in tray (without --show)
AUTOSTART_CONTENT="[Desktop Entry]
Type=Application
Name=AI 用量统计
Name[en]=AI Usage Monitor
Comment=统计 Codex 与 Antigravity 的模型、Token 数与生成速度
Icon=${ICON_PATH}
Exec=/bin/bash \"${SCRIPT_DIR}/launch.sh\"
Terminal=false
Categories=Utility;Development;
X-GNOME-Autostart-enabled=true
X-Deepin-Autostart=true
"

printf '%s' "${AUTOSTART_CONTENT}" > "${AUTOSTART_FILE}"
printf '%s' "${DESKTOP_CONTENT}" > "${APP_FILE}"

echo "已安装："
echo "  开机自启: ${AUTOSTART_FILE}"
echo "  应用菜单: ${APP_FILE}"

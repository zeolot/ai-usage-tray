#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_NAME="ai-usage-tray"
VERSION="${1:-1.0.0}"
ARCH="all"
BUILD_ROOT="${SCRIPT_DIR}/build/deb-pkg"
OUT_DIR="${SCRIPT_DIR}/dist"
OUT_DEB="${OUT_DIR}/${PKG_NAME}_${VERSION}_${ARCH}.deb"

rm -rf "${BUILD_ROOT}"
mkdir -p \
    "${BUILD_ROOT}/DEBIAN" \
    "${BUILD_ROOT}/opt/${PKG_NAME}/ai_usage_tray" \
    "${BUILD_ROOT}/opt/${PKG_NAME}/assets" \
    "${BUILD_ROOT}/usr/bin" \
    "${BUILD_ROOT}/usr/share/applications" \
    "${BUILD_ROOT}/usr/share/icons/hicolor/256x256/apps" \
    "${OUT_DIR}"

# Copy application source & assets
cp "${SCRIPT_DIR}"/ai_usage_tray/*.py "${BUILD_ROOT}/opt/${PKG_NAME}/ai_usage_tray/"
cp "${SCRIPT_DIR}/run.py" "${BUILD_ROOT}/opt/${PKG_NAME}/"
cp "${SCRIPT_DIR}/launch.sh" "${BUILD_ROOT}/opt/${PKG_NAME}/"
cp "${SCRIPT_DIR}/assets/icon.png" "${BUILD_ROOT}/opt/${PKG_NAME}/assets/"
cp "${SCRIPT_DIR}/assets/icon.png" "${BUILD_ROOT}/usr/share/icons/hicolor/256x256/apps/${PKG_NAME}.png"
chmod 755 "${BUILD_ROOT}/opt/${PKG_NAME}/run.py" "${BUILD_ROOT}/opt/${PKG_NAME}/launch.sh"

# Wrapper command in /usr/bin
cat > "${BUILD_ROOT}/usr/bin/${PKG_NAME}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec /bin/bash "/opt/ai-usage-tray/launch.sh" "$@"
EOF
chmod 755 "${BUILD_ROOT}/usr/bin/${PKG_NAME}"

# Application menu entry
cat > "${BUILD_ROOT}/usr/share/applications/${PKG_NAME}.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=AI 用量统计
Name[en]=AI Usage Monitor
Comment=统计 Codex 与 Antigravity 的模型、Token 数与生成速度
Icon=ai-usage-tray
Exec=/usr/bin/ai-usage-tray --show
Terminal=false
Categories=Utility;Development;
StartupNotify=false
EOF
chmod 644 "${BUILD_ROOT}/usr/share/applications/${PKG_NAME}.desktop"

# Debian control metadata
INSTALLED_SIZE="$(du -sk "${BUILD_ROOT}/opt" "${BUILD_ROOT}/usr" | awk '{s+=$1} END {print s}')"
cat > "${BUILD_ROOT}/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.7), python3-pyqt5
Installed-Size: ${INSTALLED_SIZE}
Maintainer: zeolot <chenglijlu@163.com>
Homepage: https://github.com/zeolot/ai-usage-tray
Description: Taskbar usage monitor for Codex and Antigravity
 Lightweight system tray application that tracks Codex and Antigravity
 model usage, token counts, cache hit rate, estimated cost, and generation
 speed on UOS, Deepin, Ubuntu, and Debian desktops.
EOF
chmod 644 "${BUILD_ROOT}/DEBIAN/control"

# Remove any stale __pycache__ if copied and normalize permissions
find "${BUILD_ROOT}" -name "__pycache__" -type d -exec rm -rf {} +
find "${BUILD_ROOT}" -type d -exec chmod 755 {} +
find "${BUILD_ROOT}" -type f -exec chmod 644 {} +
chmod 755 "${BUILD_ROOT}/opt/${PKG_NAME}/run.py" "${BUILD_ROOT}/opt/${PKG_NAME}/launch.sh" "${BUILD_ROOT}/usr/bin/${PKG_NAME}"

dpkg-deb --build --root-owner-group "${BUILD_ROOT}" "${OUT_DEB}" 2>/dev/null \
    || dpkg-deb --build "${BUILD_ROOT}" "${OUT_DEB}"

echo "Built Debian package: ${OUT_DEB}"
dpkg-deb --info "${OUT_DEB}"

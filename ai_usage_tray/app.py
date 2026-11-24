# -*- coding: utf-8 -*-
"""Cross-platform (Windows & Linux) system tray application controller."""

import sys
import time

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QCursor, QGuiApplication
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QSystemTrayIcon

from .collector import UsageCollector
from .platform_utils import (
    IS_WINDOWS,
    SingleInstanceLock,
    is_autostart_enabled,
    set_autostart,
    setup_windows_app_id,
)
from .pricing import PricingManager
from .ui import (
    PricingDialog,
    UsagePopupWindow,
    create_tray_icon,
    format_cost,
    format_tokens,
)


class AIUsageTrayApp(object):
    """Main controller connecting QSystemTrayIcon, UsageCollector, and UsagePopupWindow."""

    def __init__(self, app, start_visible=False, refresh_interval_ms=10000):
        # type: (QApplication, bool, int) -> None
        self.app = app
        self.pricing = PricingManager()
        self.collector = UsageCollector(pricing_manager=self.pricing)
        self.popup = UsagePopupWindow()

        self.popup.filter_changed.connect(self._on_filter_changed)
        self.popup.refresh_requested.connect(self.refresh_now)
        self.popup.pricing_requested.connect(self.open_pricing_dialog)

        # System tray icon (multi-size QIcon for crisp Windows 10/11 & Linux UOS/Deepin rendering)
        tray_icon = create_tray_icon()
        self.app.setWindowIcon(tray_icon)
        self.tray = QSystemTrayIcon(tray_icon, self.app)
        self.tray.activated.connect(self._on_tray_activated)

        # Context menu
        self.menu = QMenu()
        self.act_toggle = QAction("显示 / 隐藏面板", self.menu)
        self.act_toggle.triggered.connect(self.toggle_popup)
        self.menu.addAction(self.act_toggle)

        self.act_refresh = QAction("立即刷新", self.menu)
        self.act_refresh.triggered.connect(self.refresh_now)
        self.menu.addAction(self.act_refresh)

        self.act_pricing = QAction("模型单价设置...", self.menu)
        self.act_pricing.triggered.connect(self.open_pricing_dialog)
        self.menu.addAction(self.act_pricing)

        self.menu.addSeparator()

        self.act_autostart = QAction("开机自启", self.menu)
        self.act_autostart.setCheckable(True)
        self.act_autostart.setChecked(is_autostart_enabled())
        self.act_autostart.triggered.connect(self._on_toggle_autostart)
        self.menu.addAction(self.act_autostart)

        self.menu.addSeparator()

        self.act_quit = QAction("退出", self.menu)
        self.act_quit.triggered.connect(self.app.quit)
        self.menu.addAction(self.act_quit)

        self.tray.setContextMenu(self.menu)
        self.tray.show()

        # Initial load
        self.refresh_now()

        # Periodic background refresh
        self.timer = QTimer(self.app)
        self.timer.timeout.connect(self.refresh_now)
        self.timer.start(refresh_interval_ms)

        if start_visible:
            QTimer.singleShot(150, self.show_popup)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            # Debounce if popup just auto-hid from clicking the tray icon itself
            if time.time() - self.popup._last_deactivate_ts < 0.25:
                return
            self.toggle_popup()

    def _on_filter_changed(self, _source, _time_range):
        self._render_current_view()

    def _on_toggle_autostart(self, checked):
        ok = set_autostart(bool(checked))
        if not ok:
            self.act_autostart.setChecked(is_autostart_enabled())

    def refresh_now(self):
        self.collector.refresh()
        self._render_current_view()
        self._update_tray_tooltip()

    def _render_current_view(self):
        summary = self.collector.get_summary(
            source_filter=self.popup.source_filter,
            time_range=self.popup.time_range,
        )
        self.popup.update_summary(summary, self.collector.last_refresh_ts)

    def _update_tray_tooltip(self):
        today = self.collector.get_summary(source_filter="all", time_range="today")
        total = self.collector.get_summary(source_filter="all", time_range="all")
        lines = [
            "AI 用量统计 (Codex & Antigravity)",
            "今日: {} tokens · {} 请求 · {}".format(
                format_tokens(today.total_tokens),
                today.total_requests,
                format_cost(today.total_cost_usd),
            ),
            "累计: {} tokens · {} 请求 · {}".format(
                format_tokens(total.total_tokens),
                total.total_requests,
                format_cost(total.total_cost_usd),
            ),
        ]
        if not IS_WINDOWS:
            lines.append("左键点击展开详情，右键打开菜单")
        # Windows Shell_NotifyIconW szTip limit is 128 chars; keep tooltip compact
        tip = "\n".join(lines)
        if IS_WINDOWS and len(tip) > 125:
            tip = tip[:124] + "…"
        self.tray.setToolTip(tip)

    def _position_popup(self):
        cursor_pos = QCursor.pos()
        screen = None
        if hasattr(QGuiApplication, "screenAt"):
            screen = QGuiApplication.screenAt(cursor_pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        avail = screen.availableGeometry()
        full = screen.geometry()
        pw = self.popup.width()
        ph = self.popup.height()
        margin = 6

        # Default: bottom-right corner inside available desktop area (above bottom taskbar)
        x = avail.right() - pw - margin
        y = avail.bottom() - ph - margin

        # Detect which screen edge holds the taskbar (supports bottom / top / left / right)
        top_bar = avail.top() - full.top()
        bottom_bar = full.bottom() - avail.bottom()
        left_bar = avail.left() - full.left()
        right_bar = full.right() - avail.right()

        if top_bar > max(bottom_bar, left_bar, right_bar, 0):
            y = avail.top() + margin
        elif left_bar > max(bottom_bar, top_bar, right_bar, 0):
            x = avail.left() + margin
            y = avail.bottom() - ph - margin
        elif right_bar > max(bottom_bar, top_bar, left_bar, 0):
            x = avail.right() - pw - margin
            y = avail.bottom() - ph - margin

        # Align horizontally/vertically near the tray icon if valid & on-screen
        tray_geo = self.tray.geometry()
        if (
            tray_geo.isValid()
            and tray_geo.width() > 0
            and tray_geo.height() > 0
            and full.intersects(tray_geo)
        ):
            cx = tray_geo.center().x()
            cy = tray_geo.center().y()
            if left_bar > max(bottom_bar, top_bar, 0):
                x = avail.left() + margin
                y = max(avail.top() + margin, min(avail.bottom() - ph - margin, cy - ph // 2))
            elif right_bar > max(bottom_bar, top_bar, 0):
                x = avail.right() - pw - margin
                y = max(avail.top() + margin, min(avail.bottom() - ph - margin, cy - ph // 2))
            else:
                x = max(avail.left() + margin, min(avail.right() - pw - margin, cx - pw // 2))
                if tray_geo.top() < full.center().y():
                    y = avail.top() + margin
                else:
                    y = avail.bottom() - ph - margin

        self.popup.move(int(x), int(y))

    def show_popup(self):
        self.refresh_now()
        self._position_popup()
        self.popup.show()
        self.popup.raise_()
        self.popup.activateWindow()

    def toggle_popup(self):
        if self.popup.isVisible():
            self.popup.hide()
        else:
            self.show_popup()

    def open_pricing_dialog(self):
        all_summary = self.collector.get_summary("all", "all")
        active_models = [m.model for m in all_summary.models]
        self.popup.set_modal_open(True)
        try:
            dlg = PricingDialog(self.pricing, active_models=active_models, parent=self.popup)
            if dlg.exec_() == PricingDialog.Accepted:
                self._render_current_view()
                self._update_tray_tooltip()
        finally:
            self.popup.set_modal_open(False)


def main():
    if "--install-autostart" in sys.argv:
        ok = set_autostart(True)
        print("Autostart enabled." if ok else "Failed to enable autostart.")
        return 0 if ok else 1

    if "--uninstall-autostart" in sys.argv:
        ok = set_autostart(False)
        print("Autostart disabled." if ok else "Failed to disable autostart.")
        return 0 if ok else 1

    start_visible = "--show" in sys.argv
    setup_windows_app_id()

    lock = SingleInstanceLock()
    if not lock.acquire():
        print("ai-usage-tray is already running.")
        return 0

    # Enable crisp HiDPI scaling on Windows 10/11 and Linux
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("AI 用量统计")

    controller = AIUsageTrayApp(app, start_visible=start_visible)
    try:
        return app.exec_()
    finally:
        lock.release()

# -*- coding: utf-8 -*-
"""PyQt5 popup panel, model usage card rows, and pricing settings dialog."""

import datetime
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, QRectF, QSize, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import ModelStats, SummaryStats
from .pricing import DEFAULT_PRICING, PricingManager

# Palette starting with the exact bright blue from the user's screenshot
MODEL_COLORS = [
    "#1693D0",  # Sky blue (screenshot primary)
    "#10B981",  # Emerald
    "#8B5CF6",  # Violet
    "#F59E0B",  # Amber
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#6366F1",  # Indigo
    "#EF4444",  # Coral red
]


def format_tokens(count):
    # type: (int) -> str
    """Format token count cleanly: 18M, 2.4M, 850K, 12.3K, 512."""
    n = int(count or 0)
    if n >= 1000000000:
        val = n / 1000000000.0
        if val >= 10.0:
            return "{:.0f}B".format(val)
        s = "{:.1f}".format(val)
        if s.endswith(".0"):
            s = s[:-2]
        return s + "B"
    if n >= 1000000:
        val = n / 1000000.0
        if val >= 10.0:
            return "{:.0f}M".format(val)
        s = "{:.1f}".format(val)
        if s.endswith(".0"):
            s = s[:-2]
        return s + "M"
    if n >= 1000:
        val = n / 1000.0
        if val >= 10.0:
            return "{:.0f}K".format(val)
        s = "{:.1f}".format(val)
        if s.endswith(".0"):
            s = s[:-2]
        return s + "K"
    return str(n)


def format_cost(usd):
    # type: (float) -> str
    if usd < 0.005:
        return "$0.00"
    if usd < 100.0:
        return "${:.2f}".format(usd)
    return "${:,.1f}".format(usd)


def format_speed(tps, is_estimated=False):
    # type: (float, bool) -> str
    prefix = "~" if is_estimated else ""
    if tps >= 10.0:
        return "{}{:.0f}\u00A0token/秒".format(prefix, tps)
    return "{}{:.1f}\u00A0token/秒".format(prefix, tps)


def format_ttft(sec):
    # type: (float) -> str
    if sec >= 10.0:
        return "首字\u00A0{:.0f}\u00A0秒".format(sec)
    return "首字\u00A0{:.1f}\u00A0秒".format(sec)


def create_tray_icon_pixmap(size=64):
    # type: (int) -> QPixmap
    """Draw a crisp rounded gradient badge icon for the taskbar tray."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    margin = size * 0.08
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.24, size * 0.24)
    p.fillPath(path, QColor("#1693D0"))

    # Subtle inner border
    p.setPen(QPen(QColor(255, 255, 255, 55), max(1.0, size * 0.03)))
    p.drawPath(path)

    # Three ascending usage bars (minimalist chart glyph)
    bar_w = size * 0.14
    gap = size * 0.08
    total_w = 3 * bar_w + 2 * gap
    start_x = (size - total_w) / 2.0
    bottom_y = size * 0.74
    heights = [size * 0.24, size * 0.44, size * 0.34]
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#FFFFFF")))
    for i, h in enumerate(heights):
        x = start_x + i * (bar_w + gap)
        bar_rect = QRectF(x, bottom_y - h, bar_w, h)
        p.drawRoundedRect(bar_rect, bar_w * 0.45, bar_w * 0.45)

    p.end()
    return pm


def create_tray_icon():
    # type: () -> QIcon
    """Create a multi-size QIcon for crisp rendering on Windows & Linux taskbars."""
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64):
        icon.addPixmap(create_tray_icon_pixmap(sz))
    return icon


class PillDotWidget(QWidget):
    """Vertical rounded pill dot matching the screenshot's left model marker."""

    def __init__(self, color_hex, parent=None):
        # type: (str, Optional[QWidget]) -> None
        super(PillDotWidget, self).__init__(parent)
        self._color = QColor(color_hex)
        self.setFixedSize(10, 16)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(self._color))
        p.drawRoundedRect(QRectF(1.0, 2.0, 8.0, 12.0), 3.5, 3.5)
        p.end()


class SlimProgressBar(QWidget):
    """Smooth antialiased slim rounded progress bar matching the screenshot."""

    def __init__(self, ratio, color_hex, parent=None):
        # type: (float, str, Optional[QWidget]) -> None
        super(SlimProgressBar, self).__init__(parent)
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self._color = QColor(color_hex)
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)

        w = float(self.width())
        h = float(self.height())
        r = h / 2.0

        # Track
        p.setBrush(QBrush(QColor("#EFEFF2")))
        p.drawRoundedRect(QRectF(0.0, 0.0, w, h), r, r)

        # Fill (keep minimum visible nub if > 0)
        if self._ratio > 0.0:
            fill_w = max(h, w * self._ratio)
            p.setBrush(QBrush(self._color))
            p.drawRoundedRect(QRectF(0.0, 0.0, min(w, fill_w), h), r, r)
        p.end()


class ModelRowWidget(QFrame):
    """One model usage card row closely matching the screenshot design."""

    def __init__(self, stats, color_hex, show_source_badge=True, parent=None):
        # type: (ModelStats, str, bool, Optional[QWidget]) -> None
        super(ModelRowWidget, self).__init__(parent)
        self.setObjectName("ModelRow")
        self.setStyleSheet(
            """
            QFrame#ModelRow {
                background: transparent;
                border-radius: 8px;
            }
            QFrame#ModelRow:hover {
                background: #F7F9FB;
            }
            """
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # Left column: vertical pill dot aligned with model title
        dot_wrap = QVBoxLayout()
        dot_wrap.setContentsMargins(0, 2, 0, 0)
        dot_wrap.addWidget(PillDotWidget(color_hex, self))
        dot_wrap.addStretch(1)
        outer.addLayout(dot_wrap)

        # Right column: title line + progress bar + metadata subtext
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)

        # Top row: model name (+ optional tiny source badge) | right-aligned total tokens
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        name_lbl = QLabel(stats.model, self)
        name_lbl.setStyleSheet(
            "color: #1F2329; font-size: 14px; font-weight: 600; background: transparent;"
        )
        top_row.addWidget(name_lbl)

        if show_source_badge and stats.sources:
            src_name = "Codex" if "codex" in stats.sources else "AGY"
            badge = QLabel(src_name, self)
            if src_name == "Codex":
                badge_style = (
                    "color: #0B74B8; background: #EAF5FC; border-radius: 4px; "
                    "padding: 1px 5px; font-size: 10px; font-weight: 500;"
                )
            else:
                badge_style = (
                    "color: #0D8A62; background: #E9F8F2; border-radius: 4px; "
                    "padding: 1px 5px; font-size: 10px; font-weight: 500;"
                )
            badge.setStyleSheet(badge_style)
            top_row.addWidget(badge)

        top_row.addStretch(1)

        tok_lbl = QLabel(format_tokens(stats.total_tokens), self)
        tok_lbl.setStyleSheet(
            "color: #1F2329; font-size: 14px; font-weight: 600; background: transparent;"
        )
        top_row.addWidget(tok_lbl)
        right.addLayout(top_row)

        # Middle row: slim progress bar
        bar = SlimProgressBar(stats.share_pct / 100.0, color_hex, self)
        right.addWidget(bar)

        # Bottom row: exact screenshot-style metadata summary (non-breaking spaces inside each chip)
        parts = [
            "{:,}\u00A0个请求".format(stats.requests),
            format_cost(stats.cost_usd),
        ]
        tps = stats.tokens_per_sec
        if tps is not None:
            parts.append(format_speed(tps, stats.speed_is_estimated))
            parts.append("{}\u00A0次计时".format(stats.timed_count))
        ttft = stats.avg_ttft_sec
        if ttft is not None:
            parts.append(format_ttft(ttft))
        hit = stats.cache_hit_pct
        if hit is not None:
            parts.append("命中率\u00A0{:.0f}%".format(hit))
        parts.append("{:.0f}%".format(stats.share_pct))

        meta_lbl = QLabel(" · ".join(parts), self)
        meta_lbl.setWordWrap(True)
        meta_lbl.setStyleSheet(
            "color: #7A828E; font-size: 12px; line-height: 1.4; background: transparent;"
        )
        right.addWidget(meta_lbl)

        outer.addLayout(right, 1)

        # Detailed hover tooltip
        src_display = "Codex" if "codex" in stats.sources else "Antigravity"
        tip_lines = [
            "模型: {} ({})".format(stats.model, src_display),
            "总 Token: {:,} ({:.1f}%)".format(stats.total_tokens, stats.share_pct),
            "  • 新输入: {:,}".format(stats.uncached_input),
            "  • 缓存命中: {:,}".format(stats.cached_input),
            "  • 输出: {:,}{}".format(
                stats.output_tokens,
                " (含推理 {:,})".format(stats.reasoning_tokens)
                if stats.reasoning_tokens > 0
                else "",
            ),
            "请求数: {:,} | 估算费用: {}".format(stats.requests, format_cost(stats.cost_usd)),
        ]
        if tps is not None:
            tip_lines.append(
                "速度: {} ({} 次计时{})".format(
                    format_speed(tps, stats.speed_is_estimated),
                    stats.timed_count,
                    "，端到端时间差估算" if stats.speed_is_estimated else "，流式输出精确计时",
                )
            )
        if ttft is not None:
            tip_lines.append("平均首字延迟: {:.2f} 秒 ({} 次)".format(ttft, stats.ttft_count))
        self.setToolTip("\n".join(tip_lines))


class PricingDialog(QDialog):
    """Modal dialog to view/edit per-model USD/1M token pricing."""

    def __init__(self, pricing_manager, active_models=None, parent=None):
        # type: (PricingManager, Optional[List[str]], Optional[QWidget]) -> None
        super(PricingDialog, self).__init__(parent)
        self.pricing = pricing_manager
        self.setWindowTitle("模型单价设置 (USD / 1M Tokens)")
        self.resize(520, 400)
        self.setStyleSheet(
            """
            QDialog { background: #FFFFFF; }
            QLabel { color: #374151; font-size: 12px; }
            QTableWidget {
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                gridline-color: #F1F3F5;
                font-size: 12px;
                background: #FFFFFF;
            }
            QHeaderView::section {
                background: #F7F8FA;
                color: #4B5563;
                font-weight: 600;
                border: none;
                border-bottom: 1px solid #E5E7EB;
                padding: 6px;
            }
            QPushButton {
                background: #F3F4F6;
                color: #1F2329;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover { background: #E5E7EB; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hint = QLabel(
            "单价单位为美元 / 百万 Token（USD / 1M），用于估算面板中的 $ 费用。双击单元格可直接修改：",
            self,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Merge known prices + currently observed models
        all_models = set(self.pricing.prices.keys())
        if active_models:
            for m in active_models:
                all_models.add(m)
        sorted_models = sorted(
            [m for m in all_models if m != "_default"]
        ) + ["_default"]

        self.table = QTableWidget(len(sorted_models), 4, self)
        self.table.setHorizontalHeaderLabels(["模型名称", "新输入 ($)", "缓存命中 ($)", "输出 ($)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._populate_table(sorted_models)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("恢复默认单价", self)
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)

        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        box.button(QDialogButtonBox.Save).setText("保存")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        box.accepted.connect(self._on_save)
        box.rejected.connect(self.reject)
        btn_row.addWidget(box)
        layout.addLayout(btn_row)

    def _populate_table(self, model_names):
        # type: (List[str]) -> None
        self.table.setRowCount(len(model_names))
        for r, name in enumerate(model_names):
            in_r, cache_r, out_r = self.pricing.get_rate(name)
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, QTableWidgetItem("{:.3f}".format(in_r).rstrip("0").rstrip(".")))
            self.table.setItem(r, 2, QTableWidgetItem("{:.3f}".format(cache_r).rstrip("0").rstrip(".")))
            self.table.setItem(r, 3, QTableWidgetItem("{:.3f}".format(out_r).rstrip("0").rstrip(".")))

    def _on_reset(self):
        self.pricing.prices = {k: dict(v) for k, v in DEFAULT_PRICING.items()}
        names = sorted([m for m in self.pricing.prices if m != "_default"]) + ["_default"]
        self._populate_table(names)

    def _on_save(self):
        new_prices = {}  # type: Dict[str, Dict[str, float]]
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 0)
            if not name_item:
                continue
            name = name_item.text().strip()
            try:
                in_val = float(self.table.item(r, 1).text().strip())
                cache_val = float(self.table.item(r, 2).text().strip())
                out_val = float(self.table.item(r, 3).text().strip())
            except Exception:
                continue
            new_prices[name] = {
                "input": max(0.0, in_val),
                "cached_input": max(0.0, cache_val),
                "output": max(0.0, out_val),
            }
        self.pricing.save(new_prices)
        self.accept()


class UsagePopupWindow(QWidget):
    """Frameless light-mode floating card panel opened from the taskbar tray."""

    filter_changed = pyqtSignal(str, str)  # source_filter, time_range
    refresh_requested = pyqtSignal()
    pricing_requested = pyqtSignal()

    def __init__(self, parent=None):
        super(UsagePopupWindow, self).__init__(parent)
        self.source_filter = "all"
        self.time_range = "all"
        self._modal_open = False
        self._last_deactivate_ts = 0.0
        self._drag_pos = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(444)
        self.setMinimumHeight(260)
        self.setMaximumHeight(680)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame(self)
        self.card.setObjectName("MainCard")
        self.card.setStyleSheet(
            """
            QWidget {
                font-family: "Microsoft YaHei UI", "Segoe UI", "Noto Sans CJK SC", "WenQuanYi Micro Hei", sans-serif;
            }
            QFrame#MainCard {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 14px;
            }
            """
        )

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(15, 23, 42, 42))
        self.card.setGraphicsEffect(shadow)
        root_layout.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        # --- Header bar ---
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_lbl = QLabel(self.card)
        icon_lbl.setPixmap(create_tray_icon_pixmap(20))
        icon_lbl.setFixedSize(20, 20)
        header.addWidget(icon_lbl)

        title_lbl = QLabel("AI 用量统计", self.card)
        title_lbl.setStyleSheet(
            "color: #1F2329; font-size: 15px; font-weight: 700; background: transparent;"
        )
        header.addWidget(title_lbl)
        header.addStretch(1)

        btn_css = """
            QPushButton {
                background: transparent;
                color: #6B7280;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #F2F4F7;
                color: #1F2329;
            }
        """
        self.btn_refresh = QPushButton("↻", self.card)
        self.btn_refresh.setToolTip("立即刷新数据")
        self.btn_refresh.setFixedSize(26, 26)
        self.btn_refresh.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_refresh.setStyleSheet(btn_css)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        header.addWidget(self.btn_refresh)

        self.btn_pricing = QPushButton("$", self.card)
        self.btn_pricing.setToolTip("配置模型单价")
        self.btn_pricing.setFixedSize(26, 26)
        self.btn_pricing.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_pricing.setStyleSheet(btn_css)
        self.btn_pricing.clicked.connect(self.pricing_requested.emit)
        header.addWidget(self.btn_pricing)

        self.btn_close = QPushButton("×", self.card)
        self.btn_close.setToolTip("隐藏面板")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_close.setStyleSheet(btn_css)
        self.btn_close.clicked.connect(self.hide)
        header.addWidget(self.btn_close)

        card_layout.addLayout(header)

        # --- Summary KPI strip ---
        kpi_frame = QFrame(self.card)
        kpi_frame.setObjectName("KpiStrip")
        kpi_frame.setStyleSheet(
            "QFrame#KpiStrip { background: #F7F8FA; border-radius: 10px; }"
        )
        kpi_layout = QHBoxLayout(kpi_frame)
        kpi_layout.setContentsMargins(10, 8, 10, 8)
        kpi_layout.setSpacing(6)

        self.kpi_tokens = self._make_kpi_item(kpi_layout, "总 Token")
        self.kpi_reqs = self._make_kpi_item(kpi_layout, "总请求")
        self.kpi_cost = self._make_kpi_item(kpi_layout, "估算费用")
        self.kpi_cache = self._make_kpi_item(kpi_layout, "缓存命中")
        card_layout.addWidget(kpi_frame)

        # --- Filter segmented buttons ---
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self._source_btns = {}  # type: Dict[str, QPushButton]
        src_group = QFrame(self.card)
        src_group.setStyleSheet("QFrame { background: #F2F4F7; border-radius: 8px; }")
        src_lay = QHBoxLayout(src_group)
        src_lay.setContentsMargins(2, 2, 2, 2)
        src_lay.setSpacing(2)
        for key, label in (("all", "全部"), ("codex", "Codex"), ("antigravity", "Antigravity")):
            btn = QPushButton(label, src_group)
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda _chk, k=key: self._set_source(k))
            src_lay.addWidget(btn)
            self._source_btns[key] = btn
        filter_row.addWidget(src_group)
        filter_row.addStretch(1)

        self._range_btns = {}  # type: Dict[str, QPushButton]
        rng_group = QFrame(self.card)
        rng_group.setStyleSheet("QFrame { background: #F2F4F7; border-radius: 8px; }")
        rng_lay = QHBoxLayout(rng_group)
        rng_lay.setContentsMargins(2, 2, 2, 2)
        rng_lay.setSpacing(2)
        for key, label in (("today", "今日"), ("7d", "7天"), ("30d", "30天"), ("all", "全部")):
            btn = QPushButton(label, rng_group)
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda _chk, k=key: self._set_range(k))
            rng_lay.addWidget(btn)
            self._range_btns[key] = btn
        filter_row.addWidget(rng_group)
        card_layout.addLayout(filter_row)

        self._refresh_filter_styles()

        # --- Scrollable Model List ---
        self.scroll = QScrollArea(self.card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            """
            QScrollArea { background: transparent; }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 2px 0px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #D1D5DB;
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover { background: #9CA3AF; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                width: 0px;
                border: none;
                background: none;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                border: none;
            }
            """
        )

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 2, 0)
        self.list_layout.setSpacing(2)
        self.scroll.setWidget(self.list_container)
        card_layout.addWidget(self.scroll, 1)

        # --- Footer ---
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 2, 2, 0)
        self.footer_left = QLabel("加载中...", self.card)
        self.footer_left.setStyleSheet("color: #9CA3AF; font-size: 11px; background: transparent;")
        self.footer_right = QLabel("", self.card)
        self.footer_right.setStyleSheet("color: #9CA3AF; font-size: 11px; background: transparent;")
        footer.addWidget(self.footer_left)
        footer.addStretch(1)
        footer.addWidget(self.footer_right)
        card_layout.addLayout(footer)

    def _make_kpi_item(self, parent_layout, label_text):
        # type: (QHBoxLayout, str) -> QLabel
        box = QVBoxLayout()
        box.setSpacing(2)
        val_lbl = QLabel("—", self.card)
        val_lbl.setAlignment(Qt.AlignCenter)
        val_lbl.setStyleSheet(
            "color: #1F2329; font-size: 15px; font-weight: 700; background: transparent;"
        )
        cap_lbl = QLabel(label_text, self.card)
        cap_lbl.setAlignment(Qt.AlignCenter)
        cap_lbl.setStyleSheet(
            "color: #7A828E; font-size: 11px; background: transparent;"
        )
        box.addWidget(val_lbl)
        box.addWidget(cap_lbl)
        parent_layout.addLayout(box, 1)
        return val_lbl

    def _refresh_filter_styles(self):
        active_css = (
            "QPushButton { background: #FFFFFF; color: #1F2329; border: none; "
            "border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 600; }"
        )
        idle_css = (
            "QPushButton { background: transparent; color: #6B7280; border: none; "
            "border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { color: #1F2329; }"
        )
        for k, b in self._source_btns.items():
            is_on = k == self.source_filter
            b.setChecked(is_on)
            b.setStyleSheet(active_css if is_on else idle_css)
        for k, b in self._range_btns.items():
            is_on = k == self.time_range
            b.setChecked(is_on)
            b.setStyleSheet(active_css if is_on else idle_css)

    def _set_source(self, source_key):
        # type: (str) -> None
        if source_key == self.source_filter:
            return
        self.source_filter = source_key
        self._refresh_filter_styles()
        self.filter_changed.emit(self.source_filter, self.time_range)

    def _set_range(self, range_key):
        # type: (str) -> None
        if range_key == self.time_range:
            return
        self.time_range = range_key
        self._refresh_filter_styles()
        self.filter_changed.emit(self.source_filter, self.time_range)

    def set_modal_open(self, flag):
        # type: (bool) -> None
        self._modal_open = bool(flag)

    def update_summary(self, summary, refreshed_ts):
        # type: (SummaryStats, float) -> None
        self.kpi_tokens.setText(format_tokens(summary.total_tokens))
        self.kpi_reqs.setText("{:,}".format(summary.total_requests))
        self.kpi_cost.setText(format_cost(summary.total_cost_usd))
        if summary.cache_hit_pct is not None:
            self.kpi_cache.setText("{:.0f}%".format(summary.cache_hit_pct))
        else:
            self.kpi_cache.setText("—")

        # Clear existing model rows
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not summary.models:
            empty = QLabel("当前筛选条件下暂无使用记录", self.list_container)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                "color: #9CA3AF; font-size: 13px; padding: 36px 12px; background: transparent;"
            )
            self.list_layout.addWidget(empty)
        else:
            show_badge = self.source_filter == "all"
            for idx, ms in enumerate(summary.models):
                color = MODEL_COLORS[idx % len(MODEL_COLORS)]
                row = ModelRowWidget(ms, color, show_source_badge=show_badge, parent=self.list_container)
                self.list_layout.addWidget(row)
                if idx < len(summary.models) - 1:
                    sep = QFrame(self.list_container)
                    sep.setFixedHeight(1)
                    sep.setStyleSheet("background: #F1F3F5; margin-left: 28px; margin-right: 10px;")
                    self.list_layout.addWidget(sep)

        self.list_layout.addStretch(1)

        # Adjust popup height gracefully to content
        row_count = len(summary.models)
        desired_h = 216 + max(1, row_count) * 104
        self.resize(self.width(), max(280, min(670, desired_h)))

        # Footer text
        if refreshed_ts > 0:
            tstr = datetime.datetime.fromtimestamp(refreshed_ts).strftime("%H:%M:%S")
            self.footer_left.setText("更新于 {} · 自动刷新".format(tstr))
        cx_tok = format_tokens(summary.source_totals.get("codex", 0))
        ag_tok = format_tokens(summary.source_totals.get("antigravity", 0))
        self.footer_right.setText("Codex {} · AGY {}".format(cx_tok, ag_tok))

    # --- Allow dragging the card gently if user wants to move it ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super(UsagePopupWindow, self).mouseReleaseEvent(event)

    def changeEvent(self, event):
        # Hide popup automatically when user clicks elsewhere on desktop
        if event.type() == event.ActivationChange:
            if not self.isActiveWindow() and not self._modal_open:
                import time
                self._last_deactivate_ts = time.time()
                self.hide()
        super(UsagePopupWindow, self).changeEvent(event)

"""
Module: ui_overlay.py
Mục đích: Giao diện Overlay hiển thị trạng thái của Trợ lý ảo Echo Assistant.
Chức năng:
    - Cửa sổ trong suốt (translucent background), không viền (frameless), luôn trên cùng (always on top).
    - Căn chính giữa màn hình trung tâm của người dùng.
    - Vẽ hiệu ứng 'Glow Orb' (vòng tròn phát sáng ma thuật giống Siri) bằng QPainter và QRadialGradient.
    - Hiệu ứng phập phồng (breathing / pulsing animation) mượt mà với QTimer (60 FPS).
    - Hỗ trợ đa luồng an toàn tuyệt đối qua PyQt6 Signal/Slot.
"""

import math
import sys
from typing import Optional

from PyQt6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QRadialGradient,
    QScreen,
)
from PyQt6.QtWidgets import QApplication, QWidget


class OverlaySignals(QObject):
    """Signals điều phối giao diện Overlay từ bất kỳ luồng (thread) nào."""
    show_requested = pyqtSignal(str)
    hide_requested = pyqtSignal()
    status_updated = pyqtSignal(str)


class GlowOrbOverlay(QWidget):
    """
    Cửa sổ hiển thị quả cầu phát sáng (Glow Orb) nằm giữa màn hình.
    """

    def __init__(self, size: int = 300, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.orb_size = size
        self.status_text = "Echo đang lắng nghe..."
        self._pulse_phase = 0.0

        # Khởi tạo signals cho giao tiếp an toàn đa luồng
        self.signals = OverlaySignals()
        self.signals.show_requested.connect(self._on_show_requested)
        self.signals.hide_requested.connect(self._on_hide_requested)
        self.signals.status_updated.connect(self._on_status_updated)

        # Cấu hình cửa sổ trong suốt, không viền, luôn trên cùng
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # Tránh hiện icon gây phiền toái trên thanh Taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.setFixedSize(self.orb_size, self.orb_size)

        # Timer tạo hiệu ứng nhấp nháy / phập phồng (breathing animation) ~60 FPS
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)  # ~60 FPS (16ms)
        self._anim_timer.timeout.connect(self._advance_animation)

        # Định vị chính giữa màn hình chính
        self.center_on_screen()

    def center_on_screen(self) -> None:
        """Căn chỉnh cửa sổ overlay vào chính giữa màn hình chính."""
        screen: Optional[QScreen] = QGuiApplication.primaryScreen()
        if screen:
            screen_geo = screen.geometry()
            x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
            y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
            self.move(x, y)

    def _advance_animation(self) -> None:
        """Cập nhật pha dao động của hiệu ứng phập phồng."""
        self._pulse_phase = (self._pulse_phase + 0.05) % (2 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:
        """Vẽ hiệu ứng Glow Orb bằng QPainter và QRadialGradient đa tầng."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        center_x = w / 2.0
        # Dời tâm orb lên trên một chút để chừa chỗ cho dòng trạng thái bên dưới
        center_y = (h / 2.0) - 15.0

        # Tính toán độ phập phồng (pulsing breathing effect)
        # Bán kính biến thiên nhịp nhàng từ base_radius +/- pulse_delta
        pulse = math.sin(self._pulse_phase)
        base_radius = (self.orb_size * 0.28) + (pulse * 6.0)
        outer_glow_radius = base_radius * 1.85

        # -------------------------------------------------------------
        # 1. LỚP QUẦNG SÁNG NGOÀI (Ambient Outer Halo Gradient - Tím/Xanh Siri)
        # -------------------------------------------------------------
        outer_grad = QRadialGradient(QPointF(center_x, center_y), outer_glow_radius)
        # Màu tím neon Siri mờ ảo
        outer_grad.setColorAt(0.0, QColor(138, 43, 226, int(110 + pulse * 25)))   # BlueViolet
        outer_grad.setColorAt(0.4, QColor(0, 180, 255, int(80 + pulse * 20)))     # Electric Cyan
        outer_grad.setColorAt(0.7, QColor(75, 0, 130, int(40 + pulse * 15)))      # Indigo
        outer_grad.setColorAt(1.0, QColor(0, 0, 0, 0))                             # Hoàn toàn trong suốt

        painter.setBrush(outer_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(center_x, center_y),
            outer_glow_radius,
            outer_glow_radius,
        )

        # -------------------------------------------------------------
        # 2. LỚP LÕI PHÁT SÁNG CHÍNH (Core Vibrant Glow Orb)
        # -------------------------------------------------------------
        core_grad = QRadialGradient(QPointF(center_x, center_y), base_radius)
        # Tâm sáng rực trắng-cyan
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 245))
        core_grad.setColorAt(0.25, QColor(0, 245, 255, 230))                       # Cyan rực rỡ
        core_grad.setColorAt(0.55, QColor(160, 32, 240, 200))                      # Tím Magenta
        core_grad.setColorAt(0.85, QColor(0, 120, 255, 120))                       # Deep Sky Blue
        core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setBrush(core_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(center_x, center_y), base_radius, base_radius)

        # -------------------------------------------------------------
        # 3. VÒNG SÁNG ĐIỆN TỬ VIỀN MỎNG (Inner Dynamic Shimmer Ring)
        # -------------------------------------------------------------
        ring_radius = base_radius * 0.75 + (math.cos(self._pulse_phase) * 3.0)
        ring_color = QColor(255, 255, 255, int(140 + pulse * 40))
        painter.setPen(ring_color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(center_x, center_y), ring_radius, ring_radius)

        # -------------------------------------------------------------
        # 4. DÒNG CHỮ TRẠNG THÁI HIỂN THỊ (Status Text)
        # -------------------------------------------------------------
        if self.status_text:
            font = QFont("Segoe UI", 10)
            font.setBold(True)
            painter.setFont(font)

            text_rect = QRectF(0, h - 45, w, 35)

            # Đổ bóng chữ (Drop shadow) màu đen mờ để dễ nhìn trên mọi hình nền
            painter.setPen(QColor(0, 0, 0, 180))
            shadow_rect = QRectF(1, h - 44, w, 35)
            painter.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter, self.status_text)

            # Chữ chính màu trắng phát quang nhẹ
            painter.setPen(QColor(230, 250, 255, 230))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.status_text)

    # -----------------------------------------------------------------
    # SLOTS XỬ LÝ NỘI BỘ (Chạy trên Qt Main Thread)
    # -----------------------------------------------------------------
    @pyqtSlot(str)
    def _on_show_requested(self, status: str) -> None:
        if status:
            self.status_text = status
        self.center_on_screen()
        self._anim_timer.start()
        self.show()
        self.raise_()

    @pyqtSlot()
    def _on_hide_requested(self) -> None:
        self._anim_timer.stop()
        self.hide()

    @pyqtSlot(str)
    def _on_status_updated(self, text: str) -> None:
        self.status_text = text
        self.update()

    # -----------------------------------------------------------------
    # CÁC HÀM CÔNG KHAI (Thread-Safe Public API)
    # Có thể gọi an toàn từ bất kỳ luồng nào (Worker, WakeWord, STT...)
    # -----------------------------------------------------------------
    def show_overlay(self, status: str = "Echo đang lắng nghe...") -> None:
        """Hiển thị overlay kèm chữ trạng thái (an toàn từ mọi luồng)."""
        self.signals.show_requested.emit(status)

    def hide_overlay(self) -> None:
        """Ẩn overlay và dừng animation (an toàn từ mọi luồng)."""
        self.signals.hide_requested.emit()

    def set_status(self, text: str) -> None:
        """Cập nhật dòng chữ trạng thái (an toàn từ mọi luồng)."""
        self.signals.status_updated.emit(text)


# Khối chạy thử nghiệm độc lập
if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = GlowOrbOverlay()

    print("[UI Overlay] Đang mở giao diện Glow Orb phát sáng thử nghiệm...")
    overlay.show_overlay("Echo đang lắng nghe...")

    # Tự động đổi trạng thái sau 3s và ẩn sau 6s để kiểm tra
    QTimer.singleShot(3000, lambda: overlay.set_status("Đang giải mã ý định..."))
    QTimer.singleShot(6000, lambda: (print("[UI Overlay] Tự động ẩn overlay."), overlay.hide_overlay()))
    QTimer.singleShot(7000, lambda: (print("[UI Overlay] Đóng ứng dụng test."), app.quit()))

    sys.exit(app.exec())

"""
Module: app_tray.py
Mục đích: Chương trình điều phối chính của Trợ lý ảo Tèo Assistant.
Chức năng:
    - Quản lý giao diện PyQt6 trên luồng chính (Main Thread):
        + Cửa sổ Glow Orb Overlay trong suốt, mờ ảo chính giữa màn hình.
        + Khay hệ thống (System Tray Icon) chạy ngầm trên thanh tác vụ Windows Taskbar.
    - Chạy bộ nhận diện Wake Word "Tèo" (Vosk tiếng Việt) và pipeline xử lý lệnh trên các luồng phụ (QThread / Worker).
    - Luồng hoạt động hoàn chỉnh (Hands-Free Voice Flow):
        1. Người dùng gọi từ khóa ("Tèo ơi", "Ê Tèo", "Tèo", "Anh Tèo"...).
        2. WakeWordEngine (Vosk) phát hiện -> Tự động nhường micro cho STT.
        3. Phát tín hiệu mở Overlay phát sáng (Glow Orb).
        4. Phát tiếng "Bíp" xác nhận bằng winsound.
        5. Thu âm câu lệnh qua STT Engine (Google STT / Vosk Offline).
        6. Bộ não (Brain) phân tích ý định.
        7. Bộ thực thi (ActionExecutor) chạy hành động.
        8. Hoàn tất -> Ẩn Overlay -> Mở lại luồng lắng nghe Wake Word.
"""

import ctypes
import os
import socket
import sys
import threading
import time
import winsound
from typing import Optional

# Đảm bảo tiếng Việt hiển thị chính xác trên Windows Console
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# =============================================================================
# SINGLE INSTANCE GUARD (Kiểm tra tức thì TRƯỚC KHI nạp bất kỳ thư viện nặng nào)
# =============================================================================
_SINGLE_INSTANCE_MUTEX = None
_SINGLE_INSTANCE_SOCKET = None
_IS_ALREADY_ACQUIRED = False
SINGLE_INSTANCE_PORT = 65432


def ensure_single_instance() -> bool:
    """
    Kiểm tra và đảm bảo chỉ có duy nhất 1 tiến trình Tèo Assistant chạy trên hệ thống.
    Sử dụng cơ chế Dual-Lock (Windows Named Mutex qua ctypes + Socket bind localhost:65432):
        1. Named Mutex: Cơ chế Windows API giải phóng tức thì khi tiến trình bị đóng (kể cả crash).
        2. Localhost Socket: Lớp bảo vệ bổ trợ ngăn chặn xung đột trên mọi môi trường.

    Trả về:
        True: Nếu đây là tiến trình duy nhất (được phép khởi động).
        False: Nếu đã có một tiến trình khác đang chạy ngầm.
    """
    global _SINGLE_INSTANCE_MUTEX, _SINGLE_INSTANCE_SOCKET, _IS_ALREADY_ACQUIRED

    if _IS_ALREADY_ACQUIRED:
        return True

    # 1. Kiểm tra qua Windows Named Mutex (ctypes)
    if sys.platform.startswith("win"):
        try:
            ERROR_ALREADY_EXISTS = 183
            kernel32 = ctypes.windll.kernel32
            mutex_name = "Local\\TeoAssistant_SingleInstance_Mutex"
            mutex = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = kernel32.GetLastError()
            if last_error == ERROR_ALREADY_EXISTS:
                if mutex:
                    kernel32.CloseHandle(mutex)
                return False
            _SINGLE_INSTANCE_MUTEX = mutex
        except Exception:
            pass

    # 2. Kiểm tra qua Socket Binding (localhost:65432)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        sock.listen(1)
        _SINGLE_INSTANCE_SOCKET = sock
    except (socket.error, OSError):
        # Nếu socket bind thất bại -> đã có tiến trình khác giữ port 65432
        if _SINGLE_INSTANCE_MUTEX and sys.platform.startswith("win"):
            try:
                ctypes.windll.kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
            except Exception:
                pass
            _SINGLE_INSTANCE_MUTEX = None
        return False

    _IS_ALREADY_ACQUIRED = True
    return True


# Kiểm tra nhanh tại entry point TRƯỚC KHI import PyQt6 hay Vosk
if __name__ == "__main__":
    if not ensure_single_instance():
        try:
            print("Tèo Assistant đang chạy ngầm!", flush=True)
        except Exception:
            pass
        sys.exit(0)

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QGradient,
    QIcon,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from actions import ActionExecutor
from brain import Brain
from stt_engine import SpeechToText
from ui_overlay import GlowOrbOverlay
from wake_word_engine import WakeWordEngine


def create_tray_icon() -> QIcon:
    """Tạo biểu tượng System Tray phong cách Tèo Orb rực rỡ dạng vector bằng QPainter."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Vẽ vòng tròn gradient màu xanh cyan - tím neon
    grad = QLinearGradient(0, 0, 64, 64)
    grad.setColorAt(0.0, QColor(0, 230, 255))     # Cyan
    grad.setColorAt(0.5, QColor(138, 43, 226))    # Violet
    grad.setColorAt(1.0, QColor(255, 0, 128))     # Deep Pink

    painter.setBrush(grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 56, 56)

    # Vẽ vòng viền phát quang
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QColor(255, 255, 255, 220))
    painter.drawEllipse(10, 10, 44, 44)

    # Chữ 'T' (Tèo) ở trung tâm
    font = QFont("Segoe UI", 22)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "T")

    painter.end()
    return QIcon(pixmap)


class CommandProcessingWorker(QThread):
    """
    Luồng phụ thực thi chuỗi hành động xử lý giọng nói sau khi đánh thức:
    Ghi âm STT -> Giải mã ý định Brain -> Thực thi ActionExecutor.
    Đảm bảo giao diện PyQt6 hoàn toàn không bị giật lag hay treo (freeze).
    """

    show_overlay_sig = pyqtSignal(str)
    update_status_sig = pyqtSignal(str)
    hide_overlay_sig = pyqtSignal()
    finished_sig = pyqtSignal()

    def __init__(
        self,
        stt: SpeechToText,
        brain: Brain,
        executor: ActionExecutor,
        wake_engine: WakeWordEngine,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.stt = stt
        self.brain = brain
        self.executor = executor
        self.wake_engine = wake_engine
        self.active_model_name = "teo"
        self._is_busy = False

    def trigger_command(self, model_name: str) -> None:
        """Kích hoạt chuỗi xử lý lệnh từ Wake Word."""
        if self._is_busy or self.isRunning():
            print("[Worker] Đang bận xử lý câu lệnh trước, bỏ qua lượt kích hoạt trùng lặp.")
            return

        self.active_model_name = model_name
        self.start()

    def run(self) -> None:
        """Tiến trình chạy trong luồng riêng biệt."""
        self._is_busy = True
        try:
            # 1. Phát tín hiệu hiện Overlay
            self.show_overlay_sig.emit("Tèo đang lắng nghe...")

            # 2. Phát âm thanh 'Bíp' xác nhận bằng winsound (1200Hz, 180ms)
            try:
                winsound.Beep(1200, 180)
            except Exception:
                pass

            # 3. Thu âm câu lệnh rảnh tay (tự động phát hiện im lặng ngắt sớm)
            print("\n[Tèo Assistant] 🎙️ Đang lắng nghe câu lệnh người dùng...")
            raw_audio = self.stt.record_wake_command(max_duration=4.5, silence_limit=0.9)

            if not raw_audio:
                self.update_status_sig.emit("Không nghe thấy lệnh...")
                time.sleep(0.7)
                return

            # 4. Nhận diện giọng nói (Google STT / Vosk)
            self.update_status_sig.emit("Đang nhận diện giọng nói...")
            user_text = self.stt.process_audio(raw_audio)

            if not user_text or not user_text.strip():
                self.update_status_sig.emit("Không nhận diện được giọng nói...")
                time.sleep(0.7)
                return

            print(f"[Tèo Assistant 👤] Lệnh nhận diện: \"{user_text}\"")
            self.update_status_sig.emit(f"\"{user_text}\"")

            # 5. Phân tích ngữ nghĩa qua Bộ não (Brain)
            t0 = time.time()
            actions = self.brain.process(user_text)
            elapsed = round(time.time() - t0, 2)
            print(f"[Tèo Assistant 🧠] Ý định giải mã xong ({elapsed}s): {actions}")

            # 6. Thực thi hành động qua ActionExecutor
            self.update_status_sig.emit("Đang thực thi lệnh...")
            self.executor.execute(actions)

            time.sleep(0.4)

        except Exception as exc:
            print(f"[Tèo Assistant ✗ Lỗi Worker]: {exc}")
            self.update_status_sig.emit("Đã xảy ra sự cố.")
            time.sleep(0.7)
        finally:
            # 7. Ẩn Overlay
            self.hide_overlay_sig.emit()
            time.sleep(0.3)

            # 8. Mở lại luồng lắng nghe Wake Word
            self.wake_engine.resume()
            self._is_busy = False
            self.finished_sig.emit()
            print("[Tèo Assistant] ✓ Đã hoàn thành lệnh. Sẵn sàng lắng nghe từ khóa tiếp theo.\n")


class TeoAssistantApp:
    """
    Lớp điều phối toàn diện ứng dụng Tèo Assistant:
    - Quản lý ứng dụng Qt.
    - Quản lý System Tray.
    - Kết nối tín hiệu giữa WakeWordEngine (Vosk), Worker và Overlay.
    """

    def __init__(self) -> None:
        # 0. Kiểm tra Single Instance (Chỉ cho phép 1 tiến trình duy nhất)
        if not ensure_single_instance():
            try:
                print("Tèo Assistant đang chạy ngầm!", flush=True)
            except Exception:
                pass
            sys.exit(0)

        # 1. Khởi tạo QApplication
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # Giữ app chạy nền khi đóng overlay

        print("\n" + "=" * 68)
        print("         KHỞI ĐỘNG TÈO ASSISTANT (WAKE WORD VOSK & TRAY OVERLAY)")
        print("=" * 68)

        # 2. Khởi tạo Giao diện Overlay
        print("[Tèo] [1/4] Đang khởi tạo giao diện Glow Orb Overlay...")
        self.overlay = GlowOrbOverlay(size=300)

        # 3. Khởi tạo các module bộ não và hành động
        print("[Tèo] [2/4] Đang khởi tạo Bộ nhận diện STT, Brain và ActionExecutor...")
        self.stt = SpeechToText()
        self.brain = Brain()
        self.executor = ActionExecutor()

        # 4. Khởi tạo Wake Word Engine bằng Vosk tiếng Việt
        print("[Tèo] [3/4] Đang khởi tạo Wake Word Engine Vosk ('Hey Tèo')...")
        self.wake_engine = WakeWordEngine(
            wake_keyword="hey tèo",
            on_detected=self._on_wake_word_triggered,
        )

        # 5. Khởi tạo Worker xử lý giọng nói (QThread)
        print("[Tèo] [4/4] Đang kết nối luồng xử lý giọng nói CommandProcessingWorker...")
        self.worker = CommandProcessingWorker(
            stt=self.stt,
            brain=self.brain,
            executor=self.executor,
            wake_engine=self.wake_engine,
        )

        # Kết nối tín hiệu từ Worker sang Overlay an toàn đa luồng
        self.worker.show_overlay_sig.connect(self.overlay.show_overlay)
        self.worker.update_status_sig.connect(self.overlay.set_status)
        self.worker.hide_overlay_sig.connect(self.overlay.hide_overlay)

        # 6. Cấu hình Khay hệ thống (System Tray Icon)
        self._setup_system_tray()

    def _setup_system_tray(self) -> None:
        """Thiết lập biểu tượng và menu ngữ cảnh cho Khay hệ thống Windows."""
        self.tray_icon = QSystemTrayIcon(create_tray_icon(), self.app)
        self.tray_icon.setToolTip("Tèo Assistant - Sẵn sàng (Nói 'Tèo ơi' hoặc 'Ê Tèo')")

        menu = QMenu()

        # Tiêu đề thông tin
        title_action = QAction("Tèo Assistant (Đang hoạt động)", menu)
        title_action.setEnabled(False)
        menu.addAction(title_action)
        menu.addSeparator()

        # Bật/Tắt Lắng nghe Wake Word
        self.toggle_wake_action = QAction("Lắng nghe Wake Word (Tèo)", menu)
        self.toggle_wake_action.setCheckable(True)
        self.toggle_wake_action.setChecked(True)
        self.toggle_wake_action.triggered.connect(self._toggle_wake_word)
        menu.addAction(self.toggle_wake_action)

        # Kiểm tra thử nghiệm Overlay
        test_overlay_action = QAction("Xem thử Overlay (3s)", menu)
        test_overlay_action.triggered.connect(self._test_show_overlay)
        menu.addAction(test_overlay_action)

        # Thông tin mô hình
        model_info_action = QAction("Từ khóa: 'Tèo' (Vosk Offline)", menu)
        model_info_action.setEnabled(False)
        menu.addAction(model_info_action)

        menu.addSeparator()

        # Nút Thoát
        exit_action = QAction("Thoát", menu)
        exit_action.triggered.connect(self.quit)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

        # Thông báo quả bóng (Notification Balloon) chào mừng
        self.tray_icon.showMessage(
            "Tèo Assistant",
            "Đã khởi động ngầm trên khay hệ thống.\nHãy gọi 'Tèo ơi' hoặc 'Ê Tèo' để ra lệnh!",
            QSystemTrayIcon.MessageIcon.Information,
            3500,
        )

    def _on_wake_word_triggered(self, model_name: str, score: float) -> None:
        """Hàm callback được gọi từ luồng Vosk Wake Word khi phát hiện từ khóa."""
        print(f"\n[App] 🔔 Nhận tín hiệu Wake Word: '{model_name}' -> Kích hoạt Worker!")
        self.worker.trigger_command(model_name)

    def _toggle_wake_word(self, checked: bool) -> None:
        """Bật hoặc tắt luồng lắng nghe từ khóa từ menu Tray."""
        if checked:
            self.wake_engine.resume()
            print("[App] Đã bật lại tính năng lắng nghe Wake Word.")
        else:
            self.wake_engine.pause()
            print("[App] Đã tạm dừng tính năng lắng nghe Wake Word.")

    def _test_show_overlay(self) -> None:
        """Hiển thị overlay thử nghiệm trong 3 giây."""
        self.overlay.show_overlay("Tèo đang thử nghiệm...")
        QTimer.singleShot(3000, self.overlay.hide_overlay)

    def start(self) -> None:
        """Bắt đầu chạy ứng dụng."""
        # Khởi động luồng WakeWordEngine
        self.wake_engine.start()

        print("\n" + "=" * 68)
        print("✓ TÈO ASSISTANT ĐÃ HOẠT ĐỘNG HOÀN TOÀN TRÊN KHAY HỆ THỐNG!")
        print("• Hãy nói vào micro: 'Hey Tèo', 'Tèo ơi', 'Ê Tèo' hoặc 'Chào Tèo'")
        print("• Nhấn chuột phải vào icon ở góc màn hình (System Tray) để tùy chọn.")
        print("• Nhấn Ctrl + C trên terminal để đóng chương trình.")
        print("=" * 68 + "\n")

        # Chạy vòng lặp sự kiện chính của Qt (Main Thread)
        try:
            sys.exit(self.app.exec())
        except KeyboardInterrupt:
            self.quit()

    def quit(self) -> None:
        """Đóng an toàn toàn bộ ứng dụng và các tiến trình nền."""
        print("\n[App] Đang đóng Tèo Assistant...")
        try:
            self.wake_engine.stop()
        except Exception:
            pass

        try:
            if self.worker.isRunning():
                self.worker.quit()
                self.worker.wait(1000)
        except Exception:
            pass

        try:
            self.overlay.hide_overlay()
        except Exception:
            pass

        try:
            self.tray_icon.hide()
        except Exception:
            pass

        print("[App] ✓ Đã dừng toàn bộ luồng. Tạm biệt bạn!")

        # Giải phóng Mutex và Socket Single Instance
        global _SINGLE_INSTANCE_MUTEX, _SINGLE_INSTANCE_SOCKET, _IS_ALREADY_ACQUIRED
        if _SINGLE_INSTANCE_SOCKET:
            try:
                _SINGLE_INSTANCE_SOCKET.close()
            except Exception:
                pass
            _SINGLE_INSTANCE_SOCKET = None

        if _SINGLE_INSTANCE_MUTEX and sys.platform.startswith("win"):
            try:
                ctypes.windll.kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
            except Exception:
                pass
            _SINGLE_INSTANCE_MUTEX = None

        _IS_ALREADY_ACQUIRED = False

        self.app.quit()


# Bí danh tương thích ngược
EchoAssistantApp = TeoAssistantApp


if __name__ == "__main__":
    if not ensure_single_instance():
        try:
            print("Tèo Assistant đang chạy ngầm!", flush=True)
        except Exception:
            pass
        sys.exit(0)
    app_runner = TeoAssistantApp()
    app_runner.start()

"""
Test Suite: test_phase5_wake_overlay.py
Mục đích: Kiểm tra toàn diện Phase 5.1 của Tèo Assistant:
1. Giao diện Glow Orb Overlay (PyQt6 trong suốt, animation, căn giữa màn hình).
2. Module Wake Word Engine (Vosk Offline tiếng Việt với từ khóa "Tèo", luồng nền, pause/resume).
3. Luồng hoạt động tích hợp đa luồng (Signals, Worker, System Tray, Bíp).
"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import numpy as np

# Đảm bảo in tiếng Việt chuẩn trên Windows console
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from app_tray import CommandProcessingWorker, create_tray_icon
from ui_overlay import GlowOrbOverlay
from wake_word_engine import WakeWordEngine


def get_or_create_qapp():
    """Lấy hoặc tạo mới QApplication instance cho môi trường test."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_ui_overlay():
    print("\n" + "=" * 65)
    print("TEST 1: GIAO DIỆN GLOW ORB OVERLAY (PyQt6)")
    print("=" * 65)

    app = get_or_create_qapp()
    overlay = GlowOrbOverlay(size=300)

    # 1. Kiểm tra các cờ cửa sổ (Window Flags)
    flags = overlay.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint, "Cửa sổ phải là FramelessWindowHint"
    assert flags & Qt.WindowType.WindowStaysOnTopHint, "Cửa sổ phải là WindowStaysOnTopHint"
    assert flags & Qt.WindowType.Tool, "Cửa sổ phải là Tool để không chiếm Taskbar"
    print("  [✓] Cửa sổ được cấu hình chuẩn: Frameless, Always on Top, Tool window")

    # 2. Kiểm tra thuộc tính trong suốt
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), "Cửa sổ phải có nền trong suốt (WA_TranslucentBackground)"
    print("  [✓] Nền trong suốt (WA_TranslucentBackground) được kích hoạt")

    # 3. Kiểm tra kích thước và vị trí căn giữa
    assert overlay.width() == 300 and overlay.height() == 300
    overlay.center_on_screen()
    assert overlay.x() >= 0 and overlay.y() >= 0
    print(f"  [✓] Vị trí căn giữa màn hình: x={overlay.x()}, y={overlay.y()}, kích thước={overlay.width()}x{overlay.height()}")

    # 4. Kiểm tra show_overlay và hide_overlay
    overlay.show_overlay("Tèo đang lắng nghe...")
    app.processEvents()
    assert overlay.status_text == "Tèo đang lắng nghe..."
    assert overlay._anim_timer.isActive(), "Timer animation phải đang chạy khi hiển thị"
    print("  [✓] Hàm show_overlay(): Đã hiển thị và kích hoạt animation timer")

    # 5. Cập nhật status text
    overlay.set_status("Đang giải mã ý định...")
    app.processEvents()
    assert overlay.status_text == "Đang giải mã ý định..."
    print("  [✓] Hàm set_status(): Cập nhật dòng trạng thái mượt mà")

    # 6. Kiểm tra hide_overlay
    overlay.hide_overlay()
    app.processEvents()
    assert not overlay._anim_timer.isActive(), "Timer animation phải dừng khi ẩn overlay"
    print("  [✓] Hàm hide_overlay(): Đã dừng animation và ẩn giao diện")

    print("=> TEST 1 (ui_overlay.py) PASSED 100%!")


def test_wake_word_engine():
    print("\n" + "=" * 65)
    print("TEST 2: MODULE WAKE WORD ENGINE (Vosk Offline 'Hey Tèo' với Grammar)")
    print("=" * 65)

    triggered_data = []

    def on_wake(name, score):
        triggered_data.append((name, score))

    engine = WakeWordEngine(
        wake_keyword="hey tèo",
        threshold=0.5,
        on_detected=on_wake,
    )

    # 1. Kiểm tra mô hình Vosk nạp thành công và Grammar được kích hoạt
    assert engine.model is not None, "Mô hình Vosk phải được nạp thành công"
    assert engine.recognizer is not None, "KaldiRecognizer phải được khởi tạo"
    assert "hey tèo" in engine.grammar_words, "Grammar phải chứa 'hey tèo'"
    assert "[unk]" in engine.grammar_words, "Grammar phải chứa '[unk]'"
    print(f"  [✓] Đã nạp thành công mô hình Vosk từ: {engine.model_path}")
    print(f"  [✓] Đã kích hoạt Vosk Grammar: {engine.grammar_words}")

    # 2. Kiểm tra Regex CHỈ nhận diện duy nhất 'Hey Tèo' và loại bỏ toàn bộ biến thể khác (v1.3.1)
    test_cases = [
        ("hey tèo", True),
        ("hey tèo mở chrome", True),
        ("hey tèo ơi", True),
        # Loại bỏ các biến thể theo yêu cầu v1.3.1:
        ("tèo ơi", False),
        ("ê tèo", False),
        ("này tèo", False),
        ("chào tèo", False),
        ("tèo ơi mở youtube", False),
        ("hê tèo", False),
        ("tèo", False),
        ("teo", False),
        ("a lô", False),
        ("alo", False),
        ("hê lô", False),
        ("hello", False),
        ("bánh bèo", False),
        ("ăn kẹo kéo", False),
        ("theo như lời kể", False),
        ("[unk]", False),
    ]
    for text, expected in test_cases:
        res = engine._check_text_for_wake_word(text)
        assert res == expected, f"Regex sai cho '{text}': kỳ vọng {expected}, thực tế {res}"
    print("  [✓] Bộ lọc Regex Wake Word: CHỈ nhận diện duy nhất 'Hey Tèo' & chặn đứng toàn bộ biến thể khác!")

    # 3. Kiểm tra trạng thái start, pause, resume, stop
    engine.start()
    assert engine.is_listening() is True, "Engine phải ở trạng thái lắng nghe sau khi start()"
    print("  [✓] engine.start(): Luồng lắng nghe đã khởi động thành công")

    engine.pause()
    assert engine.is_listening() is False, "is_listening() phải là False khi pause"
    assert engine._paused is True
    print("  [✓] engine.pause(): Đã tạm dừng lắng nghe, giải phóng micro")

    engine.resume()
    assert engine.is_listening() is True, "is_listening() phải là True khi resume"
    assert engine._paused is False
    print("  [✓] engine.resume(): Đã kích hoạt lắng nghe trở lại")

    engine.stop()
    assert engine._running is False
    print("  [✓] engine.stop(): Đã dừng luồng sạch sẽ")

    print("=> TEST 2 (wake_word_engine.py) PASSED 100%!")


def test_command_pipeline_worker():
    print("\n" + "=" * 65)
    print("TEST 3: LUỒNG HOẠT ĐỘNG PIPELINE (Worker, Signals, Audio, Brain, Action)")
    print("=" * 65)

    app = get_or_create_qapp()

    # Tạo Mock cho các thành phần để test luồng hoàn chỉnh
    mock_stt = MagicMock()
    mock_stt.record_wake_command.return_value = b"\x00" * 3200
    mock_stt.process_audio.return_value = "mở chrome"

    mock_brain = MagicMock()
    mock_brain.process.return_value = [{"action": "open_app", "name": "chrome"}]

    mock_executor = MagicMock()
    mock_wake_engine = MagicMock()

    worker = CommandProcessingWorker(
        stt=mock_stt,
        brain=mock_brain,
        executor=mock_executor,
        wake_engine=mock_wake_engine,
    )

    signals_received = []
    worker.show_overlay_sig.connect(lambda msg: signals_received.append(("show", msg)))
    worker.update_status_sig.connect(lambda msg: signals_received.append(("update", msg)))
    worker.hide_overlay_sig.connect(lambda: signals_received.append(("hide", None)))

    # Giả lập phát tiếng Bíp winsound để test nhanh không phụ thuộc âm thanh
    with patch("winsound.Beep") as mock_beep:
        # Chạy pipeline xử lý
        worker.run()

        # 1. Kiểm tra tiếng bíp
        assert mock_beep.call_count == 1
        mock_beep.assert_called_with(1200, 180)
        print("  [✓] Âm thanh: Đã phát tiếng 'Bíp' xác nhận (1200Hz, 180ms) qua winsound")

    # 2. Kiểm tra tín hiệu Overlay
    action_types = [s[0] for s in signals_received]
    assert "show" in action_types, "Phải gửi tín hiệu show overlay"
    assert "update" in action_types, "Phải gửi tín hiệu update status"
    assert "hide" in action_types, "Phải gửi tín hiệu hide overlay"
    print(f"  [✓] Tín hiệu giao diện: {signals_received}")

    # 3. Kiểm tra các bước thực thi
    mock_stt.record_wake_command.assert_called_once()
    mock_stt.process_audio.assert_called_once()
    mock_brain.process.assert_called_with("mở chrome")
    mock_executor.execute.assert_called_with([{"action": "open_app", "name": "chrome"}])
    mock_wake_engine.resume.assert_called_once()

    print("  [✓] Pipeline: record_wake_command -> process_audio -> brain.process -> executor.execute -> wake_engine.resume")
    print("=> TEST 3 (Pipeline & Multithreading) PASSED 100%!")


def test_system_tray_icon():
    print("\n" + "=" * 65, flush=True)
    print("TEST 4: TẠO KHAY HỆ THỐNG SYSTEM TRAY ICON", flush=True)
    print("=" * 65, flush=True)

    print("  [Step 4.1] Lấy QApplication instance...", flush=True)
    app = get_or_create_qapp()
    print("  [Step 4.2] Tạo QIcon từ vector QPainter...", flush=True)
    icon = create_tray_icon()
    print(f"  [Step 4.3] Kiểm tra QIcon isNull: {icon.isNull()}...", flush=True)
    assert not icon.isNull(), "Biểu tượng System Tray không được rỗng"
    print("  [✓] Biểu tượng System Tray phong cách Tèo Orb vector được tạo thành công", flush=True)
    print("=> TEST 4 (System Tray Icon) PASSED 100%!", flush=True)


if __name__ == "__main__":
    print("\n" + "#" * 68)
    print("  BẮT ĐẦU CHẠY KIỂM THỬ PHASE 5.1: OVERLAY & WAKE WORD (TÈO ASSISTANT)")
    print("#" * 68)

    test_ui_overlay()
    test_wake_word_engine()
    test_command_pipeline_worker()
    test_system_tray_icon()

    print("\n" + "#" * 68)
    print("  ✓ TẤT CẢ 4/4 BỘ TEST PHASE 5.1 ĐÃ VƯỢT QUA XUẤT SẮC!")
    print("#" * 68 + "\n")

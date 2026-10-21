"""
Module: wake_word_engine.py
Mục đích: Bộ phát hiện từ khóa đánh thức (Wake Word Engine) cho Echo Assistant.
Chức năng:
    - Sử dụng thư viện openwakeword với runtime ONNX (chạy hoàn toàn cục bộ, miễn phí, không cần GPU).
    - Tải các mô hình từ khóa có sẵn: 'alexa', 'hey_jarvis' (dễ dàng bổ sung model 'Hey Echo' sau khi train).
    - Thu âm liên tục từ micro qua sounddevice (16kHz, 16-bit PCM, blocksize 1280 mẫu = 80ms).
    - Chạy trên luồng nền (background thread), hỗ trợ tạm dừng (pause) và kích hoạt lại (resume) 
      để giải phóng micro cho bộ thu âm STT xử lý câu lệnh, chống xung đột PortAudio.
    - Kích hoạt callback khi điểm số dự đoán vượt ngưỡng (threshold >= 0.5).
"""

import os
import threading
import time
from typing import Callable, List, Optional

import numpy as np
import sounddevice as sd
from openwakeword.model import Model


class WakeWordEngine:
    """
    Lớp lắng nghe và phát hiện Wake Word liên tục trên một luồng riêng biệt.
    """

    SAMPLE_RATE: int = 16000
    CHUNK_SIZE: int = 1280  # 80ms mỗi chunk (chuẩn đầu vào của openwakeword)

    def __init__(
        self,
        models: Optional[List[str]] = None,
        threshold: float = 0.5,
        on_detected: Optional[Callable[[str, float], None]] = None,
        cooldown_sec: float = 1.5,
    ) -> None:
        """
        Khởi tạo WakeWordEngine.

        Args:
            models: Danh sách tên hoặc đường dẫn mô hình (mặc định: ['alexa', 'hey_jarvis']).
            threshold: Ngưỡng tự tin phát hiện từ khóa (0.0 đến 1.0, mặc định: 0.5).
            on_detected: Hàm callback gọi khi phát hiện Wake Word: callback(model_name, score).
            cooldown_sec: Thời gian chờ tối thiểu giữa 2 lần kích hoạt liên tiếp (giây).
        """
        self.threshold = threshold
        self.on_detected = on_detected
        self.cooldown_sec = cooldown_sec

        from utils import resource_path

        if models is None:
            self.model_names = ["alexa", "hey_jarvis"]
        else:
            resolved_models = []
            for m in models:
                res_m = resource_path(m)
                if os.path.exists(res_m):
                    resolved_models.append(res_m)
                else:
                    resolved_models.append(m)
            self.model_names = resolved_models

        print(f"[WakeWord] Đang nạp mô hình Wake Word {self.model_names} qua ONNX...")
        self.oww_model = Model(
            wakeword_models=self.model_names,
            inference_framework="onnx"
        )
        print(f"[WakeWord] ✓ Đã nạp thành công mô hình: {list(self.oww_model.models.keys())}")

        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_trigger_time = 0.0

    def start(self) -> None:
        """Bắt đầu luồng lắng nghe Wake Word."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._paused = False
            self._thread = threading.Thread(
                target=self._listen_loop,
                name="WakeWordListenerThread",
                daemon=True,
            )
            self._thread.start()
            print("[WakeWord] 🎙️ Đã bắt đầu lắng nghe từ khóa đánh thức (Nói 'Alexa' hoặc 'Hey Jarvis')...")

    def stop(self) -> None:
        """Dừng hoàn toàn luồng lắng nghe Wake Word."""
        with self._lock:
            self._running = False
            self._paused = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        print("[WakeWord] ⏹️ Đã dừng luồng lắng nghe Wake Word.")

    def pause(self) -> None:
        """
        Tạm dừng lắng nghe và giải phóng micro để STT thu âm lệnh.
        Giúp tránh xung đột thiết bị âm thanh giữa WakeWord và STT.
        """
        with self._lock:
            self._paused = True
        print("[WakeWord] ⏸️ Tạm dừng lắng nghe Wake Word (nhường micro cho STT).")

    def resume(self) -> None:
        """Kích hoạt lại việc lắng nghe Wake Word sau khi thực thi lệnh xong."""
        # Reset prediction buffer để không bị kích hoạt nhầm bởi âm thanh cũ
        try:
            self.oww_model.reset()
        except Exception:
            pass
        with self._lock:
            self._last_trigger_time = time.time()  # Thêm cooldown nhỏ sau khi resume
            self._paused = False
        print("[WakeWord] ▶️ Tiếp tục lắng nghe từ khóa đánh thức...")

    def is_listening(self) -> bool:
        """Kiểm tra xem engine có đang trong trạng thái lắng nghe tích cực không."""
        return self._running and not self._paused

    def _listen_loop(self) -> None:
        """Vòng lặp thu âm và phân tích âm thanh liên tục."""
        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            stream = None
            try:
                # Mở stream sounddevice với blocksize = 1280
                stream = sd.InputStream(
                    samplerate=self.SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=self.CHUNK_SIZE,
                )
                stream.start()

                while self._running and not self._paused:
                    data, overflowed = stream.read(self.CHUNK_SIZE)
                    if overflowed:
                        pass

                    audio_chunk = np.frombuffer(data, dtype=np.int16)

                    # Đưa chunk vào mô hình openwakeword
                    prediction = self.oww_model.predict(audio_chunk)

                    now = time.time()
                    if (now - self._last_trigger_time) < self.cooldown_sec:
                        continue

                    # Kiểm tra xem có mô hình nào đạt ngưỡng tự tin không
                    for name, score in prediction.items():
                        if score >= self.threshold:
                            self._last_trigger_time = now
                            print(f"\n[WakeWord 🔔] ĐÃ PHÁT HIỆN TỪ KHÓA: '{name}' (Độ tin cậy: {score:.2f})!")

                            # Tự động tạm dừng trước khi gọi callback để nhường micro
                            self.pause()

                            if self.on_detected:
                                try:
                                    self.on_detected(name, float(score))
                                except Exception as cb_exc:
                                    print(f"[WakeWord ✗ Lỗi Callback]: {cb_exc}")
                            break

            except Exception as exc:
                if self._running and not self._paused:
                    print(f"[WakeWord Cảnh báo Stream Micro]: {exc}. Đang thử kết nối lại sau 1s...")
                    time.sleep(1.0)
            finally:
                if stream is not None:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass


# Khối chạy thử nghiệm độc lập
if __name__ == "__main__":
    import winsound

    def handle_wake_word(model_name: str, score: float) -> None:
        print(f"\n>>> [TEST CALLBACK] Từ khóa '{model_name}' kích hoạt! Phát tiếng Bíp...")
        winsound.Beep(1200, 200)
        time.sleep(2.0)
        print(">>> [TEST CALLBACK] Giả lập thực thi xong. Tiếp tục lắng nghe...")
        engine.resume()

    print("=" * 65)
    print("  KIỂM TRA MODULE WAKE WORD ENGINE (ECHO ASSISTANT)")
    print("  • Hãy nói vào Micro: 'Alexa' hoặc 'Hey Jarvis'")
    print("  • Nhấn Ctrl + C để dừng.")
    print("=" * 65)

    engine = WakeWordEngine(on_detected=handle_wake_word)
    engine.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nĐang dừng WakeWordEngine...")
        engine.stop()
        print("Đã thoát kiểm tra.")

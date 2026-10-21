"""
Module: wake_word_engine.py
Mục đích: Bộ phát hiện từ khóa đánh thức (Wake Word Engine) cho Tèo Assistant.
Chức năng:
    - Sử dụng mô hình Vosk Offline tiếng Việt (chạy hoàn toàn cục bộ, miễn phí, không tốn GPU).
    - Cấu hình Vosk Grammar (giới hạn từ vựng) giúp loại bỏ tạp âm và nhận diện cực nhạy.
    - Lắng nghe liên tục từ microphone qua sounddevice.RawInputStream (16kHz, 16-bit PCM Mono).
    - Nhận diện từ khóa đánh thức: "Hey Tèo", "Tèo ơi", "Ê Tèo", "Hê Tèo", "Này Tèo", "Chào Tèo", "Tèo".
    - In log debug chi tiết trong thời gian thực: mọi câu nghe được và thông báo khi khớp từ khóa.
    - Cơ chế nhường Micro an toàn đa luồng:
        + Hỗ trợ tạm dừng (pause): Đóng stream micro ngay lập tức để STT (Google STT / Vosk) thu âm lệnh.
        + Hỗ trợ tiếp tục (resume): Mở lại stream micro và reset recognizer khi lệnh thực thi xong.
    - Kích hoạt callback on_detected("teo", 1.0) tức thì khi phát hiện từ khóa.
"""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

import sounddevice as sd
import vosk

from utils import resource_path

# Đảm bảo in tiếng Việt chuẩn trên Windows console
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class WakeWordEngine:
    """
    Lớp lắng nghe và phát hiện Wake Word 'Hey Tèo' / 'Tèo' liên tục bằng mô hình Vosk tiếng Việt.
    Tối ưu hóa độ nhạy và chống nhiễu bằng Vosk Grammar.
    """

    SAMPLE_RATE: int = 16000
    BLOCK_SIZE: int = 4000  # 250ms mỗi block (nhanh, mượt, nhẹ CPU)

    # 1. Regex nhận diện các biến thể của từ khóa "Hey Tèo"
    # Phân biệt ranh giới từ để tránh khớp nhầm các từ có vần như 'bánh bèo' hay 'theo'
    DEFAULT_WAKE_REGEX = re.compile(
        r"\b(hey tèo|hê tèo|này tèo|chào tèo|ê tèo|tèo ơi|tèo|teo)\b",
        re.IGNORECASE,
    )

    # 2. Vosk Grammar (Giới hạn từ vựng) - Ngăn Vosk bị loạn bởi tiếng ồn môi trường
    DEFAULT_GRAMMAR_WORDS: List[str] = [
        "tèo",
        "tèo ơi",
        "ê tèo",
        "hey tèo",
        "hê tèo",
        "này tèo",
        "chào tèo",
        "teo",
        "[unk]",
    ]

    def __init__(
        self,
        vosk_model_path: Optional[str] = None,
        wake_keyword: str = "hey tèo",
        threshold: float = 0.5,
        on_detected: Optional[Callable[[str, float], None]] = None,
        cooldown_sec: float = 1.5,
        grammar_words: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        """
        Khởi tạo WakeWordEngine bằng Vosk tiếng Việt với Grammar tối ưu.

        Args:
            vosk_model_path: Đường dẫn tới mô hình Vosk (mặc định nạp qua resource_path('model')).
            wake_keyword: Tên từ khóa đánh thức hiển thị (mặc định: 'hey tèo').
            threshold: Tham số tương thích ngược.
            on_detected: Hàm callback gọi khi phát hiện Wake Word: callback(keyword, score).
            cooldown_sec: Thời gian chờ tối thiểu giữa 2 lần kích hoạt liên tiếp (giây).
            grammar_words: Danh sách từ vựng cho Vosk Grammar.
        """
        self.wake_keyword = wake_keyword.lower()
        self.threshold = threshold
        self.on_detected = on_detected
        self.cooldown_sec = cooldown_sec
        self.grammar_words = grammar_words or self.DEFAULT_GRAMMAR_WORDS

        vosk.SetLogLevel(-1)  # Tắt log Kaldi rườm rà

        # Xác định đường dẫn mô hình Vosk
        cache_dir = Path(os.path.expanduser("~/.cache/vosk/vosk-model-small-vn-0.4"))
        local_dir = Path(resource_path("model"))

        if vosk_model_path and Path(vosk_model_path).exists():
            self.model_path = str(vosk_model_path)
        elif local_dir.exists():
            self.model_path = str(local_dir)
        elif cache_dir.exists():
            self.model_path = str(cache_dir)
        else:
            self.model_path = "model"

        print(f"[WakeWord] Đang nạp mô hình Vosk tiếng Việt từ '{self.model_path}'...")
        try:
            self.model = vosk.Model(self.model_path)

            # Cấu hình Vosk Grammar (JSON array string với ensure_ascii=False)
            grammar_json = json.dumps(self.grammar_words, ensure_ascii=False)
            try:
                self.recognizer = vosk.KaldiRecognizer(
                    self.model,
                    float(self.SAMPLE_RATE),
                    grammar_json,
                )
                print(f"[WakeWord] ✓ Đã kích hoạt Vosk Grammar: {self.grammar_words}")
            except Exception as g_err:
                print(f"[WakeWord Cảnh báo] Không thể nạp Grammar ({g_err}), fallback về chế độ tiêu chuẩn...")
                self.recognizer = vosk.KaldiRecognizer(self.model, float(self.SAMPLE_RATE))

            print(f"[WakeWord] ✓ Sẵn sàng nhận diện từ khóa: '{self.wake_keyword}' ('Hey Tèo', 'Tèo ơi', 'Ê Tèo'...)")
        except Exception as exc:
            print(f"[WakeWord Cảnh báo] Không thể khởi tạo Vosk Model: {exc}")
            self.model = None
            self.recognizer = None

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
                name="VoskWakeWordThread",
                daemon=True,
            )
            self._thread.start()
            print(f"[WakeWord] 🎙️ Đã bắt đầu lắng nghe từ khóa '{self.wake_keyword}' (Ví dụ: 'Hey Tèo', 'Tèo ơi', 'Ê Tèo')...")

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
        if self.recognizer:
            try:
                self.recognizer.Reset()
            except Exception:
                pass
        with self._lock:
            self._last_trigger_time = time.time()  # Tránh trigger nhầm ngay lập tức
            self._paused = False
        print(f"[WakeWord] ▶️ Tiếp tục lắng nghe từ khóa '{self.wake_keyword}'...")

    def is_listening(self) -> bool:
        """Kiểm tra xem engine có đang trong trạng thái lắng nghe tích cực không."""
        return self._running and not self._paused

    def _check_text_for_wake_word(self, raw_text: str) -> bool:
        """Kiểm tra chuỗi văn bản nhận diện có khớp với từ khóa đánh thức hay không."""
        if not raw_text:
            return False
        return bool(self.DEFAULT_WAKE_REGEX.search(raw_text))

    def _listen_loop(self) -> None:
        """Vòng lặp thu âm micro và nhận diện từ khóa liên tục bằng Vosk."""
        if not self.model or not self.recognizer:
            print("[WakeWord Lỗi] Mô hình Vosk chưa sẵn sàng, luồng dừng.")
            return

        while self._running:
            if self._paused:
                time.sleep(0.05)
                continue

            stream = None
            try:
                stream = sd.RawInputStream(
                    samplerate=self.SAMPLE_RATE,
                    blocksize=self.BLOCK_SIZE,
                    dtype="int16",
                    channels=1,
                )
                stream.start()

                last_debug_text = ""

                while self._running and not self._paused:
                    data, overflowed = stream.read(self.BLOCK_SIZE)
                    if not data:
                        continue

                    matched = False
                    detected_text = ""

                    # 1. Đưa audio data vào Vosk
                    if self.recognizer.AcceptWaveform(bytes(data)):
                        try:
                            res = json.loads(self.recognizer.Result())
                            text = res.get("text", "").strip()
                            if text:
                                # In log mọi câu Vosk nghe được
                                print(f"[Vosk Debug] Đang nghe: {text}", flush=True)
                                if self._check_text_for_wake_word(text):
                                    print("[Vosk Debug] => ĐÃ KHỚP TỪ KHÓA! Kích hoạt...", flush=True)
                                    matched = True
                                    detected_text = text
                        except Exception:
                            pass
                    else:
                        # 2. Kiểm tra kết quả tức thì (Partial Result) để phản hồi siêu tốc
                        try:
                            pres = json.loads(self.recognizer.PartialResult())
                            partial = pres.get("partial", "").strip()
                            if partial and partial != last_debug_text:
                                last_debug_text = partial
                                # In log kết quả tức thì khi người dùng đang nói
                                print(f"[Vosk Debug] Đang nghe: {partial}", flush=True)
                                if self._check_text_for_wake_word(partial):
                                    print("[Vosk Debug] => ĐÃ KHỚP TỪ KHÓA! Kích hoạt...", flush=True)
                                    matched = True
                                    detected_text = partial
                                    # Reset recognizer để không lặp lại từ khóa
                                    self.recognizer.Reset()
                            elif not partial:
                                last_debug_text = ""
                        except Exception:
                            pass

                    now = time.time()
                    if matched and (now - self._last_trigger_time) >= self.cooldown_sec:
                        self._last_trigger_time = now
                        print(f"\n[WakeWord 🔔] ĐÃ PHÁT HIỆN TỪ KHÓA: '{detected_text}' -> Kích hoạt Tèo Assistant!")

                        # Tạm dừng và nhường micro cho STT ngay lập tức
                        self.pause()

                        if self.on_detected:
                            try:
                                self.on_detected("teo", 1.0)
                            except Exception as cb_err:
                                print(f"[WakeWord Cảnh báo] Lỗi trong callback on_detected: {cb_err}")
                        break

            except Exception as exc:
                if self._running and not self._paused:
                    print(f"[WakeWord Lỗi Stream Audio]: {exc}")
                    time.sleep(0.3)
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
        print(f"\n>>> [TEST CALLBACK] Phát hiện '{model_name}'! Bíp...")
        winsound.Beep(1200, 200)
        time.sleep(1)
        engine.resume()

    engine = WakeWordEngine(
        wake_keyword="hey tèo",
        on_detected=handle_wake_word,
    )

    print("\n" + "=" * 60)
    print("--- BẮT ĐẦU CHẠY THỬ NGHIỆM VOSK WAKE WORD 'HEY TÈO' ---")
    print("=" * 60)
    print("Nói một trong các từ sau để kích hoạt:")
    print("  • 'Hey Tèo' (Khuyên dùng)")
    print("  • 'Tèo ơi'")
    print("  • 'Ê Tèo'")
    print("  • 'Hê Tèo'")
    print("  • 'Này Tèo'")
    print("  • 'Chào Tèo'")
    print("  • 'Tèo'")
    print("\nNhấn Ctrl+C để dừng thử nghiệm.\n")

    engine.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nĐang dừng...")
        engine.stop()

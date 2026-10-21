"""
Module: stt_engine.py
Mục đích: Module nhận diện giọng nói (STT) kiến trúc "Hybrid Tự Học" cho VoicePilot trên Windows.
Công nghệ:
    1. Push-to-Talk (Ctrl+Space): Thu âm trực tiếp từ Microphone khi người dùng nhấn giữ phím,
       dừng ngay lập tức khi nhả phím -> Loại bỏ hoàn toàn độ trễ phát hiện khoảng lặng (VAD latency).
    2. Google STT (Online): Nhận diện độ chính xác cao, trả về kết quả NGAY LẬP TỨC (<1s) cho Bộ não xử lý.
    3. Vosk Offline STT & Threading: Chạy NGẦM Vosk bằng thư viện `threading` trên cùng đoạn audio.
       Khi Vosk trả về kết quả, tự động gọi `auto_learn(vosk_text, google_text)` để lưu vào `offline_learning.json`.
    4. Offline Fallback: Khi mất mạng, tự động đưa audio cho Vosk xử lý và áp dụng từ điển tự học.
"""

import json
import os
import queue
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

# 1. Thư viện SpeechRecognition (Google STT)
HAS_SPEECH_RECOGNITION = False
try:
    import speech_recognition as sr
    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False

# 2. Thư viện Vosk (Offline STT)
HAS_VOSK = False
try:
    import vosk
    HAS_VOSK = True
except ImportError:
    HAS_VOSK = False

# 3. Thư viện keyboard (Push-to-Talk Ctrl+Space)
HAS_KEYBOARD = False
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

# 4. Module Tự học Ngoại tuyến (auto_learn.py)
from auto_learn import apply_offline_learning, auto_learn


class SpeechToText:
    """
    Lớp xử lý Speech-to-Text Hybrid Tự Học:
    - Thu âm Push-to-Talk (Ctrl+Space).
    - Online: Trả về kết quả Google STT tức thì; chạy ngầm Vosk trong luồng riêng để tự học.
    - Offline: Nhận diện bằng Vosk và áp dụng từ điển offline_learning.json.
    """

    CHUNK_SIZE: int = 1024               # Chunk size lớn hơn (1024 hoặc 2048) để thu âm mượt hơn, tránh vấp âm
    SAMPLE_RATE: int = 16000             # Chuẩn 16kHz cho Google STT và Vosk
    CHANNELS: int = 1                    # Mono
    MIN_AUDIO_DURATION_SEC: float = 0.3  # Bỏ qua nếu dưới 0.3s (chống chạm phím nhầm)

    def __init__(
        self,
        language: str = "vi-VN",
        vosk_model_path: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Khởi tạo STT Engine Hybrid.

        Args:
            language: Mã ngôn ngữ Google STT (mặc định 'vi-VN').
            vosk_model_path: Đường dẫn thư mục mô hình Vosk tùy chọn.
            **kwargs: Giữ tương thích ngược với các tham số cũ (model_size, compute_type...).
        """
        self.language = language
        self.samples_per_frame = self.CHUNK_SIZE  # Khởi tạo chunk size 1024 cho PortAudio/sounddevice mượt hơn

        # Khởi tạo Recognizer của SpeechRecognition cho Google STT
        if HAS_SPEECH_RECOGNITION:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = False
        else:
            self.recognizer = None
            print("[STT Cảnh báo] Chưa cài đặt 'speech_recognition'! Cần pip install SpeechRecognition")

        # Khởi tạo mô hình Vosk Offline (Pre-load sẵn vào RAM)
        self.vosk_model = None
        if HAS_VOSK:
            try:
                vosk.SetLogLevel(-1)  # Tắt log Kaldi rườm rà
                from utils import resource_path
                cache_dir = Path(os.path.expanduser("~/.cache/vosk/vosk-model-small-vn-0.4"))
                local_dir = Path(resource_path("model"))

                if vosk_model_path and Path(vosk_model_path).exists():
                    self.vosk_model = vosk.Model(str(vosk_model_path))
                elif local_dir.exists():
                    self.vosk_model = vosk.Model(str(local_dir))
                elif cache_dir.exists():
                    self.vosk_model = vosk.Model(str(cache_dir))
                else:
                    self.vosk_model = vosk.Model(lang="vn")

                print("[STT] ✓ Đã nạp thành công mô hình Vosk Offline tiếng Việt.")
            except Exception as exc:
                print(f"[STT Cảnh báo] Không thể khởi tạo mô hình Vosk: {exc}")
                self.vosk_model = None
        else:
            print("[STT Cảnh báo] Chưa cài đặt thư viện 'vosk'! Cần pip install vosk")

        if not HAS_KEYBOARD:
            print("[STT Cảnh báo] Chưa cài đặt thư viện 'keyboard'! Cần pip install keyboard")

    def check_microphone(self) -> dict:
        """Kiểm tra Microphone khả dụng trên Windows."""
        try:
            devices = sd.query_devices()
        except Exception as exc:
            raise RuntimeError(f"Không thể truy vấn thiết bị âm thanh: {exc}") from exc

        input_devices = [dev for dev in devices if dev.get("max_input_channels", 0) > 0]
        if not input_devices:
            raise RuntimeError(
                "Không tìm thấy Microphone nào trên hệ thống!\n"
                "Vui lòng kiểm tra quyền Microphone trong Windows Settings."
            )
        try:
            return sd.query_devices(kind="input")
        except Exception:
            return input_devices[0]

    def release_microphone(self) -> None:
        """Giải phóng luồng Micro để tránh nghẽn/kẹt."""
        try:
            sd.stop()
        except Exception:
            pass

    @staticmethod
    def is_online(host: str = "8.8.8.8", port: int = 53, timeout: float = 0.3) -> bool:
        """
        Kiểm tra kết nối Internet siêu nhanh (<50ms) bằng kết nối socket UDP/TCP tới DNS Google.
        """
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def is_push_to_talk_pressed() -> bool:
        """
        Kiểm tra xem tổ hợp phím Push-to-Talk (Ctrl + Space) có đang được nhấn giữ hay không.
        Hỗ trợ cả 'ctrl+space', left ctrl, right ctrl kết hợp space.
        """
        if not HAS_KEYBOARD:
            return False
        try:
            return (
                keyboard.is_pressed("ctrl+space")
                or (
                    (
                        keyboard.is_pressed("ctrl")
                        or keyboard.is_pressed("left ctrl")
                        or keyboard.is_pressed("right ctrl")
                    )
                    and keyboard.is_pressed("space")
                )
            )
        except Exception:
            return False

    def recognize_google(self, raw_audio: bytes) -> str:
        """
        Gửi audio cho Google STT để nhận diện giọng nói trực tuyến.
        Trả về chuỗi văn bản nhận diện được.
        """
        if not self.recognizer or not raw_audio:
            return ""

        audio_data = sr.AudioData(raw_audio, self.SAMPLE_RATE, 2)
        try:
            # Nhận diện với Google Speech Recognition API
            text = self.recognizer.recognize_google(audio_data, language=self.language)
            return text.strip() if text else ""
        except sr.UnknownValueError:
            # Không phát hiện giọng nói rõ ràng
            return ""
        except sr.RequestError as exc:
            raise ConnectionError(f"Google STT Service không khả dụng: {exc}") from exc

    def recognize_vosk(self, raw_audio: bytes) -> str:
        """
        Nhận diện âm thanh ngoại tuyến sử dụng mô hình Vosk (KaldiRecognizer).
        """
        if not self.vosk_model or not raw_audio:
            return ""
        try:
            rec = vosk.KaldiRecognizer(self.vosk_model, self.SAMPLE_RATE)
            rec.AcceptWaveform(raw_audio)
            res = json.loads(rec.FinalResult())
            return str(res.get("text", "")).strip()
        except Exception as exc:
            print(f"[STT ✗ Lỗi Vosk]: {exc}")
            return ""

    def _run_vosk_background(self, raw_audio: bytes, google_text: str) -> None:
        """
        Hàm chạy trong luồng ngầm (threading.Thread):
        Nhận diện Vosk trên cùng audio và tự động kích hoạt auto_learn(vosk_text, google_text).
        Đảm bảo hoàn toàn không làm gián đoạn hoặc chậm luồng chính.
        """
        try:
            t0 = time.time()
            vosk_text = self.recognize_vosk(raw_audio)
            elapsed = round(time.time() - t0, 3)

            print(f"\n[STT: Luồng ngầm Vosk ({elapsed}s)] Kết quả: \"{vosk_text}\"")

            if vosk_text and google_text:
                # Tự động học sự khác biệt giữa Vosk và Google STT
                auto_learn(vosk_text, google_text)
        except Exception as exc:
            print(f"[STT: Lỗi trong luồng ngầm Vosk]: {exc}")

    def record_push_to_talk(
        self,
        timeout: Optional[float] = None,
        max_record_duration: float = 15.0,
    ) -> bytes:
        """
        Thu âm Push-to-Talk (Ctrl+Space):
        - Chờ người dùng nhấn và giữ [Ctrl + Space].
        - Bắt đầu ghi âm ngay khi nhấn.
        - Dừng ghi âm ngay lập tức khi nhả phím.
        - Trả về bytes dữ liệu âm thanh thô (PCM 16kHz 16-bit mono).
        """
        self.check_microphone()

        print("[STT] ⏳ Nhấn và GIỮ phím [Ctrl + Space] để bắt đầu nói...")

        start_wait = time.time()
        # 1. Chờ phím Ctrl+Space được nhấn
        while not self.is_push_to_talk_pressed():
            if timeout is not None and (time.time() - start_wait) > timeout:
                print("[STT] Hết thời gian chờ (timeout), không có phím nhấn.")
                return b""
            time.sleep(0.015)

        # 2. Bắt đầu thu âm ngay khi phím được nhấn
        print("[STT] 🎙️ Đang thu âm... (Hãy nói và GIỮ phím, NHẢ phím để gửi lệnh)")

        audio_queue: queue.Queue = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            audio_queue.put(bytes(indata))

        stream = None
        recorded_frames = []
        record_start = time.time()

        try:
            stream = sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.samples_per_frame,
                dtype="int16",
                channels=self.CHANNELS,
                callback=audio_callback,
            )
            stream.start()

            # 3. Thu âm liên tục khi phím vẫn đang được giữ
            while self.is_push_to_talk_pressed():
                try:
                    frame = audio_queue.get(timeout=0.04)
                    recorded_frames.append(frame)
                except queue.Empty:
                    pass

                if (time.time() - record_start) >= max_record_duration:
                    print("[STT Cảnh báo] Đạt thời lượng tối đa (15s). Tự động dừng thu âm.")
                    break

            # Khi người dùng NHẢ phím: KHÔNG dừng mic ngay lập tức.
            # Đợi thêm 350ms (0.35s) để thu nốt âm thanh / âm tiết cuối cùng
            print("[STT] ⏹️ Đã nhả phím. Đợi 350ms thu nốt âm thanh cuối...")
            time.sleep(0.35)

            # Sau khi đợi 350ms thu nốt âm cuối, mới dừng mic và đóng luồng
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            stream = None

        except sd.PortAudioError as exc:
            print(f"[STT ✗ Lỗi Micro]: {exc}")
            raise
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

            # Thu nốt các frame âm thanh còn sót lại trong hàng đợi
            while not audio_queue.empty():
                try:
                    recorded_frames.append(audio_queue.get_nowait())
                except queue.Empty:
                    break

        print("[STT] Đang xử lý âm thanh...")

        if not recorded_frames:
            print("[STT] Không nghe thấy gì, vui lòng nói to hơn hoặc giữ phím lâu hơn")
            return b""

        raw_audio = b"".join(recorded_frames)
        duration_sec = len(raw_audio) / (self.SAMPLE_RATE * self.CHANNELS * 2)

        if duration_sec < self.MIN_AUDIO_DURATION_SEC:
            print(f"[STT] Đoạn thu âm quá ngắn ({duration_sec:.2f}s < {self.MIN_AUDIO_DURATION_SEC}s) -> Bỏ qua.")
            print("[STT] Không nghe thấy gì, vui lòng nói to hơn hoặc giữ phím lâu hơn")
            return b""

        return raw_audio

    def record_fixed(self, duration: float = 3.0) -> bytes:
        """
        Thu âm thời lượng cố định (dùng cho test tự động hoặc khi không dùng Push-to-Talk).
        """
        self.check_microphone()
        frames_to_read = int(self.SAMPLE_RATE * duration)
        print(f"[STT] Đang ghi âm {duration}s...")
        data = sd.rec(frames_to_read, samplerate=self.SAMPLE_RATE, channels=self.CHANNELS, dtype="int16")
        sd.wait()
        return data.tobytes()

    def record_wake_command(self, max_duration: float = 4.5, silence_limit: float = 0.9) -> bytes:
        """
        Thu âm thông minh sau khi đánh thức bằng Wake Word:
        - Lắng nghe khi người dùng bắt đầu nói.
        - Tự động ngắt khi phát hiện im lặng (silence_limit ~0.9s) sau khi đã nói xong.
        - Tối đa max_duration (4.5s) để tránh treo nếu môi trường có tiếng ồn nền.
        """
        self.check_microphone()
        chunk_size = self.CHUNK_SIZE
        recorded_frames = []
        speech_started = False
        silence_start = None
        start_time = time.time()
        speech_energy_threshold = 400.0  # RMS threshold cho giọng nói người

        print(f"[STT 🎙️] Đang lắng nghe câu lệnh (tối đa {max_duration}s)...")
        try:
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=self.CHANNELS, dtype="int16", blocksize=chunk_size) as stream:
                while (time.time() - start_time) < max_duration:
                    data, _ = stream.read(chunk_size)
                    recorded_frames.append(data.tobytes())
                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                    energy = np.sqrt(np.mean(samples ** 2)) if len(samples) > 0 else 0.0

                    if energy > speech_energy_threshold:
                        speech_started = True
                        silence_start = None
                    elif speech_started:
                        if silence_start is None:
                            silence_start = time.time()
                        elif (time.time() - silence_start) >= silence_limit:
                            # Người dùng đã nói xong và im lặng 0.9s -> Ngắt sớm!
                            break
                    else:
                        # Chưa bắt đầu nói: nếu quá 2.8s không có tiếng động -> dừng sớm
                        if (time.time() - start_time) > 2.8:
                            break
        except Exception as exc:
            print(f"[STT Cảnh báo record_wake_command]: {exc}")
            return self.record_fixed(duration=3.5)

        return b"".join(recorded_frames)

    def listen_command(self) -> str:
        """
        Lắng nghe câu lệnh rảnh tay (sau khi Wake Word đánh thức).
        """
        raw_audio = self.record_wake_command()
        if not raw_audio:
            return ""
        return self.process_audio(raw_audio)

    def process_audio(self, raw_audio: bytes) -> str:
        """
        Xử lý đoạn âm thanh theo kiến trúc Hybrid:
        - Có mạng: Gửi Google STT lấy kết quả trả về NGAY LẬP TỨC.
                   Đồng thời dùng threading chạy NGẦM Vosk để tự học.
        - Mất mạng: Nhận diện bằng Vosk Offline, áp dụng từ điển tự học và trả về kết quả.
        """
        if not raw_audio:
            print("[STT] Không nghe thấy gì, vui lòng nói to hơn hoặc giữ phím lâu hơn")
            return ""

        online = self.is_online()

        if online:
            # =================================================================
            # CHẾ ĐỘ CÓ MẠNG (ONLINE): GOOGLE STT + LUỒNG NGẦM VOSK TỰ HỌC
            # =================================================================
            try:
                t0 = time.time()
                google_text = self.recognize_google(raw_audio)
                elapsed = round(time.time() - t0, 3)

                clean_google = google_text.strip() if google_text else ""

                # Nếu kết quả từ Google STT trả về chuỗi rỗng "" hoặc khoảng trắng:
                # In thông báo và BỎ QUA, TUYỆT ĐỐI không gửi cho Vosk (để tránh Vosk tự bịa ra "mưa bất chợt")
                if not clean_google:
                    print("[STT] Không nghe thấy gì, vui lòng nói to hơn hoặc giữ phím lâu hơn")
                    return ""

                print(f"[STT Online - Google STT ({elapsed}s)]: \"{clean_google}\"")

                # KÍCH HOẠT LUỒNG NGẦM VOSK ĐỂ TỰ HỌC (CHỈ KHI CÓ KẾT QUẢ THẬT)
                bg_thread = threading.Thread(
                    target=self._run_vosk_background,
                    args=(raw_audio, clean_google),
                    daemon=True,
                    name="VoskAutoLearnThread",
                )
                bg_thread.start()

                # TRẢ VỀ KẾT QUẢ NGAY LẬP TỨC CHO BỘ NÃO XỬ LÝ (TỐC ĐỘ < 1s)
                return clean_google

            except ConnectionError as conn_err:
                print(f"[STT Cảnh báo] Mất kết nối Google STT ({conn_err}). Chuyển sang Vosk Offline...")
                # Rơi xuống xử lý Offline bên dưới
            except Exception as exc:
                print(f"[STT Cảnh báo] Google STT gặp sự cố ({exc}). Chuyển sang Vosk Offline...")
                # Rơi xuống xử lý Offline bên dưới

        # =====================================================================
        # CHẾ ĐỘ MẤT MẠNG (OFFLINE): VOSK + TỪ ĐIỂN TỰ HỌC OFFLINE_LEARNING.JSON
        # =====================================================================
        print("[STT: OFFLINE] Đang nhận diện ngoại tuyến bằng mô hình Vosk...")
        t0 = time.time()
        vosk_text = self.recognize_vosk(raw_audio)
        elapsed = round(time.time() - t0, 3)
        print(f"[STT Offline - Vosk ({elapsed}s)]: \"{vosk_text}\"")

        clean_vosk = vosk_text.strip() if vosk_text else ""
        if not clean_vosk:
            print("[STT] Không nghe thấy gì, vui lòng nói to hơn hoặc giữ phím lâu hơn")
            return ""

        # Áp dụng từ điển tự học từ offline_learning.json
        final_text = apply_offline_learning(clean_vosk)
        if final_text != clean_vosk:
            print(f"[STT Offline] Đã áp dụng từ điển tự học: \"{clean_vosk}\" -> \"{final_text}\"")

        return final_text

    def listen(
        self,
        push_to_talk: bool = True,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Lắng nghe và chuyển giọng nói thành văn bản.

        Args:
            push_to_talk: True để sử dụng Push-to-Talk (Ctrl+Space), False để thu âm cố định.
            timeout: Thời gian chờ tối đa khi chưa bấm phím (giây).

        Returns:
            str: Văn bản nhận diện được.
        """
        try:
            if push_to_talk:
                raw_audio = self.record_push_to_talk(timeout=timeout)
            else:
                raw_audio = self.record_fixed(duration=3.0)

            if not raw_audio:
                return ""

            return self.process_audio(raw_audio)

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[STT ✗ Lỗi]: {exc}")
            return ""
        finally:
            self.release_microphone()


# Khối chạy thử nghiệm trực tiếp
if __name__ == "__main__":
    print("=" * 65)
    print("  KIỂM TRA HỆ THỐNG NHẬN DIỆN GIỌNG NÓI HYBRID TỰ HỌC (VOICEPILOT)")
    print("  • Push-to-Talk: Nhấn và GIỮ phím [Ctrl + Space] để nói")
    print("  • Online: Google STT (<1s) + Chạy ngầm Vosk tự học")
    print("  • Offline: Vosk STT + Từ điển tự học offline_learning.json")
    print("  • Nhấn [Ctrl + C] để thoát chương trình.")
    print("=" * 65)

    try:
        stt = SpeechToText()

        status_net = "Có mạng (Google STT + Vosk ngầm)" if stt.is_online() else "Mất mạng (Vosk Offline)"
        print(f"\n[Trạng thái mạng]: {status_net}")

        while True:
            text = stt.listen(push_to_talk=True)
            if text:
                print(f"\n=> KẾT QUẢ TRẢ VỀ CHO BỘ NÃO: \"{text}\"\n")
            else:
                print("=> Không nhận diện được âm thanh rõ ràng hoặc đã hủy.\n")

            time.sleep(0.3)

    except KeyboardInterrupt:
        print("\n[STT] Đã nhận tín hiệu dừng. Tạm biệt!")
    except Exception as e:
        print(f"\n[Lỗi chương trình]: {e}")

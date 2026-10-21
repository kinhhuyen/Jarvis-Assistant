"""
Module: assistant.py
Mục đích: Chương trình chính kết nối 3 module của Trợ lý ảo Windows (VoicePilot):
    1. stt_engine.py  (SpeechToText)  : Thu âm và nhận diện giọng nói tiếng Việt.
    2. brain.py       (Brain)         : Phân tích ý định với Hybrid Routing (Regex + Ollama).
    3. actions.py     (ActionExecutor): Thực thi tuần tự các hành động trên hệ thống.
"""

import sys
import time

# Đảm bảo in tiếng Việt có dấu không bị lỗi UnicodeEncodeError trên Console Windows
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import colorama
from colorama import Back, Fore, Style

from actions import ActionExecutor
from brain import Brain
from stt_engine import SpeechToText

# Khởi tạo colorama tự động reset màu sau mỗi lệnh print
colorama.init(autoreset=True)


def print_banner() -> None:
    """Hiển thị banner giới thiệu trợ lý ảo đẹp mắt."""
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}╔══════════════════════════════════════════════════════════════════════════╗
║                    VOICEPILOT - TRỢ LÝ ẢO WINDOWS                        ║
║                                                                          ║
║  • Kiến trúc: Hybrid Tự Học (Push-to-Talk [Ctrl+Space] | Tốc độ < 1s)    ║
║  • Online STT: Google Speech-to-Text (Phản hồi tức thì)                  ║
║  • Offline STT & Tự học: Vosk luồng ngầm + offline_learning.json        ║
║  • Phân tích thông minh: Hybrid Routing (Fast Path Regex + Ollama LLM)   ║
║  • Thoát chương trình: Nhấn tổ hợp phím [Ctrl + C]                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def main() -> None:
    """Hàm khởi động và điều phối vòng lặp chính của Trợ lý ảo."""
    print_banner()

    # 1. Khởi tạo các module thành phần
    print(f"{Fore.YELLOW}[1/3] Đang khởi tạo STT Engine (Hybrid Google STT + Vosk Offline + Push-to-Talk)...")
    stt = SpeechToText(language="vi-VN")

    print(f"\n{Fore.YELLOW}[2/3] Đang kết nối Bộ não phân tích (Brain - Ollama llama3.2)...")
    brain = Brain(ollama_url="http://localhost:11434", model="llama3.2")

    print(f"\n{Fore.YELLOW}[3/3] Đang nạp Bộ thực thi hành động (Action Executor)...")
    executor = ActionExecutor()

    print(f"\n{Fore.GREEN}{Style.BRIGHT}==========================================================================")
    print(f"{Fore.GREEN}{Style.BRIGHT}✓ TẤT CẢ MODULE ĐÃ SẴN SÀNG! HÃY NÓI CÂU LỆNH VÀO MICRO CỦA BẠN.")
    print(f"{Fore.GREEN}{Style.BRIGHT}==========================================================================\n")

    # 2. Vòng lặp lắng nghe và xử lý liên tục
    while True:
        try:
            print(f"{Fore.CYAN}{Style.BRIGHT}──────────────────────────────────────────────────────────────────────────")
            print(f"{Fore.CYAN}[🎙️ Trợ lý ảo] Đang lắng nghe bạn nói...")

            # Bước 1: Thu âm và chuyển giọng nói thành văn bản
            user_text = stt.listen()

            if not user_text or not user_text.strip():
                # Không nhận diện được âm thanh rõ ràng hoặc hết thời gian
                stt.release_microphone()
                time.sleep(0.1)
                continue

            print(f"\n{Fore.GREEN}{Style.BRIGHT}[👤 Bạn đã nói]: \"{user_text}\"")

            # Bước 2: Phân tích văn bản qua Brain (Hybrid Routing)
            print(f"{Fore.MAGENTA}[🧠 Phân tích]: Đang giải mã ý định...")
            t_start = time.time()
            actions = brain.process(user_text)
            elapsed = round(time.time() - t_start, 2)
            print(f"{Fore.MAGENTA}[🧠 Phân tích xong ({elapsed}s)]: {len(actions)} hành động được sinh ra.")

            # Bước 3: Thực thi tuần tự các action qua ActionExecutor
            print(f"{Fore.YELLOW}[⚡ Thực thi]: Đang tiến hành thực hiện hành động...")
            executor.execute(actions)

            # Đảm bảo micro được giải phóng (close) hoàn toàn trước khi bắt đầu lượt nghe tiếp theo
            stt.release_microphone()
            time.sleep(0.2)
            print(f"{Fore.GREEN}[✓ Hoàn tất] Micro đã giải phóng hoàn toàn. Sẵn sàng cho câu lệnh tiếp theo.\n")

        except KeyboardInterrupt:
            # Xử lý phím tắt Ctrl+C thoát an toàn
            stt.release_microphone()
            raise
        except Exception as exc:
            stt.release_microphone()
            print(f"\n{Fore.RED}[✗ Lỗi không mong muốn trong vòng lặp]: {exc}")
            print(f"{Fore.YELLOW}[!] Đang khôi phục lại trạng thái lắng nghe...\n")
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}{Style.BRIGHT}[!] Đã nhận tín hiệu dừng (Ctrl + C). Đang đóng Trợ lý ảo...")
        time.sleep(0.5)
        print(f"{Fore.GREEN}{Style.BRIGHT}[✓] Đã thoát an toàn. Tạm biệt và hẹn gặp lại bạn!\n")
        sys.exit(0)
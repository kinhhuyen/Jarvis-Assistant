"""
Module: auto_learn.py
Mục đích: Module Tự Học Ngoại Tuyến (Offline Self-Learning) cho Trợ lý ảo VoicePilot.
Chức năng:
    - Nhận diện sự sai lệch giữa kết quả nhận diện của Vosk (offline) và Google STT (online).
    - Lọc bỏ triệt để các câu rác, câu nói mơ hồ hoặc ảo giác của STT qua các tầng Validation:
        + Kiểm tra độ tương đồng ngữ âm (Phonetic Similarity) bằng difflib.SequenceMatcher (loại bỏ ratio < 0.3).
        + Hỗ trợ bypass động từ cho ứng dụng hợp lệ (kể cả 1 từ như "chờ ro" -> "chrome") và lệnh âm lượng.
        + Giới hạn số lượng từ linh hoạt (Vosk: 1-7 từ).
        + Giới hạn kích thước file offline_learning.json tối đa 100 cặp từ theo cơ chế FIFO (First-In, First-Out).
    - Hỗ trợ đầy đủ các lệnh điều khiển hệ thống, thay đổi âm lượng và tìm kiếm thông tin.
    - Khi mất mạng, áp dụng từ điển đã học để chuyển đổi kết quả của Vosk thành câu lệnh chính xác.
"""

import difflib
import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Dict, Optional

# Đảm bảo in tiếng Việt có dấu không bị lỗi UnicodeEncodeError trên Console Windows
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Khóa an toàn đa luồng cho các thao tác đọc/ghi file offline_learning.json
_LEARNING_LOCK = threading.Lock()

# Đường dẫn mặc định tới file offline_learning.json
from utils import get_data_path
LEARNING_FILE_PATH = Path(get_data_path("offline_learning.json"))

# Giới hạn kích thước tối đa cho file offline_learning.json (FIFO)
MAX_LEARNING_ENTRIES = 100

# Ngưỡng tương đồng ngữ âm tối thiểu (difflib.SequenceMatcher ratio >= 0.5)
MIN_PHONETIC_SIMILARITY = 0.5

# Giới hạn chênh lệch số lượng từ tối đa giữa Vosk và Google (chống Vosk bịa câu dài lan man)
MAX_WORD_COUNT_DIFF = 2

# ĐIỀU KIỆN 1: Danh sách động từ hợp lệ mở rộng cho mọi loại lệnh
VALID_COMMAND_VERBS = (
    "mở", "tắt", "khóa", "khoá", "chụp", "tìm", "đóng",
    "kiếm", "tra", "xem", "tăng", "giảm", "chỉnh", "đặt", "bật", "khởi động"
)

# Danh sách từ khóa tìm kiếm: Bỏ qua kiểm tra động từ nếu câu chứa các từ khóa này
SEARCH_BYPASS_KEYWORDS = (
    "giá", "thời tiết", "tin tức", "tỷ giá", "tỉ giá", "chứng khoán"
)

# Danh sách từ khóa điều chỉnh âm lượng: Bỏ qua kiểm tra động từ
VOLUME_BYPASS_KEYWORDS = (
    "âm lượng", "phần trăm", "%"
)

# Danh sách ứng dụng hợp lệ: Bỏ qua kiểm tra động từ và cho phép độ dài 1 từ (ví dụ: "chờ ro" -> "chrome")
VALID_APP_NAMES = {
    "chrome", "edge", "zalo", "discord", "notepad", "microsoft store",
    "calc", "máy tính", "word", "excel", "cmd", "explorer", "thư mục",
    "coccoc", "paint", "spotify", "github", "telegram", "settings"
}

# ĐIỀU KIỆN 3: Danh sách các từ khóa rác / vô nghĩa đặc trưng do STT nghe sai
GARBAGE_KEYWORDS = [
    "mục đốc",
    "trưng bày",
    "hôm microsoft e",
]

# Danh sách các câu lệnh bị cắt cụt do nói dở hoặc nhả phím quá sớm
INCOMPLETE_COMMANDS = {
    "mở ổ",
    "mở do",
    "mở pic",
    "mở note",
}


def get_learning_file_path(custom_path: Optional[str] = None) -> Path:
    """Trả về đối tượng Path trỏ tới file offline_learning.json."""
    if custom_path:
        return Path(custom_path)
    return LEARNING_FILE_PATH


def load_offline_learning(filepath: Optional[str] = None) -> Dict[str, str]:
    """
    Tải từ điển tự học từ file offline_learning.json.
    Bọc try/except an toàn chống crash nếu file json bị lỗi định dạng.
    Trả về dict dạng: {"vosk_text": "google_text"}.
    """
    target_path = get_learning_file_path(filepath)
    with _LEARNING_LOCK:
        if not target_path.exists():
            return {}
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {
                        str(k).strip().lower(): str(v).strip().lower()
                        for k, v in data.items()
                        if k and v
                    }
        except Exception as exc:
            try:
                print(f"[AutoLearn Cảnh báo] Không thể đọc {target_path.name}: {exc}")
            except Exception:
                pass
    return {}


def auto_learn(
    vosk_text: str,
    google_text: str,
    filepath: Optional[str] = None
) -> bool:
    """
    Hàm tự học: So sánh kết quả nhận diện giữa Vosk và Google STT.
    Áp dụng 4 tầng lọc (Validation) nghiêm ngặt để loại bỏ câu rác:
        - Điều kiện 0 (Độ tương đồng ngữ âm): Sử dụng difflib.SequenceMatcher.
          Nếu ratio < 0.3 (Vosk tự bịa từ/nghe sai hoàn toàn), TUYỆT ĐỐI KHÔNG LƯU.
        - Điều kiện 1 (Mục đích rõ ràng / Bypass):
          + Nếu google_text là ứng dụng hợp lệ (chrome, edge...): Cho phép lưu (kể cả 1 từ).
          + Nếu google_text chứa từ khóa âm lượng ("âm lượng", "phần trăm", "%"): Cho phép lưu.
          + Nếu google_text chứa từ khóa tìm kiếm ("giá", "thời tiết"...): Cho phép lưu.
          + Các câu khác bắt buộc phải bắt đầu bằng động từ hợp lệ.
        - Điều kiện 2 (Số lượng từ hợp lệ):
          + Vosk text: 1 đến 7 từ.
          + Google text: 1 đến 7 từ (cho ứng dụng hợp lệ), hoặc 2 đến 7 từ (cho lệnh thường).
        - Điều kiện 3 (Khử rác STT): Loại bỏ từ vô nghĩa và câu lệnh bị cắt cụt do nói dở.
        - Điều kiện 4 (Giới hạn kích thước file): Giới hạn tối đa 100 cặp từ theo FIFO.

    Args:
        vosk_text: Chuỗi văn bản nhận diện từ Vosk (luồng chạy ngầm).
        google_text: Chuỗi văn bản nhận diện từ Google STT.
        filepath: Đường dẫn file json tùy chọn (mặc định offline_learning.json).

    Returns:
        bool: True nếu đã ghi nhớ cặp từ mới hợp lệ, False nếu bị bỏ qua.
    """
    try:
        if not isinstance(vosk_text, str) or not isinstance(google_text, str):
            return False

        v_clean = vosk_text.strip().lower()
        g_clean = google_text.strip().lower()

        # Kiểm tra rỗng hoặc giống nhau
        if not v_clean or not g_clean or v_clean == g_clean:
            return False

        # Kiểm tra độ dài ký tự tối thiểu (chống rác 1 ký tự)
        if len(v_clean) < 2 or len(g_clean) < 2:
            try:
                print(f"[AutoLearn] Bỏ qua câu lệnh rác: Ký tự quá ngắn < 2 ('{v_clean}' -> '{g_clean}')")
            except Exception:
                pass
            return False

        g_words = g_clean.split()
        v_words = v_clean.split()

        # =====================================================================
        # ĐIỀU KIỆN CHÊNH LỆCH SỐ TỪ:
        # Nếu số lượng từ của vosk_text chênh lệch quá lớn so với google_text (> 2 từ),
        # lập tức CHẶN để ngăn Vosk tự bịa ra các câu dài lan man khi mic bị nhiễu.
        # Ví dụ: Google 4 từ nhưng Vosk bịa ra 7 từ -> chênh lệch 3 từ > 2 từ -> Chặn.
        # =====================================================================
        word_diff = abs(len(v_words) - len(g_words))
        if word_diff > MAX_WORD_COUNT_DIFF:
            try:
                print(
                    f"[AutoLearn] Bỏ qua câu lệnh rác: Chênh lệch số từ quá lớn ({word_diff} từ > {MAX_WORD_COUNT_DIFF} từ) "
                    f"('{v_clean}' [{len(v_words)} từ] vs '{g_clean}' [{len(g_words)} từ])"
                )
            except Exception:
                pass
            return False

        # =====================================================================
        # ĐIỀU KIỆN 0: KIỂM TRA ĐỘ TƯƠNG ĐỒNG NGỮ ÂM (PHONETIC SIMILARITY)
        # Sử dụng difflib.SequenceMatcher để so sánh chuỗi vosk_text và google_text.
        # Ngưỡng tối thiểu là 0.5 (Vosk phải nghe giống Google ít nhất 50%).
        # Nếu độ tương đồng (ratio) < 0.5 (quá khác biệt, chứng tỏ Vosk nghe sai hoàn toàn
        # và tự bịa ra), thì TUYỆT ĐỐI KHÔNG LƯU vào file json.
        # =====================================================================
        raw_ratio = difflib.SequenceMatcher(None, v_clean, g_clean).ratio()
        no_space_ratio = difflib.SequenceMatcher(
            None, v_clean.replace(" ", ""), g_clean.replace(" ", "")
        ).ratio()
        sim_ratio = min(raw_ratio, no_space_ratio)

        # Với các câu từ 3 từ trở lên: kiểm tra thêm độ tương đồng từ vựng
        # Chống trường hợp Vosk bịa câu hoàn toàn khác nghĩa nhưng vô tình trùng các âm đơn lẻ
        # (ví dụ: 'xem phim gia và ông này' [0 từ tương đồng] vs 'tìm kiếm giá vàng hôm nay')
        if len(v_words) >= 3 and len(g_words) >= 3:
            matching_words = sum(
                1 for vw in v_words
                if any(difflib.SequenceMatcher(None, vw, gw).ratio() >= 0.75 for gw in g_words)
            )
            word_overlap_ratio = matching_words / len(v_words)
            if word_overlap_ratio < 0.3:
                sim_ratio = min(sim_ratio, word_overlap_ratio)

        if sim_ratio < MIN_PHONETIC_SIMILARITY:
            try:
                print(
                    f"[AutoLearn] Bỏ qua câu lệnh rác: Độ tương đồng ngữ âm quá thấp ({sim_ratio:.2f} < {MIN_PHONETIC_SIMILARITY}) "
                    f"('{v_clean}' -> '{g_clean}')"
                )
            except Exception:
                pass
            return False

        # =====================================================================
        # ĐIỀU KIỆN 1: MỞ RỘNG ĐIỀU KIỆN BYPASS (KHÔNG CẦN ĐỘNG TỪ)
        # 1. google_text là tên ứng dụng hợp lệ (chrome, edge, zalo, discord...)
        # 2. google_text chứa từ khóa âm lượng ("âm lượng", "phần trăm", "%")
        # 3. google_text chứa từ khóa tìm kiếm ("giá", "thời tiết", "tin tức"...)
        # =====================================================================
        is_app_bypass = (
            g_clean in VALID_APP_NAMES
            or (g_clean.startswith("mở ") and g_clean[3:].strip() in VALID_APP_NAMES)
        )
        is_volume_bypass = any(k in g_clean for k in VOLUME_BYPASS_KEYWORDS)
        is_search_bypass = any(k in g_clean for k in SEARCH_BYPASS_KEYWORDS)

        should_bypass_verb = is_app_bypass or is_volume_bypass or is_search_bypass

        if not should_bypass_verb:
            starts_verb = (
                (len(g_words) >= 1 and g_words[0] in VALID_COMMAND_VERBS)
                or (len(g_words) >= 2 and f"{g_words[0]} {g_words[1]}" in VALID_COMMAND_VERBS)
            )
            if not starts_verb:
                try:
                    print(f"[AutoLearn] Bỏ qua câu lệnh rác: Google text '{g_clean}' không bắt đầu bằng động từ hợp lệ")
                except Exception:
                    pass
                return False

        # =====================================================================
        # ĐIỀU KIỆN 2: GIỚI HẠN SỐ LƯỢNG TỪ
        # - Vosk text cho phép từ 1 đến 7 từ (bắt được cả "chờ ro" và "âm lượng lên 80%").
        # - Google text cho phép từ 1 đến 7 từ nếu là ứng dụng hợp lệ (cho phép 1 từ "chrome"),
        #   hoặc từ 2 đến 7 từ đối với các câu lệnh thông thường.
        # =====================================================================
        if len(v_words) < 1 or len(v_words) > 7:
            try:
                print(f"[AutoLearn] Bỏ qua câu lệnh rác: Vosk text '{v_clean}' có độ dài không hợp lệ ({len(v_words)} từ, yêu cầu 1-7 từ)")
            except Exception:
                pass
            return False

        min_g_words = 1 if is_app_bypass else 2
        max_g_words = 7
        if len(g_words) < min_g_words or len(g_words) > max_g_words:
            try:
                print(f"[AutoLearn] Bỏ qua câu lệnh rác: Google text '{g_clean}' có độ dài không hợp lệ ({len(g_words)} từ, yêu cầu {min_g_words}-{max_g_words} từ)")
            except Exception:
                pass
            return False

        # =====================================================================
        # ĐIỀU KIỆN 3: LOẠI BỎ TỪ KHÓA VÔ NGHĨA / RÁC DO STT SINH RA
        # =====================================================================
        for kw in GARBAGE_KEYWORDS:
            if kw in g_clean or kw in v_clean:
                try:
                    print(f"[AutoLearn] Bỏ qua câu lệnh rác: Chứa từ vô nghĩa '{kw}' ('{v_clean}' -> '{g_clean}')")
                except Exception:
                    pass
                return False

        # Loại bỏ các câu lệnh bị cắt cụt do nói dở
        if g_clean in INCOMPLETE_COMMANDS:
            try:
                print(f"[AutoLearn] Bỏ qua câu lệnh rác: Câu lệnh bị cắt cụt/thiếu từ ('{g_clean}')")
            except Exception:
                pass
            return False

        target_path = get_learning_file_path(filepath)

        with _LEARNING_LOCK:
            current_data = {}
            if target_path.exists():
                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            current_data = {
                                str(k).strip().lower(): str(v).strip().lower()
                                for k, v in loaded.items()
                            }
                except Exception as exc:
                    try:
                        print(f"[AutoLearn Cảnh báo] Lỗi đọc file cũ {target_path.name}: {exc}. Khởi tạo lại rỗng.")
                    except Exception:
                        pass
                    current_data = {}

            # Nếu đã có và giá trị giống hệt, không cần ghi lại
            if current_data.get(v_clean) == g_clean:
                return False

            # Cập nhật / Thêm mới cặp từ
            current_data[v_clean] = g_clean

            # =====================================================================
            # ĐIỀU KIỆN 4: GIỚI HẠN KÍCH THƯỚC FILE (FIFO TỐI ĐA 100 CẶP TỪ)
            # Nếu file offline_learning.json đã có hơn 100 cặp từ, hãy xóa bớt
            # những cặp cũ nhất (FIFO) để tránh file phình to vô tội vạ.
            # =====================================================================
            while len(current_data) > MAX_LEARNING_ENTRIES:
                oldest_key = next(iter(current_data))
                removed_val = current_data.pop(oldest_key)
                try:
                    print(
                        f"[AutoLearn: FIFO] Đã xóa cặp từ cũ nhất '{oldest_key}' -> '{removed_val}' "
                        f"(Vượt quá giới hạn {MAX_LEARNING_ENTRIES} cặp từ)"
                    )
                except Exception:
                    pass

            # Ghi an toàn qua file tạm rồi thay thế (atomic write)
            try:
                temp_path = target_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(current_data, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, target_path)
                try:
                    print(f"[AutoLearn] [OK] ĐÃ TỰ HỌC: \"{v_clean}\" -> \"{g_clean}\" (Đã lưu vào {target_path.name})")
                except Exception:
                    pass
                return True
            except Exception as exc:
                try:
                    print(f"[AutoLearn Error] Không thể ghi file {target_path.name}: {exc}")
                except Exception:
                    pass
                return False

    except Exception as exc:
        try:
            print(f"[AutoLearn ✗ Lỗi ngoại lệ trong quá trình tự học]: {exc}")
        except Exception:
            pass
        return False


def apply_offline_learning(text: str, filepath: Optional[str] = None) -> str:
    """
    Áp dụng từ điển tự học vào chuỗi văn bản từ Vosk khi hệ thống chạy Offline.
    Quy tắc thay thế:
        1. Khớp chính xác toàn bộ chuỗi (Exact match).
        2. Khớp cụm từ con (Substring/Phrase match) theo thứ tự từ dài đến ngắn.

    Args:
        text: Chuỗi văn bản thô do Vosk trả về.
        filepath: Đường dẫn file json tùy chọn.

    Returns:
        str: Chuỗi văn bản đã được chuẩn hóa / sửa lỗi theo từ điển tự học.
    """
    try:
        if not text or not isinstance(text, str):
            return ""

        cleaned = text.strip()
        lower_t = cleaned.lower()

        learned_map = load_offline_learning(filepath)
        if not learned_map:
            return cleaned

        # 1. Khớp chính xác toàn câu
        if lower_t in learned_map:
            return learned_map[lower_t]

        # 2. Thay thế cụm từ con theo thứ tự độ dài giảm dần
        result = lower_t
        sorted_items = sorted(learned_map.items(), key=lambda item: len(item[0]), reverse=True)

        for v_key, g_val in sorted_items:
            # Thay thế độc lập cụm từ (word boundary)
            pattern = re.compile(rf"(?<!\w){re.escape(v_key)}(?!\w)", re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(g_val, result)

        return result.strip()
    except Exception as exc:
        try:
            print(f"[AutoLearn Cảnh báo] Lỗi khi áp dụng từ điển tự học: {exc}")
        except Exception:
            pass
        return text.strip() if isinstance(text, str) else ""

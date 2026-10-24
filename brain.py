"""
Module: brain.py
Mục đích: Bộ não xử lý ngôn ngữ tự nhiên (NLU) cho Trợ lý ảo Windows.
Kiến trúc: Hybrid Routing (Định tuyến kết hợp)
    1. FAST PATH (Rule-based Regex): Bắt các lệnh cơ bản tức thì (độ trễ < 1ms).
    2. SLOW PATH (LLM - Ollama llama3.2): Tự động sửa lỗi chính tả từ STT,
       xử lý câu lệnh phức tạp và câu lệnh kết hợp nhiều hành động.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from rapidfuzz import fuzz

from memory_manager import MemoryManager

# Đảm bảo in tiếng Việt có dấu không bị lỗi UnicodeEncodeError trên Console Windows
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class Brain:
    """
    Lớp xử lý ý định và sinh danh sách các hành động (Actions) cho Trợ lý ảo.

    Sử dụng kiến trúc Hybrid Routing:
        - Fast Path (Regex): Ưu tiên tốc độ tối đa cho các lệnh đơn lẻ quen thuộc.
        - Slow Path (Ollama LLM): Xử lý ngôn ngữ tự nhiên sâu, sửa lỗi chính tả và tách lệnh ghép.
    """

    # Dictionary map phiên âm Việt sang tên app chuẩn (so khớp RapidFuzz >80%)
    PHONETIC_DICT: Dict[str, str] = {
        "quật": "word",
        "guốt": "word",
        "an ti gra vơ ti": "antigravity",
        "an ti": "antigravity",
        "rề vô": "revo uninstaller",
        "in sờ to lơ": "revo uninstaller",
        "chôm": "chrome",
    }

    # Từ điển FUZZY_MAP mở rộng: Map mạnh mẽ các biến thể nghe nhầm / phiên âm tiếng Việt thành app chuẩn
    FUZZY_MAP: Dict[str, str] = {
        # chrome
        "chờ rộng": "chrome",
        "chờ rôm": "chrome",
        "cờ rô": "chrome",
        "cờ rôm": "chrome",
        "chôm": "chrome",
        "chrome": "chrome",
        "google chrome": "chrome",
        "google": "chrome",
        "gúc gồ": "chrome",
        "gu gồ": "chrome",
        "gúc": "chrome",
        "trình duyệt": "chrome",

        # edge
        "mở trình diện": "edge",
        "trình diện": "edge",
        "ếp": "edge",
        "ép": "edge",
        "ếp cờ": "edge",
        "ép cờ": "edge",
        "ếp cờ rô": "edge",
        "ép cờ rô": "edge",
        "ết": "edge",
        "edge": "edge",
        "msedge": "edge",
        "microsoft edge": "edge",
        "cạnh": "edge",

        # zalo
        "vỡ giả lô": "zalo",
        "giả lô": "zalo",
        "da lô": "zalo",
        "dà lô": "zalo",
        "zalo": "zalo",

        # máy tính (calc)
        "máy bân": "máy tính",
        "mê tân": "máy tính",
        "máy tình": "máy tính",
        "máy tính": "máy tính",
        "calc": "calc",
        "calculator": "calc",

        # notepad
        "nốt bát": "notepad",
        "nốc bát": "notepad",
        "nốt pát": "notepad",
        "notepad": "notepad",
        "ghi chú": "notepad",
        "soạn thảo": "notepad",

        # excel
        "mờ sờ ép": "excel",
        "ếch xen": "excel",
        "excel": "excel",
        "microsoft excel": "excel",

        # word
        "quật": "word",
        "guốt": "word",
        "quớt": "word",
        "guốc": "word",
        "uốt": "word",
        "word": "word",
        "microsoft word": "word",

        # antigravity
        "an ti gra vơ ti": "antigravity",
        "an ti": "antigravity",
        "an ti gra vi ti": "antigravity",
        "antigravity": "antigravity",

        # revo uninstaller
        "rề vô": "revo uninstaller",
        "in sờ to lơ": "revo uninstaller",
        "revo": "revo uninstaller",
        "revo uninstaller": "revo uninstaller",

        # cmd
        "xi em đê": "cmd",
        "com măng": "cmd",
        "cmd": "cmd",
        "terminal": "cmd",
        "command prompt": "cmd",

        # settings
        "sét tình": "settings",
        "sết tinh": "settings",
        "cài đặt": "settings",
        "settings": "settings",

        # discord
        "mỡ đi cồ": "discord",
        "mỡ đi cọt": "discord",
        "mở đi cọt": "discord",
        "đi cọt": "discord",
        "đi cồ": "discord",
        "đít cọt": "discord",
        "đi xcọt": "discord",
        "đít cọc": "discord",
        "đít sờ cọt": "discord",
        "discord": "discord",

        # github
        "git hắp": "github",
        "gít húp": "github",
        "github": "github",

        # spotify
        "sờ pốt ti phai": "spotify",
        "sốp ti": "spotify",
        "sờ pốt ti": "spotify",
        "spotify": "spotify",

        # microsoft store
        "mai cờ rô sốp sờ to": "microsoft store",
        "míc sô sốp": "microsoft store",
        "chợ ứng dụng": "microsoft store",
        "microsoft store": "microsoft store",
        "store": "microsoft store",

        # telegram
        "tê lê gram": "telegram",
        "tê lê": "telegram",
        "telegram": "telegram",

        # explorer / thư mục
        "phay ếch pờ lo rơ": "explorer",
        "phay ếch": "explorer",
        "phai ếch": "explorer",
        "phai": "explorer",
        "mở phai": "explorer",
        "thư mục": "explorer",
        "mở thư mục": "explorer",
        "explorer": "explorer",
        "file explorer": "explorer",
        "tệp": "explorer",
        "ếp lò hương": "explorer",
        "mở ếp lò hương": "explorer",
        "lò hương": "explorer",
        "ưu phai": "explorer",
        "mở ưu phai": "explorer",

        # cốc cốc
        "cốc cốc": "coccoc",
        "coccoc": "coccoc",

        # paint
        "paint": "paint",
        "vẽ": "paint",
        "mspaint": "paint",

        # =====================================================================
        # Từ khóa tìm kiếm phổ biến & các biến thể STT nghe nhầm (Search Web)
        # =====================================================================
        # giá vàng
        "giớn vông": "giá vàng",
        "giởn đông": "giá vàng",
        "kiếm gió vào": "giá vàng",
        "chính giá tàn ôm": "giá vàng",
        "định giá phạm": "giá vàng",
        "kiếm gió": "giá vàng",
        "giá phạm": "giá vàng",
        "giá phàng": "giá vàng",
        "gió vào": "giá vàng",
        "giờnộng vông": "giá vàng",
        "giá vàng": "giá vàng",

        # thời tiết
        "thời tiếc": "thời tiết",
        "thời tiết đè nẵng": "thời tiết đà nẵng",
        "thời tiết": "thời tiết",

        # tin tức
        "tin tức": "tin tức",
        "tin tứt": "tin tức",

        # tỷ giá
        "tỷ giá": "tỷ giá",
        "tỉ giá": "tỷ giá",
        "tỷ dá": "tỷ giá",

        # bóng đá
        "bóng đá": "bóng đá",
        "bóng dá": "bóng đá",

        # =====================================================================
        # Thư mục hệ thống & Từ lóng phiên âm (Pictures, Downloads, Documents)
        # =====================================================================
        # pictures / ảnh
        "bít trơ": "pictures",
        "bít thơ": "pictures",
        "pic trơ": "pictures",
        "mở bít trơ": "pictures",
        "ảnh": "pictures",
        "hình ảnh": "pictures",
        "mở ảnh": "pictures",
        "mở hình ảnh": "pictures",
        "pictures": "pictures",

        # downloads / tải về
        "đao lốt": "downloads",
        "đao nốt": "downloads",
        "đao lát": "downloads",
        "mở đao lốt": "downloads",
        "tải về": "downloads",
        "tải xuống": "downloads",
        "mở tải về": "downloads",
        "mở tải xuống": "downloads",
        "downloads": "downloads",

        # documents / tài liệu
        "tài liệu": "documents",
        "mở tài liệu": "documents",
        "văn bản": "documents",
        "đốc cu mần": "documents",
        "documents": "documents",
    }

    # Danh sách các thư mục hệ thống chuẩn hỗ trợ qua open_folder
    FOLDER_TARGETS = {
        "pictures", "downloads", "documents", "desktop", "music", "videos"
    }

    # Danh sách các chủ đề tìm kiếm chuẩn được hỗ trợ qua FUZZY_MAP
    SEARCH_TOPICS = {
        "giá vàng", "thời tiết", "tin tức", "tỷ giá", "bóng đá"
    }

    # Bảng sửa lỗi chính tả cứng cho các cụm từ STT hay nghe nhầm trong câu tìm kiếm
    FUZZY_SEARCH_CORRECTIONS: Dict[str, str] = {
        "giớn vông": "giá vàng",
        "giởn đông": "giá vàng",
        "kiếm gió vào": "giá vàng",
        "chính giá tàn ôm": "giá vàng",
        "định giá phạm": "giá vàng",
        "kiếm gió": "giá vàng",
        "giá phạm": "giá vàng",
        "giá phàng": "giá vàng",
        "gió vào": "giá vàng",
        "giờnộng vông": "giá vàng",
        "thời tiếc": "thời tiết",
        "thời tiết đè nẵng": "thời tiết đà nẵng",
        "tin tứt": "tin tức",
        "tỷ dá": "tỷ giá",
        "tỉ giá": "tỷ giá",
        "bóng dá": "bóng đá",
        "đà ảnh": "đà nẵng",
        "chứng khoác": "chứng khoán",
    }

    # Danh sách các app chuẩn trong WHITELIST
    WHITELIST = {
        "chrome", "edge", "notepad", "calc", "máy tính", "word",
        "excel", "cmd", "explorer", "thư mục", "zalo", "coccoc",
        "paint", "spotify", "discord", "github", "microsoft store",
        "telegram", "settings", "antigravity", "revo uninstaller"
    }

    # Danh sách app hợp lệ để kiểm tra và chống ảo giác LLM
    VALID_APP_NAMES = WHITELIST

    # Giữ tương thích ngược với APP_WHITELIST_MAP
    APP_WHITELIST_MAP = FUZZY_MAP

    # Các liên từ nối báo hiệu câu lệnh ghép nhiều hành động (cần đưa qua LLM)
    COMPOUND_CONJUNCTIONS: List[str] = [
        " và ", " rồi ", " sau đó ", " đồng thời ", " tiếp theo ", " cùng với "
    ]

    # System Prompt tối ưu hóa cho mô hình llama3.2, hỗ trợ sửa lỗi tìm kiếm thông minh và suy luận phiên âm
    SYSTEM_PROMPT: str = """Bạn là bộ não phân tích lệnh của Trợ lý ảo VoicePilot trên Windows.
Nhiệm vụ của bạn: Phân tích câu lệnh của người dùng thành danh sách các hành động JSON (actions).

QUY TẮC CỰC KỲ NGHIÊM NGẶT VỀ NHẬN DIỆN Ý ĐỊNH (CHỐNG ẢO GIÁC TUYỆT ĐỐI):
1. ĐIỀU KIỆN TIÊN QUYẾT: CHỈ trả về action nếu câu lệnh của người dùng có chứa ĐỘNG TỪ HÀNH ĐỘNG RÕ RÀNG (mở, bật, khởi động, chạy, tắt, đóng, thoát, chụp, tìm, tìm kiếm, kiếm, định giá, tra cứu, xem, tăng, giảm, đặt, chỉnh, cài, khóa, restart, v.v.) VÀ DANH TỪ LIÊN QUAN ĐẾN MÁY TÍNH / THÔNG TIN CẦN TÌM / PHẦN MỀM / HỆ THỐNG.
2. NẾU KHÔNG THỎA MÃN ĐIỀU KIỆN TRÊN: Nếu câu nói là chào hỏi, cảm thán, trò chuyện xã giao, hoặc câu vô nghĩa / không rõ nghĩa (ví dụ: "Hôm nay đợi đại tế", "Trời hôm nay đẹp quá", "Xin chào bạn", "Alo 123", "Tôi mệt quá"): BẮT BUỘC TRẢ VỀ DUY NHẤT: {"actions": [{"action": "unknown"}]}.
3. TUYỆT ĐỐI KHÔNG TỰ BỊA RA HÀNH ĐỘNG khi câu nói không hề có động từ hành động rõ ràng.

QUY TẮC PHÂN BIỆT ĐỘ SÁNG VÀ ÂM LƯỢNG (BẮT BUỘC TUÂN THỦ):
- Nếu câu lệnh có từ "sáng", "độ sáng", "ánh sáng" -> BẮT BUỘC trả về action "brightness" (TUYỆT ĐỐI KHÔNG trả về volume).
- Nếu câu lệnh có từ "âm lượng", "âm thanh", "tiếng" -> BẮT BUỘC trả về action "volume" (TUYỆT ĐỐI KHÔNG trả về brightness).

QUY TẮC SUY ĐOÁN TÊN ỨNG DỤNG VÀ PHIÊN ÂM TIẾNG ANH (Chỉ áp dụng khi CÓ ĐỘNG TỪ MỞ/BẬT/CHẠY/TẮT/ĐÓNG/KHỞI ĐỘNG):
- DANH SÁCH APP HỢP LỆ DUY NHẤT TRONG WHITELIST: chrome, edge, zalo, notepad, máy tính, calc, word, excel, cmd, coccoc, paint, spotify, discord, github, microsoft store, telegram, settings, antigravity, revo uninstaller.
- QUY TẮC ĐẶC BIỆT VỀ PHIÊN ÂM ANH-VIỆT:
  Người dùng Việt Nam thường phát âm tên app tiếng Anh theo phiên âm tiếng Việt (Ví dụ: 'đít cọt' = discord, 'sờ pốt ti' = spotify). Nếu gặp từ lạ trong câu 'mở [X]', hãy suy luận xem đó là app tiếng Anh nào trong danh sách hỗ trợ.
  Các từ phiên âm này ĐƯỢC XEM LÀ TÊN PHẦN MỀM HỢP LỆ (KHÔNG PHẢI VÔ NGHĨA). Khi gặp 'mở [X]', 'bật [X]', 'chạy [X]' với [X] là từ lạ, BẮT BUỘC SUY LUẬN xem [X] tương ứng với app nào trong danh sách WHITELIST.
  + Ví dụ phiên âm:
    * "quật", "guốt", "quớt", "guốc", "uốt" -> app: "word"
    * "an ti gra vơ ti", "an ti", "an ti gra vi ti" -> app: "antigravity"
    * "rề vô", "in sờ to lơ", "revo" -> app: "revo uninstaller"
    * "chôm", "chờ rôm", "chờ rộng", "cờ rôm", "cờ rô", "gu gồ" -> app: "chrome"
    * "đít cọt", "đi xcọt", "đít cọc", "đít sờ cọt" -> app: "discord"
    * "git hắp", "gít húp" -> app: "github"
    * "sờ pốt ti phai", "sốp ti", "sờ pốt ti" -> app: "spotify"
    * "mai cờ rô sốp sờ to", "míc sô sốp", "chợ ứng dụng" -> app: "microsoft store"
    * "tê lê gram", "tê lê" -> app: "telegram"
    * "sét tình", "sết tinh", "cài đặt" -> app: "settings"
    * "mờ sờ ép", "ếch xen" -> app: "excel"
    * "xi em đê", "com măng" -> app: "cmd"
    * "ếp", "ép", "ếp cờ", "ết", "ếp cờ rô" -> app: "edge"
    * "vỡ giả lô", "giả lô", "da lô", "dà lô" -> app: "zalo"
    * "nốt bát", "nốc bát", "nốt pát" -> app: "notepad"
    * "máy bân", "mê tân", "máy tình" -> app: "máy tính" (calc)
    * "phay ếch pờ lo rơ", "phay ếch", "phai ếch", "phai", "ếp lò hương", "ưu phai" -> action: "open_explorer"
- Bất kỳ app nào không thuộc WHITELIST -> BẮT BUỘC trả về {"action": "unknown"}.

QUY TẮC THÔNG MINH CHO LỆNH TÌM KIẾM (search_web - BẢO TOÀN NGUYÊN VĂN & CHỈ SỬA LỖI NẶNG):
- Kích hoạt khi câu lệnh có ý định tìm kiếm trên web ("tìm kiếm", "tìm", "tra cứu", "kiếm", "định giá", "xem", "search", "google", v.v.).
- NGUYÊN TẮC CỐT LÕI VỀ BẢO TOÀN TỪ KHÓA: Nếu câu lệnh tìm kiếm đã có nghĩa (ví dụ: "thời tiết", "giá bitcoin", "bảng xếp hạng bóng đá", "công thức nấu ăn", "tin tức"), BẮT BUỘC GIỮ NGUYÊN VĂN 100%, TUYỆT ĐỐI KHÔNG TỰ Ý SỬA ĐỔI HOẶC BỊA THÊM TỪ KHÓA.
- CHỈ ĐƯỢC PHÉP SỬA LỖI NẾU CỤM TỪ ĐÓ LÀ TỪ VÔ NGHĨA HOÀN TOÀN DO STT NGHE NHẦM:
  + "giớn vông", "giởn đông", "kiếm gió vào", "chính giá tàn ôm", "định giá phạm", "kiếm gió", "giá phạm", "gió vào" -> query: "giá vàng" (hoặc "giá vàng hôm nay").
  + "thời tiếc", "thời tiết đè nẵng", "thời tiết đà ảnh" -> query: "thời tiết" (hoặc "thời tiết đà nẵng").
  + "tin tứt" -> query: "tin tức".
  + "tỷ dá", "tỉ giá" -> query: "tỷ giá".
  + "bóng dá" -> query: "bóng đá".
  + "chứng khoác" -> query: "chứng khoán".

Danh sách Action hợp lệ:
- open_app: {"action": "open_app", "name": "<tên app trong whitelist>"}
- close_app: {"action": "close_app", "name": "<tên app trong whitelist>"}
- search_web: {"action": "search_web", "query": "<từ khóa tìm kiếm đã được chuẩn hóa/sửa lỗi chính tả>"}
- screenshot: {"action": "screenshot"}
- lock_screen: {"action": "lock_screen"}
- shutdown: {"action": "shutdown"}
- restart: {"action": "restart"}
- open_explorer: {"action": "open_explorer"}
- open_drive: {"action": "open_drive", "drive": "C"} hoặc {"action": "open_drive", "drive": "D"}
- open_folder: {"action": "open_folder", "folder": "pictures"} hoặc {"action": "open_folder", "folder": "downloads"} hoặc {"action": "open_folder", "folder": "documents"}
- volume: {"action": "volume", "direction": "up hoặc down"} hoặc {"action": "volume", "percentage": 0 đến 100}
- brightness: {"action": "brightness", "direction": "up hoặc down"} hoặc {"action": "brightness", "percentage": 0 đến 100}
- wifi: {"action": "wifi", "state": "on hoặc off"}
- bluetooth: {"action": "bluetooth", "state": "on hoặc off"}
- unknown: {"action": "unknown"}
- unknown: {"action": "unknown"}

BẮT BUỘC:
Trả về duy nhất định dạng JSON có cấu trúc:
{"actions": [{"action": "..."}]}
Tuyệt đối không giải thích hay viết thêm bất kỳ văn bản nào khác.

Ví dụ:
Input: "Hôm nay đợi đại tế"
Output: {"actions": [{"action": "unknown"}]}

Input: "Trời hôm nay đẹp quá bạn ơi"
Output: {"actions": [{"action": "unknown"}]}

Input: "mở ổ d"
Output: {"actions": [{"action": "open_drive", "drive": "D"}]}

Input: "mở ổ c"
Output: {"actions": [{"action": "open_drive", "drive": "C"}]}

Input: "mở bít trơ"
Output: {"actions": [{"action": "open_folder", "folder": "pictures"}]}

Input: "mở ảnh"
Output: {"actions": [{"action": "open_folder", "folder": "pictures"}]}

Input: "mở đao lốt"
Output: {"actions": [{"action": "open_folder", "folder": "downloads"}]}

Input: "mở tài liệu"
Output: {"actions": [{"action": "open_folder", "folder": "documents"}]}

Input: "mở đít cọc"
Output: {"actions": [{"action": "open_app", "name": "discord"}]}

Input: "mở sờ pốt ti"
Output: {"actions": [{"action": "open_app", "name": "spotify"}]}

Input: "mở git hắp"
Output: {"actions": [{"action": "open_app", "name": "github"}]}

Input: "bật tê lê"
Output: {"actions": [{"action": "open_app", "name": "telegram"}]}

Input: "mở mai cờ rô sốp sờ to"
Output: {"actions": [{"action": "open_app", "name": "microsoft store"}]}

Input: "mở cài đặt"
Output: {"actions": [{"action": "open_app", "name": "settings"}]}

Input: "Định giá phạm hôm nay"
Output: {"actions": [{"action": "search_web", "query": "giá vàng hôm nay"}]}

Input: "Kiếm gió vào hôm nay"
Output: {"actions": [{"action": "search_web", "query": "giá vàng hôm nay"}]}

Input: "mở ếp lò hương"
Output: {"actions": [{"action": "open_explorer"}]}

Input: "mở ưu phai"
Output: {"actions": [{"action": "open_explorer"}]}

Input: "phai"
Output: {"actions": [{"action": "open_explorer"}]}

Input: "khóa màn hình"
Output: {"actions": [{"action": "lock_screen"}]}

Input: "khởi động lại máy"
Output: {"actions": [{"action": "restart"}]}

Input: "Mở Chrome và tìm kiếm giá vàng"
Output: {"actions": [{"action": "open_app", "name": "chrome"}, {"action": "search_web", "query": "giá vàng"}]}

Input: "mở chrome, mở word"
Output: {"actions": [{"action": "open_app", "name": "chrome"}, {"action": "open_app", "name": "word"}]}

Input: "đặt âm lượng 50%"
Output: {"actions": [{"action": "volume", "percentage": 50}]}

Input: "chụp màn hình rồi tắt máy"
Output: {"actions": [{"action": "screenshot"}, {"action": "shutdown"}]}
"""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout: float = 5.0,
        memory_file: Optional[str] = None,
        phonetics_file: Optional[str] = None,
    ) -> None:
        """
        Khởi tạo bộ não trợ lý ảo.

        Args:
            ollama_url: Đường dẫn gốc tới dịch vụ Ollama (mặc định: http://localhost:11434).
            model: Tên mô hình LLM chạy trên Ollama (mặc định: llama3.2).
            timeout: Thời gian chờ phản hồi tối đa từ LLM (giây).
            memory_file: Đường dẫn tùy chọn tới file memory.json.
            phonetics_file: Đường dẫn tùy chọn tới file learned_phonetics.json.
        """
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.memory = MemoryManager(filepath=memory_file)

        # Quản lý file learned_phonetics.json (Tự học từ lóng / phiên âm)
        if phonetics_file is None:
            from utils import get_data_path
            self.phonetics_file = Path(get_data_path("learned_phonetics.json"))
        else:
            self.phonetics_file = Path(phonetics_file)

        # Tạo file learned_phonetics.json nếu chưa tồn tại
        if not self.phonetics_file.exists():
            try:
                with open(self.phonetics_file, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
            except Exception as exc:
                print(f"[Brain Cảnh báo] Không thể khởi tạo file {self.phonetics_file.name}: {exc}")

        # Khởi tạo bản đồ fuzzy_map động trong RAM (kết hợp từ điển tĩnh và từ đã tự học)
        self.fuzzy_map: Dict[str, str] = dict(self.FUZZY_MAP)
        if self.phonetics_file.exists():
            try:
                with open(self.phonetics_file, "r", encoding="utf-8") as f:
                    learned_data = json.load(f)
                    if isinstance(learned_data, dict):
                        clean_learned = {
                            str(k).strip().lower(): str(v).strip().lower()
                            for k, v in learned_data.items()
                        }
                        self.fuzzy_map.update(clean_learned)
                        if clean_learned:
                            print(f"[Brain] Đã nạp {len(clean_learned)} từ phiên âm tự học từ {self.phonetics_file.name}")
            except Exception as exc:
                print(f"[Brain Cảnh báo] Lỗi khi nạp file {self.phonetics_file.name}: {exc}")

    def _save_learned_word(self, raw_word: str, app_name: str) -> None:
        """
        Lưu cặp từ lóng/phiên âm (raw_word -> app_name) vào file learned_phonetics.json
        và cập nhật ngay lập tức vào self.fuzzy_map trong RAM.
        Đảm bảo an toàn tuyệt đối với try-except để không bao giờ bị crash app.
        """
        try:
            raw_clean = str(raw_word).strip().lower()
            app_clean = str(app_name).strip().lower()
            if not raw_clean or not app_clean:
                return

            # BẢO VỆ CHỐNG LƯU NHẦM APP CHUẨN:
            if raw_clean in self.WHITELIST:
                print(f"[Brain Cảnh báo] '{raw_clean}' là app chuẩn trong Whitelist, bỏ qua không lưu làm từ lóng.")
                return

            if raw_clean in self.FUZZY_MAP and self.FUZZY_MAP[raw_clean] != app_clean:
                print(f"[Brain Cảnh báo] '{raw_clean}' đã được định nghĩa chuẩn trong FUZZY_MAP ('{self.FUZZY_MAP[raw_clean]}'), không ghi đè.")
                return

            # Cập nhật ngay lập tức vào RAM
            self.fuzzy_map[raw_clean] = app_clean

            # Đọc và lưu lại vào file learned_phonetics.json
            current_data = {}
            if self.phonetics_file.exists():
                try:
                    with open(self.phonetics_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            current_data = loaded
                except Exception:
                    current_data = {}

            current_data[raw_clean] = app_clean

            # Ghi an toàn qua file tạm rồi replace
            temp_path = self.phonetics_file.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.phonetics_file)

            print(f"[Brain: TỰ HỌC] Đã ghi nhớ từ lóng '{raw_clean}' là app '{app_clean}' cho lần sau.")
        except Exception as exc:
            print(f"[Brain Cảnh báo] Lỗi khi lưu từ học được vào {self.phonetics_file.name}: {exc}")

    def _correct_search_query(self, query: str) -> str:
        """
        Chuẩn hóa và sửa lỗi nghe nhầm (STT artifacts) trong từ khóa tìm kiếm.
        NGUYÊN TẮC:
        - Nếu câu lệnh tìm kiếm đã có nghĩa và đúng chính tả, BẮT BUỘC giữ nguyên văn 100%.
        - CHỈ sửa lỗi nếu cụm từ đó là từ vô nghĩa hoặc nghe nhầm rõ ràng do STT (ví dụ: 'giớn vông' -> 'giá vàng').
        """
        if not query:
            return ""

        cleaned = query.strip()
        lower_q = cleaned.lower()

        # 1. Khớp chính xác toàn bộ query với bảng sửa lỗi hoặc từ điển chủ đề tìm kiếm
        if lower_q in self.FUZZY_SEARCH_CORRECTIONS:
            return self.FUZZY_SEARCH_CORRECTIONS[lower_q]
        if lower_q in self.fuzzy_map and self.fuzzy_map[lower_q] in self.SEARCH_TOPICS:
            return self.fuzzy_map[lower_q]

        # 2. Thay thế cụm từ con (substring) theo thứ tự từ dài đến ngắn
        result = cleaned
        sorted_corrections = sorted(
            self.FUZZY_SEARCH_CORRECTIONS.items(),
            key=lambda x: len(x[0]),
            reverse=True
        )
        for wrong, right in sorted_corrections:
            pattern = re.compile(rf"(?<!\w){re.escape(wrong)}(?!\w)", re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(right, result)

        return result.strip()

    def _fast_path(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """
        FAST PATH: Sử dụng biểu thức chính quy (Regex) kết hợp từ điển FUZZY_MAP.
        - Bắt nhanh mọi câu lệnh tìm kiếm ("tìm kiếm", "tìm", "tra cứu", "google", "tìm giúp tôi"...)
          và trích xuất query tức thì (<1ms), không cần gọi LLM, bảo toàn 100% nguyên văn.
        - Nếu câu nói chứa các từ nối (" và ", " rồi ", " sau đó ", " tiếp theo ") hoặc có dấu phẩy ","
          đi kèm hành động khác: chuyển sang SLOW PATH (LLM) phân tách nhiều action.
        - Nếu sau khi map vẫn không khớp Whitelist, chuyển sang Slow Path (LLM) để đoán thay vì chặn.
        """
        if not text:
            return None

        raw_cleaned = text.strip().rstrip(".!?;:")
        cleaned = raw_cleaned.lower()

        # 1. FAST PATH TỔNG QUÁT CHO MỌI CÂU TÌM KIẾM:
        # Bắt mọi câu bắt đầu bằng: "tìm kiếm", "tìm", "kiếm", "tra cứu", "tra", "google", "search"
        match_search = re.match(
            r"^(?:tìm\s+kiếm|tìm|kiếm|tra\s+cứu|tra|google|search)(?:\s+(?:giúp\s+tôi|giúp\s+em|hộ\s+tôi|giúp|hộ))?\s+(.+)$",
            raw_cleaned,
            re.IGNORECASE
        )
        if match_search:
            raw_query = match_search.group(1).strip()
            # Kiểm tra xem có phải câu lệnh ghép kèm hành động thứ hai không (ví dụ: 'tìm giá vàng rồi tắt máy', 'tìm bitcoin và mở chrome')
            has_action_after = bool(
                re.search(
                    r"(?:,|\s+(?:và|rồi|sau\s+đó|tiếp\s+theo|đồng\s+thời|cùng\s+với))\s*(?:mở|mỡ|bật|chạy|khởi\s+động|tắt|đóng|thoát|chụp|khóa|khoá|restart|reboot)\b",
                    raw_query,
                    re.IGNORECASE
                )
            )
            if not has_action_after and raw_query:
                # Bảo toàn nguyên văn 100% khi có nghĩa, chỉ sửa nếu STT nghe nhầm từ vô nghĩa
                clean_query = self._correct_search_query(raw_query)
                return [{"action": "search_web", "query": clean_query}]

        # 1b. TÌM KIẾM THEO CHỦ ĐỀ TRỰC TIẾP (BẮT TRỌN VẸN CẢ ĐỊA DANH / TỪ PHÍA SAU):
        # Ví dụ: "thời tiết Đà Nẵng", "thời tiết Hà Nội", "giá vàng hôm nay", "tin tức bóng đá", "tỷ giá USD"
        match_direct_topic = re.match(
            r"^(thời\s+tiết|giá\s+vàng|tin\s+tức|tỷ\s+giá|tỉ\s+giá|chứng\s+khoán|bóng\s+đá)\b(?:\s+(.+))?$",
            raw_cleaned,
            re.IGNORECASE
        )
        if match_direct_topic:
            clean_query = self._correct_search_query(raw_cleaned)
            return [{"action": "search_web", "query": clean_query}]

        # 2. BỎ QUA FAST PATH nếu là câu lệnh kết hợp / đa hành động (có từ nối hoặc dấu phẩy)
        padded = f" {cleaned} "
        compound_conjunctions = [" và ", " rồi ", " sau đó ", " tiếp theo ", " đồng thời ", " cùng với "]
        if "," in text or any(conj in padded for conj in compound_conjunctions):
            print(f"[Brain: FAST PATH] Phát hiện lệnh kết hợp (có từ nối hoặc dấu phẩy) -> Bỏ qua Fast Path, chuyển sang SLOW PATH (LLM)...")
            return None

        # 3. Lệnh khóa máy / khóa màn hình (lock_screen)
        if re.match(r"^(?:khóa|khoá)\s+(?:máy|máy\s+tính|màn\s+hình|pc)$|^(?:lock|lock\s*screen|lock\s*pc)$", cleaned):
            return [{"action": "lock_screen"}]

        # 4. Lệnh khởi động lại máy (restart)
        if re.match(r"^(?:khởi\s+động\s+lại|restart|reboot)(?:\s+(?:lại\s+)?(?:máy|máy\s+tính|pc|hệ\s+thống))?$|^(?:restart|reboot)\s+(?:máy|pc)$", cleaned):
            return [{"action": "restart"}]

        # 5. Lệnh mở File Explorer / mở thư mục / từ lóng (open_explorer)
        if (
            re.match(r"^(?:mở|bật)\s+(?:file\s+explorer|explorer|thư\s+mục|tệp|ếp\s+lò\s+hương|ưu\s+phai|phai|phay\s+ếch(?:\s+pờ\s+lo\s+rơ)?|phai\s+ếch)$|^(?:file\s+explorer|thư\s+mục|ếp\s+lò\s+hương|ưu\s+phai|phai|phay\s+ếch(?:\s+pờ\s+lo\s+rơ)?|phai\s+ếch)$", cleaned)
            or cleaned in ("mở file explorer", "mở thư mục", "thư mục", "file explorer", "ếp lò hương", "ưu phai", "phai", "mở ếp lò hương", "mở ưu phai", "mở phai", "phay ếch", "phay ếch pờ lo rơ", "phai ếch")
        ):
            return [{"action": "open_explorer"}]

        # 5b. Lệnh mở ổ đĩa (open_drive): "mở ổ d", "mở ổ c", "mở ổ đĩa d", "ổ d", "ổ c"
        match_drive = re.match(
            r"^(?:mở|bật|vào|truy\s+cập)?\s*(?:ổ|ổ\s+đĩa)\s+([a-zA-Z])$",
            cleaned
        )
        if match_drive:
            drive_letter = match_drive.group(1).upper()
            return [{"action": "open_drive", "drive": drive_letter}]

        # 5c. Lệnh mở thư mục (open_folder): "mở bít trơ", "mở ảnh", "mở đao lốt", "mở downloads", "mở tài liệu"...
        match_folder = re.match(
            r"^(?:mở|bật|vào)\s+(?:thư\s+mục\s+)?(bít\s+trơ|bít\s+thơ|pic\s+trơ|pictures|ảnh|hình\s+ảnh|đao\s+lốt|đao\s+nốt|đao\s+lát|downloads|tải\s+về|tải\s+xuống|documents|tài\s+liệu|đốc\s+cu\s+mần|desktop|màn\s+hình\s+chính|music|nhạc|videos|video)$",
            cleaned
        )
        if match_folder:
            raw_f = match_folder.group(1).strip()
            folder_target = self.fuzzy_map.get(raw_f, raw_f)
            return [{"action": "open_folder", "folder": folder_target}]

        # 6. Khớp trực tiếp nguyên câu với từ lóng trong fuzzy_map (ví dụ: "vỡ giả lô", "giớn vông", "thời tiếc", "bít trơ", "đao lốt")
        if cleaned in self.fuzzy_map:
            target = self.fuzzy_map[cleaned]
            if target in self.FOLDER_TARGETS:
                return [{"action": "open_folder", "folder": target}]
            if target in ("explorer", "thư mục"):
                return [{"action": "open_explorer"}]
            if target in self.SEARCH_TOPICS:
                return [{"action": "search_web", "query": target}]
            if target in self.WHITELIST:
                return [{"action": "open_app", "name": target}]

        # 7. Lệnh xem thời tiết / xem giá vàng nhanh (ví dụ: "xem thời tiết Đà Nẵng", "xem giá vàng", "kiểm tra giá vàng")
        match_xem = re.match(r"^(?:xem|kiểm\s+tra)\s+(.+)$", raw_cleaned, re.IGNORECASE)
        if match_xem:
            topic_candidate = match_xem.group(1).strip()
            clean_query = self._correct_search_query(topic_candidate)
            return [{"action": "search_web", "query": clean_query}]

        # 8. Lệnh chụp màn hình
        if re.match(r"^(?:chụp|chụp lại|lấy)\s+(?:ảnh\s+)?màn\s+hình$|^(?:screenshot|screen\s*shot)$", cleaned):
            return [{"action": "screenshot"}]

        # 9. Lệnh tắt máy
        if re.match(r"^(?:tắt|shutdown)\s+(?:máy|máy\s+tính|pc)$", cleaned):
            return [{"action": "shutdown"}]

        # 10. Lệnh bật/tắt Wi-Fi
        if re.search(r"\b(?:bật|mở|kết\s*nối)\s*(?:wifi|wi-fi|mạng\s*wifi|mạng\s*wi-fi)\b", cleaned):
            return [{"action": "wifi", "state": "on"}]
        if re.search(r"\b(?:tắt|đóng|ngắt)\s*(?:wifi|wi-fi|mạng\s*wifi|mạng\s*wi-fi)\b", cleaned):
            return [{"action": "wifi", "state": "off"}]

        # 11. Lệnh bật/tắt Bluetooth
        if re.search(r"\b(?:bật|mở|kết\s*nối)\s*(?:bluetooth|búp\s*tút|bờ\s*lu\s*tút)\b", cleaned):
            return [{"action": "bluetooth", "state": "on"}]
        if re.search(r"\b(?:tắt|đóng|ngắt)\s*(?:bluetooth|búp\s*tút|bờ\s*lu\s*tút)\b", cleaned):
            return [{"action": "bluetooth", "state": "off"}]

        # 12. KIỂM TRA ĐỘ SÁNG MÀN HÌNH (BRIGHTNESS): Có chữ "sáng" -> brightness
        has_brightness_keyword = bool(re.search(r"\b(?:độ\s*sáng|ánh\s*sáng|sáng|màn\s*hình\s*sáng)\b", cleaned))

        if has_brightness_keyword:
            # Tìm phần trăm nếu có (ví dụ: "tăng độ sáng 20%", "độ sáng 50%", "giảm độ sáng 10%")
            match_bright_pct = re.search(r"(\d{1,3})\s*(?:%|phần\s*trăm)?", cleaned)
            pct_val = int(match_bright_pct.group(1)) if match_bright_pct else None

            is_up = bool(re.search(r"\b(?:tăng|cho\s+sáng|sáng\s+hơn|lên)\b", cleaned))
            is_down = bool(re.search(r"\b(?:giảm|hạ|cho\s+tối|tối\s+hơn|bớt|xuống)\b", cleaned))

            if pct_val is not None and 0 <= pct_val <= 100:
                if is_up and not re.search(r"\b(?:lên\s+mức|ở\s+mức|đặt|chỉnh|cài)\b", cleaned):
                    return [{"action": "brightness", "direction": "up", "step": pct_val}]
                elif is_down and not re.search(r"\b(?:xuống\s+mức|ở\s+mức|đặt|chỉnh|cài)\b", cleaned):
                    return [{"action": "brightness", "direction": "down", "step": pct_val}]
                else:
                    return [{"action": "brightness", "percentage": pct_val}]
            else:
                if is_down:
                    return [{"action": "brightness", "direction": "down"}]
                else:
                    return [{"action": "brightness", "direction": "up"}]

        # 13. KIỂM TRA ÂM LƯỢNG HỆ THỐNG (VOLUME): Có chữ "âm lượng", "âm thanh", "tiếng" -> volume
        has_volume_keyword = bool(re.search(r"\b(?:âm\s*lượng|âm\s*thanh|tiếng|volume)\b", cleaned))
        if has_volume_keyword or re.search(r"\b(?:bật\s+to|cho\s+to|bật\s+nhỏ|cho\s+nhỏ)\b", cleaned):
            match_vol_pct = re.search(r"(\d{1,3})\s*(?:%|phần\s*trăm)?", cleaned)
            pct_val = int(match_vol_pct.group(1)) if match_vol_pct else None

            is_up = bool(re.search(r"\b(?:tăng|bật\s+to|cho\s+to|to\s+hơn|to|lên)\b", cleaned))
            is_down = bool(re.search(r"\b(?:giảm|hạ|bật\s+nhỏ|cho\s+nhỏ|nhỏ\s+hơn|nhỏ|xuống)\b", cleaned))

            if pct_val is not None and 0 <= pct_val <= 100:
                if is_up and not re.search(r"\b(?:lên\s+mức|ở\s+mức|đặt|chỉnh|cài)\b", cleaned):
                    return [{"action": "volume", "direction": "up", "step": pct_val / 100.0}]
                elif is_down and not re.search(r"\b(?:xuống\s+mức|ở\s+mức|đặt|chỉnh|cài)\b", cleaned):
                    return [{"action": "volume", "direction": "down", "step": pct_val / 100.0}]
                else:
                    return [{"action": "volume", "percentage": pct_val}]
            else:
                if is_down:
                    return [{"action": "volume", "direction": "down"}]
                elif is_up:
                    return [{"action": "volume", "direction": "up"}]

        # 13. Lệnh mở ứng dụng đơn lẻ: "mở [tên app]", "mỡ [tên app]", "bật [tên app]", "vỡ [tên app]"
        match_open = re.match(
            r"^(?:mở|mỡ|vỡ|bật|khởi\s+động|chạy)\s+(?:ứng\s+dụng|phần\s+mềm|app|trình\s+duyệt)?\s*(.+)$",
            cleaned
        )
        if match_open:
            raw_app = match_open.group(1).strip()
            # Bước 1: Đưa qua fuzzy_map (kết hợp cả từ tĩnh và từ tự học)
            mapped_app = self.fuzzy_map.get(raw_app, raw_app)

            # Bước 2: Xử lý các trường hợp đặc biệt (explorer, folder, tìm kiếm theo chủ đề)
            if mapped_app in ("explorer", "thư mục"):
                return [{"action": "open_explorer"}]
            if mapped_app in self.FOLDER_TARGETS:
                return [{"action": "open_folder", "folder": mapped_app}]
            if mapped_app in self.SEARCH_TOPICS:
                return [{"action": "search_web", "query": mapped_app}]

            # FAST PATH: Trả về action open_app ngay lập tức mà không cần gọi LLM (tốc độ < 0.1s)
            # Hỗ trợ mở mọi ứng dụng Windows (tiktok, word, excel, capcut, zalo, telegram...)
            if mapped_app:
                return [{"action": "open_app", "name": mapped_app}]

        # 14. Lệnh đóng ứng dụng: "đóng [tên app]", "tắt [tên app]"
        match_close = re.match(
            r"^(?:đóng|tắt|thoát|dừng)\s+(?:ứng\s+dụng|phần\s+mềm|app)?\s*(.+)$",
            cleaned
        )
        if match_close:
            raw_app = match_close.group(1).strip()
            if raw_app in ("máy", "máy tính", "pc"):
                return [{"action": "shutdown"}]
            mapped_app = self.fuzzy_map.get(raw_app, raw_app)
            if mapped_app in self.WHITELIST:
                return [{"action": "close_app", "name": mapped_app}]
            else:
                return None

        return None


    def _parse_llm_json(self, response_text: str, original_text: str = "") -> List[Dict[str, Any]]:
        """
        Trích xuất và chuẩn hóa danh sách Action từ chuỗi phản hồi của LLM.
        """
        cleaned = response_text.strip()

        # Thử parse toàn bộ chuỗi JSON trực tiếp
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return self._validate_actions(data, original_text=original_text)
            if isinstance(data, dict):
                actions = data.get("actions", [data])
                return self._validate_actions(actions, original_text=original_text)
        except Exception:
            pass

        # Tìm kiếm khối markdown ```json ... ```
        code_block = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", cleaned, re.DOTALL)
        if code_block:
            try:
                data = json.loads(code_block.group(1))
                if isinstance(data, list):
                    return self._validate_actions(data, original_text=original_text)
                if isinstance(data, dict):
                    actions = data.get("actions", [data])
                    return self._validate_actions(actions, original_text=original_text)
            except Exception:
                pass

        # Tìm kiếm mảng JSON [ ... ] trong phản hồi
        array_match = re.search(r"\[\s*\{.*?\}\s*\]", cleaned, re.DOTALL)
        if array_match:
            try:
                data = json.loads(array_match.group(0))
                if isinstance(data, list):
                    return self._validate_actions(data, original_text=original_text)
            except Exception:
                pass

        # Tìm kiếm object {"actions": [ ... ]}
        obj_match = re.search(r"\{\s*\"actions\"\s*:\s*\[.*?\]\s*\}", cleaned, re.DOTALL)
        if obj_match:
            try:
                data = json.loads(obj_match.group(0))
                return self._validate_actions(data.get("actions", []), original_text=original_text)
            except Exception:
                pass

        return [{"action": "unknown"}]

    def _validate_actions(self, actions: Any, original_text: str = "") -> List[Dict[str, Any]]:
        """
        Đảm bảo đầu ra là List các dict hợp lệ có trường 'action'.
        Kiểm tra chặt chẽ tên app, chống tuyệt đối việc LLM bịa đặt tên ứng dụng lạ.
        Nếu app không nằm trong WHITELIST, lập tức chuyển thành {"action": "unknown"}.
        Đối với search_web, bảo toàn nguyên văn từ khóa người dùng nói.
        """
        if not isinstance(actions, list):
            return [{"action": "unknown"}]

        valid_list = []
        for item in actions:
            if isinstance(item, dict) and "action" in item:
                act = item.get("action")
                if act == "open_app":
                    raw_name = str(item.get("name") or item.get("app_name") or "").strip().lower()
                    # Chuẩn hóa tên app qua fuzzy_map (đã bao gồm từ tự học) nếu có
                    app_name = self.fuzzy_map.get(raw_name, raw_name)
                    # Nếu tên app sau chuẩn hóa vẫn không thuộc danh sách WHITELIST -> ép về unknown
                    if app_name not in self.WHITELIST:
                        print(f"[Brain: Chặn ảo giác LLM] Tên app '{raw_name}' không thuộc WHITELIST -> chuyển thành unknown")
                        valid_list.append({"action": "unknown"})
                        continue
                    item["name"] = app_name
                    item.pop("app_name", None)
                    valid_list.append(item)
                elif act == "close_app":
                    raw_name = str(item.get("name") or item.get("app_name") or "").strip().lower()
                    app_name = self.fuzzy_map.get(raw_name, raw_name)
                    if app_name not in self.WHITELIST:
                        print(f"[Brain: Chặn ảo giác LLM] Tên app đóng '{raw_name}' không thuộc WHITELIST -> chuyển thành unknown")
                        valid_list.append({"action": "unknown"})
                        continue
                    item["name"] = app_name
                    item.pop("app_name", None)
                    valid_list.append(item)
                elif act == "search_web":
                    query = str(item.get("query", "")).strip()

                    # Nếu LLM không sinh ra query, fallback trích xuất từ câu người dùng nói
                    if not query and original_text:
                        rgx = re.search(
                            r"(?:tìm\s+kiếm|tìm|tra\s+cứu|search|google|kiếm|định\s+giá)\s+(.+?)(?:\s+(?:và|rồi|sau\s+đó|tiếp\s+theo)\s+(?:mở|bật|chạy|khởi\s+động|chụp|tắt|đóng|khóa|restart)|$)",
                            original_text,
                            re.IGNORECASE,
                        )
                        if rgx:
                            query = rgx.group(1).strip()

                    # Chuẩn hóa qua _correct_search_query: giữ nguyên văn nếu có nghĩa, chỉ sửa STT artifacts
                    query = self._correct_search_query(query)
                    item["query"] = query
                    valid_list.append(item)
                elif act == "volume":
                    if "percentage" in item and item["percentage"] is not None:
                        try:
                            pct_val = float(str(item["percentage"]).replace("%", "").strip())
                            item["percentage"] = max(0, min(100, round(pct_val)))
                        except Exception:
                            item.pop("percentage", None)
                    valid_list.append(item)
                elif act == "brightness":
                    if "percentage" in item and item["percentage"] is not None:
                        try:
                            pct_val = float(str(item["percentage"]).replace("%", "").strip())
                            item["percentage"] = max(0, min(100, round(pct_val)))
                        except Exception:
                            item.pop("percentage", None)
                    if "step" in item and item["step"] is not None:
                        try:
                            item["step"] = int(str(item["step"]).replace("%", "").strip())
                        except Exception:
                            item["step"] = 10
                    valid_list.append(item)
                elif act in ("wifi", "bluetooth"):
                    state = str(item.get("state", "on")).strip().lower()
                    item["state"] = "on" if state in ("on", "enable", "enabled", "bật", "true", "1") else "off"
                    valid_list.append(item)
                elif act == "open_drive":
                    raw_drive = str(item.get("drive", "")).strip().upper()
                    match_d = re.search(r"([A-Z])", raw_drive)
                    if match_d:
                        item["drive"] = match_d.group(1)
                        valid_list.append(item)
                    else:
                        valid_list.append({"action": "unknown"})
                elif act == "open_folder":
                    raw_folder = str(item.get("folder") or item.get("name") or "").strip().lower()
                    folder_target = self.fuzzy_map.get(raw_folder, raw_folder)
                    item["folder"] = folder_target
                    item.pop("name", None)
                    valid_list.append(item)
                elif act in ("screenshot", "shutdown", "lock_screen", "restart", "open_explorer", "unknown"):
                    valid_list.append(item)
                else:
                    valid_list.append({"action": "unknown"})
            elif isinstance(item, str):
                if item in ("screenshot", "shutdown", "lock_screen", "restart", "open_explorer", "unknown"):
                    valid_list.append({"action": item})
                else:
                    valid_list.append({"action": "unknown"})

        if not valid_list or all(isinstance(a, dict) and a.get("action") == "unknown" for a in valid_list):
            return [{"action": "unknown"}]

        return valid_list

    def _extract_raw_app_names(self, text: str) -> List[str]:
        """
        Trích xuất từ gốc / từ lóng mà người dùng đã đọc sau các động từ mở/mỡ/bật/chạy/khởi động/vỡ...
        Hỗ trợ cả câu đơn và câu ghép nối ("mở đít cọc", "mở đít cọc và tìm giá vàng", "bật sốp ti").
        """
        cleaned = text.strip()
        pattern = r"(?:mở|mỡ|bật|chạy|khởi\s+động|vỡ)\s+(?:ứng\s+dụng|phần\s+mềm|app|trình\s+duyệt|cái|con)?\s*([^,\.;!?\n\r]+?)(?=\s+(?:và|rồi|sau\s+đó|tiếp\s+theo|đồng\s+thời|cùng\s+với)\s+|$|,)"
        matches = re.findall(pattern, cleaned, flags=re.IGNORECASE)
        results = []
        for m in matches:
            candidate = m.strip()
            # Bỏ các từ phụ đầu ngữ nếu còn sót
            candidate = re.sub(r"^(?:ứng\s+dụng|phần\s+mềm|app|trình\s+duyệt|cái|con)\s+", "", candidate, flags=re.IGNORECASE).strip()
            if candidate:
                results.append(candidate.lower())
        return results

    def _trigger_auto_learning(self, original_text: str, actions: List[Dict[str, Any]]) -> None:
        """
        Kích hoạt cơ chế TỰ HỌC khi LLM (SLOW PATH) suy luận thành công action open_app:
        Trích xuất từ gốc (raw_app) trong câu nói của người dùng và lưu vào learned_phonetics.json.

        Quy tắc an toàn chống gán sai ngữ cảnh:
        1. CÂU ĐƠN (Single Command):
           - Không chứa từ nối ('và', 'rồi', 'sau đó'...) và chỉ có 1 hành động open_app.
           - Trích xuất raw_app và kiểm tra tính hợp lệ trước khi lưu.
        2. CÂU GHÉP (Compound Sentence):
           - Bắt buộc từ lóng (raw_app) và tên app (app_name) phải nằm trong CÙNG MỘT CỤM/VẾ CỦA CÂU.
           - Nếu số lượng vế câu không khớp với số hành động hoặc có bất kỳ vế nào không thể tách
             chính xác 1-1, TẠM THỜI BỎ QUA việc tự học để tránh gán sai ngữ cảnh.
        3. BẢO VỆ TÊN APP CHUẨN (Whitelist Guard):
           - Tuyệt đối KHÔNG bao giờ lưu các tên app đã thuộc WHITELIST (chrome, edge, notepad...) làm từ lóng!
           - Tuyệt đối không ghi đè các từ đã có trong từ điển chuẩn FUZZY_MAP nếu trỏ tới app khác.
        """
        if not actions or not original_text:
            return

        open_actions = [
            act for act in actions
            if isinstance(act, dict) and act.get("action") == "open_app" and act.get("name") in self.WHITELIST
        ]
        if not open_actions:
            return

        # Kiểm tra từ nối báo hiệu câu ghép
        connecting_regex = r"\s+(?:và|rồi|sau\s+đó|tiếp\s+theo|đồng\s+thời|cùng\s+với)\s+|[,;]"
        has_connecting_words = bool(re.search(connecting_regex, original_text, flags=re.IGNORECASE))
        is_compound = has_connecting_words or len(actions) > 1

        # =========================================================================
        # TRƯỜNG HỢP 1: CÂU ĐƠN (Single Command)
        # =========================================================================
        if not is_compound:
            if len(open_actions) != 1:
                return

            target_app = open_actions[0].get("name", "").strip().lower()
            if not target_app or target_app not in self.WHITELIST:
                return

            raw_candidates = self._extract_raw_app_names(original_text)
            if len(raw_candidates) != 1:
                return

            raw_word = raw_candidates[0].strip().lower()
            if (
                raw_word
                and raw_word in original_text.lower()
                and raw_word != target_app
                and raw_word not in self.WHITELIST
                and (raw_word not in self.FUZZY_MAP or self.FUZZY_MAP[raw_word] == target_app)
            ):
                if self.fuzzy_map.get(raw_word) != target_app:
                    self._save_learned_word(raw_word, target_app)
            return

        # =========================================================================
        # TRƯỜNG HỢP 2: CÂU GHÉP (Compound Sentence)
        # =========================================================================
        # Tách câu thành các vế (clauses) theo từ nối hoặc dấu phẩy
        clauses = [
            c.strip()
            for c in re.split(connecting_regex, original_text, flags=re.IGNORECASE)
            if c.strip()
        ]

        # ĐIỀU KIỆN 3: Nếu số lượng vế không khớp với số lượng hành động -> câu quá phức tạp -> BỎ QUA
        if len(clauses) != len(actions):
            print(f"[Brain: Tự học] Bỏ qua câu ghép '{original_text}': số vế ({len(clauses)}) không khớp số hành động ({len(actions)}).")
            return

        # Duyệt từng cặp (clause, action) để đảm bảo raw_app và app_name nằm trong CÙNG MỘT VẾ CÂU
        for clause, act in zip(clauses, actions):
            if not isinstance(act, dict) or act.get("action") != "open_app":
                continue

            target_app = act.get("name", "").strip().lower()
            if not target_app or target_app not in self.WHITELIST:
                continue

            # ĐIỀU KIỆN 2: Trích xuất từ lóng CHỈ từ đúng vế câu này
            clause_candidates = self._extract_raw_app_names(clause)
            if len(clause_candidates) != 1:
                # Nếu vế này không có động từ mở (ví dụ 'discord') hoặc có nhiều hơn 1 ứng viên -> Bỏ qua
                continue

            raw_word = clause_candidates[0].strip().lower()

            # Bắt buộc từ lóng phải nằm trong CÙNG VẾ CÂU (clause)
            if raw_word not in clause.lower():
                continue

            # Tuyệt đối không lưu các app trong Whitelist làm từ lóng
            if raw_word in self.WHITELIST:
                continue

            # Không lưu nếu từ lóng giống hệt app_name
            if raw_word == target_app:
                continue

            # Không ghi đè từ điển chuẩn static nếu trỏ tới app khác
            if raw_word in self.FUZZY_MAP and self.FUZZY_MAP[raw_word] != target_app:
                continue

            if self.fuzzy_map.get(raw_word) != target_app:
                self._save_learned_word(raw_word, target_app)

    def _slow_path(self, text: str) -> List[Dict[str, Any]]:
        """
        SLOW PATH: Gửi câu lệnh tới Ollama để phân tích ngữ nghĩa,
        sửa lỗi chính tả và tách chuỗi hành động kết hợp.
        Tối ưu tốc độ với temperature=0.0 và num_predict ngắn (100 tokens).
        """
        if not text:
            return [{"action": "unknown"}]

        cleaned = text.strip().rstrip(".!?;:")

        # =====================================================================
        # VERBATIM QUERY PROTECTION (BẢO VỆ NGUYÊN VĂN CÂU TÌM KIẾM):
        # Nếu câu lệnh bắt đầu bằng "tìm", "kiếm", "tra cứu", "google",
        # hãy trích xuất CHÍNH XÁC phần text phía sau làm query, TUYỆT ĐỐI KHÔNG gọi LLM.
        # Chống LLM bịa đặt / bóp méo query (ví dụ: 'giởn giá vông hƹm nay').
        # =====================================================================
        match_verbatim = re.match(
            r"^(?:tìm\s+kiếm|tìm|kiếm|tra\s+cứu|tra|google|search)(?:\s+(?:giúp\s+tôi|giúp\s+em|hộ\s+tôi|giúp|hộ))?\s+(.+)$",
            cleaned,
            re.IGNORECASE
        )
        if match_verbatim:
            exact_query = match_verbatim.group(1).strip()
            # Kiểm tra xem có lệnh kết hợp phía sau không (ví dụ: 'và mở chrome', 'rồi tắt máy')
            split_match = re.split(
                r"\s+(?:và|rồi|sau\s+đó|tiếp\s+theo|đồng\s+thời|cùng\s+với)\s+(?=(?:mở|bật|chạy|tắt|đóng|chụp|khóa|restart))",
                exact_query,
                maxsplit=1,
                flags=re.IGNORECASE
            )
            if len(split_match) == 2:
                first_query = split_match[0].strip()
                second_cmd = split_match[1].strip()
                print(f"[Brain: SLOW PATH - Verbatim Protection] Trích xuất nguyên văn query '{first_query}' (KHÔNG gọi LLM)")
                actions = [{"action": "search_web", "query": first_query}]
                second_actions = self._fast_path(second_cmd) or self._slow_path(second_cmd)
                actions.extend([a for a in second_actions if a.get("action") != "unknown"])
                return actions if actions else [{"action": "unknown"}]
            else:
                print(f"[Brain: SLOW PATH - Verbatim Protection] Trích xuất nguyên văn query '{exact_query}' (KHÔNG gọi LLM)")
                return [{"action": "search_web", "query": exact_query}]

        chat_url = f"{self.ollama_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{self.SYSTEM_PROMPT}\n"
                        "BẮT BUỘC: Chỉ trả về JSON duy nhất, không thêm bất kỳ văn bản giải thích nào."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 100,  # Giới hạn số token đầu ra để LLM phản hồi nhanh nhất
            },
        }

        try:
            response = requests.post(chat_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            resp_json = response.json()
            content = resp_json.get("message", {}).get("content", "")
            actions = self._parse_llm_json(content, original_text=text)

            # BƯỚC 3: Kích hoạt cơ chế TỰ HỌC cho từ lóng / phiên âm
            self._trigger_auto_learning(text, actions)

            return actions

        except requests.exceptions.RequestException as exc:
            # Fallback an toàn nếu mất kết nối hoặc Ollama bị lỗi
            print(f"[Brain Cảnh báo] Không thể kết nối tới Ollama ({exc}). Fallback an toàn về unknown.")
            return [{"action": "unknown"}]
        except Exception as exc:
            print(f"[Brain Cảnh báo] Lỗi xử lý LLM ({exc}). Fallback về unknown.")
            return [{"action": "unknown"}]

    @staticmethod
    def _is_valid_actions(actions: Any) -> bool:
        """
        Kiểm tra danh sách actions có hợp lệ để lưu vào bộ nhớ không.
        Không lưu nếu rỗng hoặc toàn bộ là unknown.
        """
        if not actions or not isinstance(actions, list):
            return False
        return any(
            isinstance(act, dict) and act.get("action") not in (None, "unknown")
            for act in actions
        )

    def _match_phonetic_rapid(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """
        So khớp câu lệnh với từ điển phiên âm PHONETIC_DICT bằng RapidFuzz (>80%).
        Được gọi trước khi gọi LLM (Slow Path) để nhận diện tức thì tên ứng dụng.
        """
        if not text:
            return None

        cleaned = text.strip().lower().rstrip(".!?;:")

        # Kiểm tra xem có phải lệnh đóng/tắt không
        is_close = False
        candidate = cleaned

        match_close = re.match(r"^(?:đóng|tắt|thoát|dừng)\s+(?:ứng\s+dụng|phần\s+mềm|app)?\s*(.+)$", cleaned)
        match_open = re.match(r"^(?:mở|mỡ|vỡ|bật|khởi\s+động|chạy|vào)\s+(?:ứng\s+dụng|phần\s+mềm|app|trình\s+duyệt)?\s*(.+)$", cleaned)

        if match_close:
            is_close = True
            candidate = match_close.group(1).strip()
        elif match_open:
            is_close = False
            candidate = match_open.group(1).strip()

        best_score = 0.0
        best_target = None
        best_key = None

        for phonetic_key, target_app in self.PHONETIC_DICT.items():
            # Tính độ tương đồng bằng rapidfuzz
            score = float(fuzz.ratio(candidate, phonetic_key))
            score_partial = float(fuzz.partial_ratio(candidate, phonetic_key))
            effective_score = max(score, score_partial if len(candidate) > len(phonetic_key) else score)

            if effective_score > best_score:
                best_score = effective_score
                best_target = target_app
                best_key = phonetic_key

        if best_score > 80.0 and best_target:
            action_type = "close_app" if is_close else "open_app"
            print(f"[Brain: RapidFuzz Phonetics] Khớp '{candidate}' với phiên âm '{best_key}' -> app: '{best_target}' (score: {best_score:.1f}% > 80%)")
            return [{"action": action_type, "name": best_target}]

        return None

    def process(self, text: str) -> List[Dict[str, Any]]:
        """
        Xử lý văn bản đầu vào và trả về danh sách các action cần thực thi.

        Kiến trúc tích hợp 3 tầng:
        0. MEMORY CACHE (Bộ nhớ đệm): Kiểm tra câu lệnh đã từng xử lý trước đó.
           - Khớp chính xác 100% -> Trả về kết quả ngay (<1ms).
           - Khớp mờ (Fuzzy >= 85%) -> Tự động lấy kết quả và lưu biến thể mới.
        1. FAST PATH (Regex Rule-based): Xử lý tức thì các câu lệnh đơn lẻ quen thuộc.
        2. SLOW PATH (Ollama LLM): Xử lý ngôn ngữ tự nhiên sâu và tách câu lệnh kết hợp.

        Sau khi xử lý thành công (kết quả không phải unknown), tự động ghi nhớ vào memory.json.
        """
        if not text or not text.strip():
            return [{"action": "unknown"}]

        input_text = text.strip()

        # =====================================================================
        # BƯỚC 0: KIỂM TRA BỘ NHỚ ĐỆM (MEMORY CACHE)
        # =====================================================================
        # TUYỆT ĐỐI KHÔNG sử dụng Memory Cache nếu độ dài câu nói < 3 từ (ví dụ: "mở ổ", "mở do")
        # để chống khớp sai lệch ngữ cảnh. Phải đưa qua Fast Path hoặc LLM để xử lý chính xác.
        words = input_text.split()
        if len(words) < 3:
            print(f"[Brain: Bỏ qua Memory Cache] Câu nói quá ngắn ({len(words)} từ < 3 từ: '{input_text}') -> Chuyển thẳng tới Fast Path / LLM.")
        else:
            cached_result = self.memory.get(input_text)
            if cached_result is not None:
                cached_actions, matched_key, score = cached_result
                if score >= 0.999:
                    print(f"[Brain: MEMORY CACHE] Lấy từ bộ nhớ -> <1ms -> {cached_actions}")
                else:
                    pct = round(score * 100, 1)
                    print(f"[Brain: MEMORY CACHE (Fuzzy {pct}%)] Khớp với '{matched_key}' -> Lấy từ bộ nhớ (<1ms) -> {cached_actions}")
                return cached_actions

        # =====================================================================
        # BƯỚC 1: FAST PATH (Regex)
        # =====================================================================
        fast_actions = self._fast_path(input_text)
        if fast_actions is not None:
            print(f"[Brain: FAST PATH (Regex)] Khớp lệnh nhanh -> {fast_actions}")
            if self._is_valid_actions(fast_actions) and len(words) >= 3:
                self.memory.set(input_text, fast_actions)
                print(f"[Brain: MEMORY CACHE] Đã ghi nhớ câu lệnh: '{input_text}'")
            return fast_actions

        # =====================================================================
        # BƯỚC 1.5: RAPIDFUZZ SO KHỚP PHIÊN ÂM (>80%) TRƯỚC KHI GỌI LLM
        # =====================================================================
        phonetic_actions = self._match_phonetic_rapid(input_text)
        if phonetic_actions is not None:
            print(f"[Brain: RAPIDFUZZ (>80%)] Khớp phiên âm tiếng Anh -> {phonetic_actions}")
            if self._is_valid_actions(phonetic_actions) and len(words) >= 2:
                self.memory.set(input_text, phonetic_actions)
                print(f"[Brain: MEMORY CACHE] Đã ghi nhớ câu lệnh: '{input_text}'")
            return phonetic_actions

        # =====================================================================
        # BƯỚC 2: SLOW PATH (Ollama LLM)
        # =====================================================================
        print(f"[Brain: SLOW PATH (LLM)] Đang phân tích với Ollama ({self.model})...")
        t0 = time.time()
        slow_actions = self._slow_path(input_text)
        duration = round(time.time() - t0, 2)
        print(f"[Brain: SLOW PATH (LLM)] Hoàn thành trong {duration}s -> {slow_actions}")

        if self._is_valid_actions(slow_actions) and len(words) >= 3:
            self.memory.set(input_text, slow_actions)
            print(f"[Brain: MEMORY CACHE] Đã ghi nhớ câu lệnh: '{input_text}'")

        return slow_actions


# Khối mã chạy thử nghiệm với các câu lệnh mẫu
if __name__ == "__main__":
    print("=" * 65)
    print("  KIỂM TRA BỘ NÃO TRỢ LÝ ẢO (BRAIN VỚI MEMORY CACHE)")
    print("=" * 65)

    # Sử dụng file memory.json cho phiên test
    brain = Brain(ollama_url="http://localhost:11434", model="llama3.2")

    test_samples = [
        # --- Nhóm 1: Fast Path Tổng quát cho Mọi Câu Tìm Kiếm (Giữ nguyên văn 100%, <1ms) ---
        "Tìm kiếm thời tiết",
        "Tìm giá bitcoin",
        "Tra cứu bảng xếp hạng bóng đá",
        "Tìm giúp tôi công thức làm bánh mì",
        "Google thời tiết Hà Nội",

        # --- Nhóm 2: Từ điển dự phòng cho các chủ đề tìm kiếm nghe nhầm (FUZZY_MAP & FUZZY_SEARCH_CORRECTIONS) ---
        "giớn vông",              # -> search_web "giá vàng" (<1ms)
        "thời tiếc",              # -> search_web "thời tiết" (<1ms)
        "tìm kiếm giớn vông",     # -> search_web "giá vàng" (<1ms)
        "tin tứt",                # -> search_web "tin tức" (<1ms)
        "tỷ dá",                  # -> search_web "tỷ giá" (<1ms)
        "bóng dá",                # -> search_web "bóng đá" (<1ms)

        # --- Nhóm 3: Fast Path & Phiên âm tiếng Anh (FUZZY_MAP mở rộng) ---
        "mở đít cọt",             # discord
        "mở git hắp",             # github
        "mở sờ pốt ti phai",      # spotify
        "mở mai cờ rô sốp sờ to", # microsoft store
        "mở phay ếch",            # explorer
        "mở sét tình",            # settings
        "mở ếch xen",             # excel
        "mở quớt",                # word
        "mở xi em đê",            # cmd
        "mở tê lê gram",          # telegram
        "vỡ giả lô",              # zalo
        "đặt âm lượng 50%",

        # --- Nhóm 4: Kiểm thử ghi nhớ và tái sử dụng qua Memory Cache ---
        "mở chờ rôm",             # Lần 1: Lưu vào memory
        "mở chờ rôm",             # Lần 2: Lấy tức thì từ Memory Cache (<1ms)

        # --- Nhóm 5: Unknown / Chống ảo giác (Không lưu vào memory) ---
        "Hôm nay trời đẹp quá bạn ơi",
        "Hôm nay đợi đại tế",
    ]

    print("\n--- BẮT ĐẦU CHẠY THỬ NGHIỆM CÁC CÂU LỆNH MẪU ---\n")
    for sample in test_samples:
        print(f"Input: \"{sample}\"")
        actions = brain.process(sample)
        print(f"Result JSON: {json.dumps(actions, ensure_ascii=False)}")
        print("-" * 50)

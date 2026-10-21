"""
Module: memory_manager.py
Mục đích: Quản lý bộ nhớ đệm (Memory Cache) cho Trợ lý ảo VoicePilot.
Chức năng:
    - Lưu trữ các cặp key-value (Câu lệnh người dùng -> Danh sách actions) vào memory.json.
    - Tự động tạo file nếu chưa tồn tại; xử lý an toàn khi file json bị hỏng (corrupted).
    - Hỗ trợ tìm kiếm chính xác (Exact Match) với độ trễ < 1ms.
    - Hỗ trợ tìm kiếm mờ (Fuzzy Matching >= 85%) qua rapidfuzz/difflib, tự động học và lưu câu lệnh mới.
"""

import difflib
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Đảm bảo in tiếng Việt có dấu không bị lỗi UnicodeEncodeError trên Console Windows
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


class MemoryManager:
    """
    Lớp quản lý bộ nhớ đệm câu lệnh của Trợ lý ảo.
    """

    DEFAULT_SIMILARITY_THRESHOLD: float = 0.85  # Ngưỡng tương đồng tối thiểu: 85%

    def __init__(
        self,
        filepath: Optional[str] = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        """
        Khởi tạo MemoryManager.

        Args:
            filepath: Đường dẫn tới file memory.json (mặc định: cùng thư mục với module).
            similarity_threshold: Ngưỡng độ tương đồng fuzzy matching (mặc định 0.85 = 85%).
        """
        if filepath is None:
            from utils import get_data_path
            self.filepath = Path(get_data_path("memory.json"))
        else:
            self.filepath = Path(filepath)

        self.similarity_threshold = similarity_threshold
        self._lock = threading.Lock()
        self.cache: Dict[str, List[Dict[str, Any]]] = {}

        # Tải bộ nhớ từ file khi khởi động
        self._load_memory()

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Chuẩn hóa chuỗi câu lệnh:
        - Viết thường.
        - Cắt bỏ khoảng trắng thừa và dấu câu ở hai đầu.
        - Gom các khoảng trắng liên tiếp thành 1 dấu cách đơn.
        """
        if not text:
            return ""
        cleaned = text.strip().lower().rstrip(".!?,;:")
        return re.sub(r"\s+", " ", cleaned)

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """
        Tính độ tương đồng giữa hai chuỗi từ 0.0 đến 1.0.
        Ưu tiên rapidfuzz (tốc độ cao), fallback về difflib.SequenceMatcher.
        """
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        if HAS_RAPIDFUZZ:
            return fuzz.ratio(s1, s2) / 100.0
        return difflib.SequenceMatcher(None, s1, s2).ratio()

    def _load_memory(self) -> None:
        """
        Đọc dữ liệu từ file memory.json vào bộ nhớ RAM.
        Nếu file chưa tồn tại -> tự tạo file rỗng {}.
        Nếu file JSON bị lỗi định dạng (do copy paste đè file) -> tự động ghi đè lại file rỗng {}
        thay vì văng lỗi (Crash) app.
        """
        with self._lock:
            if not self.filepath.exists():
                print(f"[MemoryManager] File '{self.filepath.name}' chưa tồn tại. Đang tạo mới...")
                self.cache = {}
                self._overwrite_with_empty()
                return

            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()

                # Nếu file rỗng (0 bytes) -> nạp dict rỗng và chuẩn hóa thành {}
                if not content:
                    self.cache = {}
                    self._overwrite_with_empty()
                    return

                data = json.loads(content)
                if isinstance(data, dict):
                    self.cache = data
                    print(f"[MemoryManager] Đã tải thành công {len(self.cache)} câu lệnh từ '{self.filepath.name}'.")
                else:
                    raise ValueError("Dữ liệu trong memory.json không phải là dict.")

            except (json.JSONDecodeError, ValueError, UnicodeDecodeError, Exception) as err:
                print(f"[MemoryManager: CẢNH BÁO] File '{self.filepath.name}' bị lỗi định dạng ({err})!")
                print(f"[MemoryManager] Tự động ghi đè lại thành file rỗng '{{}}' để chống crash app.")

                # Sao lưu file lỗi (nếu có thể) để người dùng không mất dữ liệu cũ
                try:
                    timestamp = int(time.time())
                    backup_path = self.filepath.with_suffix(f".corrupt_{timestamp}.bak")
                    shutil.copy2(self.filepath, backup_path)
                except Exception:
                    pass

                self.cache = {}
                self._overwrite_with_empty()

    def _overwrite_with_empty(self) -> None:
        """Ghi đè file memory.json thành file rỗng {} một cách an toàn."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                f.write("{\n}")
                f.flush()
                os.fsync(f.fileno())
        except Exception as exc:
            print(f"[MemoryManager: Cảnh báo ghi đè rỗng]: {exc}")
            try:
                self._save_memory_unlocked()
            except Exception:
                pass

    def _save_memory_unlocked(self) -> None:
        """
        Ghi dữ liệu self.cache xuống đĩa một cách an toàn (Atomic Write).
        Ghi ra file tạm thời trước rồi mới đổi tên để tránh hỏng file nếu bị ngắt đột ngột.
        """
        tmp_path = self.filepath.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Ghi đè nguyên tử lên file chính
            if tmp_path.exists():
                os.replace(tmp_path, self.filepath)

        except Exception as exc:
            print(f"[MemoryManager: Lỗi ghi file]: {exc}")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def get(self, text: str) -> Optional[Tuple[List[Dict[str, Any]], str, float]]:
        """
        Tìm kiếm câu lệnh trong bộ nhớ đệm:
        1. Kiểm tra khớp chính xác 100% (Exact match).
        2. Nếu không khớp chính xác, thực hiện so khớp mờ (Fuzzy matching >= similarity_threshold).
           Nếu tìm thấy kết quả mờ thỏa mãn, tự động học và lưu câu lệnh mới vào bộ nhớ.

        Args:
            text: Chuỗi câu lệnh của người dùng.

        Returns:
            Tuple[actions, matched_key, similarity_score] nếu tìm thấy, ngược lại trả về None.
        """
        cleaned = self.normalize_text(text)
        if not cleaned:
            return None

        with self._lock:
            # 1. KIỂM TRA KHỚP CHÍNH XÁC (Exact Match) -> < 1ms
            if cleaned in self.cache:
                return (self.cache[cleaned], cleaned, 1.0)

            # 2. KIỂM TRA SO KHỚP MỜ (Fuzzy Matching)
            if not self.cache:
                return None

            best_key: Optional[str] = None
            best_score: float = 0.0

            for cached_key in self.cache.keys():
                score = self._calculate_similarity(cleaned, cached_key)
                if score > best_score:
                    best_score = score
                    best_key = cached_key

            # Nếu độ tương đồng vượt ngưỡng (mặc định >= 85%)
            if best_key is not None and best_score >= self.similarity_threshold:
                matched_actions = self.cache[best_key]

                # TỰ ĐỘNG HỌC: Chỉ lưu câu lệnh mới biến thể này nếu action thực sự hợp lệ
                if self.is_valid_actions(matched_actions):
                    if cleaned not in self.cache:
                        self.cache[cleaned] = matched_actions
                        self._save_memory_unlocked()

                return (matched_actions, best_key, best_score)

        return None

    @staticmethod
    def is_valid_actions(actions: Any) -> bool:
        """
        Kiểm tra danh sách actions có chứa ít nhất một action hợp lệ hay không.
        Từ chối lưu nếu:
        - actions là None hoặc rỗng
        - actions không phải là list
        - Tất cả các phần tử trong actions đều là {"action": "unknown"} hoặc không có action hợp lệ.
        """
        if not actions or not isinstance(actions, list):
            return False
        return any(
            isinstance(act, dict) and act.get("action") not in (None, "unknown")
            for act in actions
        )

    def set(self, text: str, actions: List[Dict[str, Any]]) -> None:
        """
        Lưu câu lệnh và danh sách hành động tương ứng vào bộ nhớ đệm.

        Args:
            text: Chuỗi câu lệnh của người dùng.
            actions: Danh sách các action hợp lệ (chặn lưu nếu rỗng hoặc toàn bộ là unknown).
        """
        cleaned = self.normalize_text(text)
        if not cleaned:
            return

        # BẢO VỆ CHỐNG LƯU RÁC: Tuyệt đối không lưu nếu actions không có hành động hợp lệ
        if not self.is_valid_actions(actions):
            return

        with self._lock:
            self.cache[cleaned] = actions
            self._save_memory_unlocked()

    def clear(self) -> None:
        """Xóa toàn bộ bộ nhớ đệm (dùng khi kiểm thử hoặc làm mới)."""
        with self._lock:
            self.cache = {}
            self._save_memory_unlocked()


# Khối chạy thử nghiệm độc lập
if __name__ == "__main__":
    print("=" * 60)
    print("  KIỂM TRA MODULE BỘ NHỚ ĐỆM (MEMORY MANAGER)")
    print("=" * 60)

    test_file = "test_memory.json"
    if os.path.exists(test_file):
        os.remove(test_file)

    mgr = MemoryManager(filepath=test_file, similarity_threshold=0.85)

    # 1. Thêm câu lệnh mẫu vào memory
    print("\n--- 1. Lưu câu lệnh mẫu vào memory ---")
    mgr.set("mở chờ rôm", [{"action": "open_app", "name": "chrome"}])
    mgr.set("chụp màn hình", [{"action": "screenshot"}])
    print("Đã lưu: 'mở chờ rôm', 'chụp màn hình'")

    # 2. Thử truy vấn chính xác
    print("\n--- 2. Truy vấn chính xác 100% ---")
    res1 = mgr.get("mở chờ rôm")
    print(f"Input: 'mở chờ rôm' -> Kết quả: {res1}")

    # 3. Thử truy vấn mờ (Fuzzy matching)
    print("\n--- 3. Truy vấn mờ (Fuzzy >= 85%) ---")
    res2 = mgr.get("mở cờ rôm")  # Độ giống ~ 94.7%
    if res2:
        actions, matched_key, score = res2
        pct = round(score * 100, 1)
        print(f"Input: 'mở cờ rôm' -> Khớp với '{matched_key}' (Độ giống: {pct}%) -> {actions}")
    else:
        print("Không tìm thấy khớp mờ.")

    # 4. Kiểm tra xem 'mở cờ rôm' đã được tự động lưu vào memory chưa
    print("\n--- 4. Kiểm tra cơ chế tự động học ---")
    res3 = mgr.get("mở cờ rôm")
    print(f"Lần 2 gọi 'mở cờ rôm' (Exact match?): {res3}")

    # 5. Dọn dẹp file test
    if os.path.exists(test_file):
        os.remove(test_file)
        print("\nĐã dọn dẹp file test.")

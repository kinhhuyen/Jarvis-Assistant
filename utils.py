"""
Module: utils.py
Mục đích: Cung cấp tiện ích định vị đường dẫn động (Dynamic Path Resolution) cho Echo / Jarvis Assistant.
Chức năng:
    - Nhận biết môi trường chạy: Python script thông thường hoặc đóng gói PyInstaller (.exe).
    - resource_path(relative_path): Lấy đường dẫn tài nguyên tĩnh / read-only từ `sys._MEIPASS` khi đóng gói.
    - get_data_path(relative_path): Lấy đường dẫn file dữ liệu ghi (JSON memory, learned phonetics, offline learning).
      Khi đóng gói (.exe), tự động đồng bộ sang thư mục chứa file .exe để lưu trữ lâu dài giữa các phiên làm việc.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Union


def is_frozen() -> bool:
    """Kiểm tra ứng dụng có đang chạy dưới dạng file thực thi (.exe) được đóng gói bởi PyInstaller hay không."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_base_dir() -> Path:
    """
    Lấy thư mục gốc chứa tài nguyên tĩnh giải nén:
    - Khi đóng gói (.exe): Trỏ tới thư mục tạm `sys._MEIPASS`.
    - Khi chạy mã nguồn: Trỏ tới thư mục chứa file utils.py.
    """
    if is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def get_exe_dir() -> Path:
    """
    Lấy thư mục chứa file thực thi (.exe) hoặc thư mục dự án khi chạy mã nguồn.
    Dùng cho các file dữ liệu đọc/ghi cần lưu trữ liên tục (persistent data).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative_path: Union[str, Path]) -> str:
    """
    Lấy đường dẫn tuyệt đối đến file/thư mục tài nguyên:
    - Nếu chương trình đang chạy dưới dạng file .exe (sys._MEIPASS tồn tại),
      trả về đường dẫn tới thư mục tạm sys._MEIPASS.
    - Nếu không, trả về đường dẫn tương đối từ thư mục dự án hiện tại.

    Áp dụng cho:
    - Model Vosk (model/)
    - Model Wake Word openwakeword (.onnx)
    - File âm thanh, icon...
    """
    base = get_base_dir()
    resolved = base / relative_path
    return str(resolved)


def get_resource_path(relative_path: Union[str, Path]) -> str:
    """Bí danh (alias) tương thích với resource_path."""
    return resource_path(relative_path)


def get_data_path(relative_path: Union[str, Path], default_content: str = "{}") -> str:
    """
    Lấy đường dẫn tuyệt đối đến file dữ liệu đọc/ghi (JSON learning, memory, phonetics):
    - Khi đóng gói (.exe):
        + Đặt tại thư mục chứa file .exe để dữ liệu tự học không bị mất khi thoát ứng dụng.
        + Nếu file chưa tồn tại ở thư mục .exe, tự động sao chép file mẫu từ sys._MEIPASS sang.
        + Nếu cả 2 nơi đều chưa có, tự tạo mới với default_content.
    - Khi chạy mã nguồn:
        + Đặt tại thư mục dự án gốc.
        + Tự tạo mới với default_content nếu chưa tồn tại.
    """
    rel = Path(relative_path)
    if is_frozen():
        exe_dir = get_exe_dir()
        target = exe_dir / rel
        if not target.exists():
            bundled = get_base_dir() / rel
            if bundled.exists():
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(bundled), str(target))
                    return str(target)
                except Exception:
                    pass
            # Nếu không thể copy từ bundle, tạo file rỗng mặc định
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(default_content)
            except Exception:
                pass
        return str(target)
    else:
        target = get_base_dir() / rel
        if not target.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(default_content)
            except Exception:
                pass
        return str(target)

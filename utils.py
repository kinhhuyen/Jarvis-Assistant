"""
Module: utils.py
Mục đích: Cung cấp tiện ích đường dẫn động, ghi log xoay vòng, quản lý cấu hình và thiết bị âm thanh.
Chức năng:
    - Nhận biết môi trường chạy: Python script thông thường hoặc đóng gói PyInstaller (.exe).
    - resource_path(relative_path): Lấy đường dẫn tài nguyên tĩnh / read-only từ `sys._MEIPASS` khi đóng gói.
    - get_data_path(relative_path): Lấy đường dẫn file dữ liệu ghi (JSON memory, learned phonetics, offline learning, config).
    - setup_file_logging(log_filename): Thiết lập ghi log xoay vòng ra `teo_debug.log` để bắt bệnh từ xa khi ẩn console CMD.
    - Autostart Windows: Quản lý registry key Run trong HKCU để tự động khởi động cùng Windows.
    - Microphone Management: Quét danh sách micro, kiểm tra tương thích 16kHz và lưu cấu hình vào `config.json`.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Cờ và biến lưu trạng thái logging toàn cục
_LOGGING_INITIALIZED: bool = False
_LOGGER: Optional[logging.Logger] = None


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
    Lấy đường dẫn tuyệt đối đến file/thư mục tài nguyên tĩnh:
    - Khi chạy file .exe: Lấy từ thư mục tạm sys._MEIPASS.
    - Khi chạy source code: Lấy từ thư mục dự án hiện tại.
    """
    base = get_base_dir()
    resolved = base / relative_path
    return str(resolved)


def get_resource_path(relative_path: Union[str, Path]) -> str:
    """Bí danh (alias) tương thích với resource_path."""
    return resource_path(relative_path)


def get_data_path(relative_path: Union[str, Path], default_content: str = "{}") -> str:
    """
    Lấy đường dẫn tuyệt đối đến file dữ liệu đọc/ghi (JSON learning, memory, phonetics, config):
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


# =============================================================================
# LOGGING FILE SYSTEM (teo_debug.log - Bắt bệnh từ xa khi ẩn CMD)
# =============================================================================

class StreamToLogger:
    """
    Bộ chuyển hướng luồng dữ liệu (stdout/stderr) vào hệ thống logging.
    Đồng thời vẫn gửi dữ liệu tới luồng console gốc (nếu đang chạy trên terminal).
    """

    def __init__(self, log_fn, original_stream=None) -> None:
        self.log_fn = log_fn
        self.original_stream = original_stream

    def write(self, message: str) -> None:
        if self.original_stream is not None:
            try:
                self.original_stream.write(message)
                self.original_stream.flush()
            except Exception:
                pass
        text = message.strip()
        if text:
            try:
                self.log_fn(text)
            except Exception:
                pass

    def flush(self) -> None:
        if self.original_stream is not None:
            try:
                self.original_stream.flush()
            except Exception:
                pass


def setup_file_logging(
    log_filename: str = "teo_debug.log",
    max_bytes: int = 3 * 1024 * 1024,  # Giới hạn 3 MB mỗi file log
    backup_count: int = 2,              # Giữ tối đa 2 file cũ (.1, .2)
) -> str:
    """
    Cấu hình ghi log xoay vòng (RotatingFileHandler) ra file teo_debug.log.
    Chuyển hướng sys.stdout và sys.stderr để tự động bắt trọn vẹn:
    - Log debug của Vosk ("Đang nghe...", "ĐÃ KHỚP TỪ KHÓA...")
    - Log của STT Engine, Brain, Actions, Registry
    - Toàn bộ exception/traceback khi chạy file .exe (ẩn CMD).
    """
    global _LOGGING_INITIALIZED, _LOGGER
    log_path = get_exe_dir() / log_filename

    if _LOGGING_INITIALIZED and _LOGGER is not None:
        return str(log_path)

    logger = logging.getLogger("TeoAssistant")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    try:
        handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Chuyển hướng stdout và stderr
        sys.stdout = StreamToLogger(logger.info, sys.__stdout__)
        sys.stderr = StreamToLogger(logger.error, sys.__stderr__)

        _LOGGING_INITIALIZED = True
        _LOGGER = logger
        print(f"[Logging] ✓ Đã kích hoạt ghi log xoay vòng ra file: '{log_path}'")
    except Exception as exc:
        print(f"[Logging Cảnh báo] Không thể khởi tạo RotatingFileHandler: {exc}")

    return str(log_path)


# =============================================================================
# AUTOSTART WITH WINDOWS (Khởi động cùng Windows qua HKCU Run)
# =============================================================================

RUN_REG_PATH: str = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_APP_NAME: str = "TeoAssistant"


def is_autostart_enabled() -> bool:
    """Kiểm tra xem app đã được đăng ký khởi động cùng Windows trong HKCU hay chưa."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, REG_APP_NAME)
            return bool(val)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    """
    Bật hoặc tắt tự động khởi động cùng Windows bằng winreg.
    Trỏ chính xác tới file .exe khi đóng gói hoặc python script khi dev.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                if getattr(sys, "frozen", False):
                    exe_path = os.path.abspath(sys.executable)
                    cmd = f'"{exe_path}"'
                else:
                    exe_path = os.path.abspath(sys.executable)
                    script_path = os.path.abspath(sys.argv[0])
                    cmd = f'"{exe_path}" "{script_path}"'
                winreg.SetValueEx(key, REG_APP_NAME, 0, winreg.REG_SZ, cmd)
                print(f"[Autostart] ✓ Đã kích hoạt khởi động cùng Windows: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, REG_APP_NAME)
                    print("[Autostart] ✓ Đã hủy đăng ký khởi động cùng Windows.")
                except FileNotFoundError:
                    pass
            return True
        finally:
            winreg.CloseKey(key)
    except Exception as exc:
        print(f"[Autostart Lỗi] Thao tác Registry thất bại: {exc}")
        return False


# =============================================================================
# CONFIGURATION & MICROPHONE MANAGEMENT (Cấu hình và chọn Microphone)
# =============================================================================

def load_config() -> dict:
    """Đọc tệp cấu hình config.json (hoặc trả về dict rỗng)."""
    cfg_path = get_data_path("config.json", default_content="{}")
    try:
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        return data
    except Exception as exc:
        print(f"[Config Cảnh báo] Không thể đọc config.json ({exc}), dùng cấu hình mặc định.")
    return {}


def save_config(cfg: dict) -> bool:
    """Lưu tệp cấu hình config.json an toàn."""
    cfg_path = get_data_path("config.json", default_content="{}")
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        print(f"[Config Lỗi] Không thể lưu config.json: {exc}")
        return False


def get_available_microphones(filter_compatible: bool = True) -> List[Dict[str, Any]]:
    """
    Quét danh sách Microphone đang kết nối qua sounddevice.
    filter_compatible=True: Chỉ lấy các micro tương thích với chuẩn 16000Hz 1 channel int16.
    """
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        default_in = sd.default.device[0] if sd.default.device else None
        mics: List[Dict[str, Any]] = []

        for idx, dev in enumerate(devices):
            max_in = dev.get("max_input_channels", 0)
            if max_in > 0:
                is_compat = True
                if filter_compatible:
                    try:
                        sd.check_input_settings(
                            device=idx,
                            channels=1,
                            dtype="int16",
                            samplerate=16000,
                        )
                    except Exception:
                        is_compat = False

                if not filter_compatible or is_compat:
                    hostapi_name = ""
                    try:
                        hostapi_info = sd.query_hostapis(dev.get("hostapi", 0))
                        hostapi_name = hostapi_info.get("name", "")
                    except Exception:
                        pass

                    mics.append({
                        "index": idx,
                        "name": dev.get("name", f"Microphone {idx}"),
                        "hostapi": dev.get("hostapi", 0),
                        "hostapi_name": hostapi_name,
                        "channels": max_in,
                        "is_default": (idx == default_in),
                    })
        return mics
    except Exception as exc:
        print(f"[Audio Cảnh báo] Không thể truy vấn danh sách Micro: {exc}")
        return []


def get_configured_microphone() -> Tuple[Optional[int], str]:
    """
    Lấy thông tin Microphone được cấu hình từ config.json.
    Trả về: (device_index: Optional[int], device_display_name: str)
    - None: Dùng Micro mặc định của hệ thống.
    """
    cfg = load_config()
    saved_idx = cfg.get("microphone_index")
    saved_name = cfg.get("microphone_name")

    if saved_idx is None and not saved_name:
        return (None, "Mặc định hệ thống")

    mics = get_available_microphones(filter_compatible=False)
    if not mics:
        return (None, "Mặc định hệ thống")

    # 1. Tìm theo index trước nếu tên khớp
    if saved_idx is not None:
        for m in mics:
            if m["index"] == saved_idx and (not saved_name or m["name"] == saved_name):
                return (m["index"], m["name"])

    # 2. Nếu index bị đổi (cắm lại cổng USB), tìm theo tên
    if saved_name:
        for m in mics:
            if saved_name.lower() in m["name"].lower() or m["name"].lower() in saved_name.lower():
                return (m["index"], m["name"])

    return (None, "Mặc định hệ thống")


def set_configured_microphone(device_index: Optional[int], device_name: str) -> bool:
    """Lưu cấu hình Microphone đã chọn vào config.json."""
    cfg = load_config()
    cfg["microphone_index"] = device_index
    cfg["microphone_name"] = device_name
    print(f"[Config] Đã lưu cấu hình Microphone: index={device_index}, name='{device_name}'")
    return save_config(cfg)

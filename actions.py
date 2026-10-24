"""
Module: actions.py
Mục đích: Bộ thực thi hành động (Action Executor) cho Trợ lý ảo Windows.
Chức năng:
    - Nhận danh sách các action (list[dict]) từ brain.py và thực thi tuần tự.
    - Hỗ trợ các hành động:
        1. open_app: Mở ứng dụng Windows (chrome, edge, notepad, calc, word, excel, cmd...).
        2. search_web: Tìm kiếm Google bằng webbrowser.
        3. screenshot: Chụp màn hình và lưu vào thư mục Pictures bằng PIL.ImageGrab.
        4. shutdown: Hẹn giờ tắt máy tính bằng lệnh Windows shutdown.
        5. volume: Tăng/giảm âm lượng hệ thống bằng pycaw và comtypes.
        6. unknown: Thông báo không hiểu câu lệnh.
    - Mỗi action được bọc trong try/except độc lập để tránh gián đoạn chuỗi lệnh.
"""

import os
import re
import subprocess
import sys
import time
import urllib.parse
import webbrowser
import winreg
from pathlib import Path
from typing import Any, Dict, List, Optional

# Đảm bảo in tiếng Việt có dấu không bị lỗi UnicodeEncodeError trên Console Windows
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thư viện chụp màn hình
try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

# Thư viện điều khiển độ sáng màn hình
try:
    import screen_brightness_control as sbc
except ImportError:
    sbc = None

# Thư viện điều khiển âm lượng hệ thống Windows
try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except ImportError:
    AudioUtilities = None
    IAudioEndpointVolume = None

# Thư viện quản lý tiến trình hệ thống
try:
    import psutil
except ImportError:
    psutil = None

# Thư viện tự động tìm kiếm và mở ứng dụng đã cài đặt trên Windows (Lazy load khi cần)
_AppOpener = None
_AppOpener_loaded = False

def get_app_opener():
    global _AppOpener, _AppOpener_loaded
    if not _AppOpener_loaded:
        _AppOpener_loaded = True
        try:
            # Nếu file Data/data.json bị lỗi định dạng trước đó, dọn dẹp để AppOpener không crash
            data_json_path = os.path.join(os.getcwd(), "Data", "data.json")
            if os.path.exists(data_json_path):
                try:
                    with open(data_json_path, "r", encoding="utf-8") as _f:
                        json.load(_f)
                except Exception:
                    try:
                        os.remove(data_json_path)
                    except Exception:
                        pass
            import AppOpener as ao
            _AppOpener = ao
        except Exception:
            _AppOpener = None
    return _AppOpener


class ActionExecutor:
    """
    Lớp điều phối và thực thi tuần tự các hành động của Trợ lý ảo trên Windows.
    """

    # Bảng ánh xạ tên viết tắt/phổ biến sang tên file thực thi (.exe)
    APP_MAP: Dict[str, str] = {
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "edge": "msedge.exe",
        "msedge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "notepad": "notepad.exe",
        "ghi chú": "notepad.exe",
        "calc": "calc.exe",
        "calculator": "calc.exe",
        "máy tính": "calc.exe",
        "word": "winword.exe",
        "winword": "winword.exe",
        "microsoft word": "winword.exe",
        "excel": "excel.exe",
        "microsoft excel": "excel.exe",
        "cmd": "cmd.exe",
        "terminal": "cmd.exe",
        "command prompt": "cmd.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "task manager": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "spotify": "spotify.exe",
        "coccoc": "coccoc.exe",
        "cốc cốc": "coccoc.exe",
        "zalo": "zalo.exe",
        "telegram": "telegram.exe",
        "discord": "discord.exe",
        "github": "github.exe",
        "settings": "ms-settings:",
        "cài đặt": "ms-settings:",
        "microsoft store": "ms-windows-store:",
        "store": "ms-windows-store:",
        "tiktok": "tiktok.exe",
        "powerpoint": "powerpnt.exe",
        "capcut": "capcut.exe",
        "antigravity": "Antigravity IDE.exe",
        "revo uninstaller": "RevoUninPro.exe",
        "revo": "RevoUninPro.exe",
    }

    # Bảng đường dẫn tuyệt đối mặc định cho các app phổ biến khi không nằm trong PATH
    DEFAULT_APP_PATHS: Dict[str, str] = {
        "zalo": os.path.expandvars(r"%LOCALAPPDATA%\Programs\Zalo\Zalo.exe"),
        "telegram": os.path.expandvars(r"%APPDATA%\Telegram Desktop\Telegram.exe"),
        "discord": os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe"),
        "antigravity": r"D:\file\Antigravity IDE\Antigravity IDE.exe",
        "revo uninstaller": os.path.expandvars(r"%PROGRAMFILES%\VS Revo Group\Revo Uninstaller Pro\RevoUninPro.exe"),
        "revo": os.path.expandvars(r"%PROGRAMFILES%\VS Revo Group\Revo Uninstaller Pro\RevoUninPro.exe"),
    }

    def __init__(self, pictures_dir: Optional[Path] = None) -> None:
        """
        Khởi tạo ActionExecutor.

        Args:
            pictures_dir: Thư mục lưu ảnh chụp màn hình (mặc định: ~/Pictures).
        """
        if pictures_dir is None:
            self.pictures_dir = Path.home() / "Pictures"
        else:
            self.pictures_dir = Path(pictures_dir)

    def _get_volume_endpoint(self):
        """
        Khởi tạo hoặc lấy đối tượng IAudioEndpointVolume từ pycaw.
        Hỗ trợ tương thích cả phiên bản pycaw cũ và pycaw mới nhất.
        """
        if AudioUtilities is None:
            raise RuntimeError(
                "Chưa cài đặt thư viện điều khiển âm lượng! Vui lòng chạy: pip install pycaw comtypes"
            )

        devices = AudioUtilities.GetSpeakers()
        # Kiểm tra API pycaw phiên bản mới (có sẵn thuộc tính EndpointVolume)
        if hasattr(devices, "EndpointVolume"):
            return devices.EndpointVolume

        # Hỗ trợ API pycaw phiên bản cũ qua COM interface
        from ctypes import POINTER, cast
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    def _find_app_in_registry(self, exe_name: str) -> Optional[str]:
        """
        BƯỚC 1: Truy vấn đường dẫn file .exe của app trong Windows Registry.
        Kiểm tra khóa App Paths trong HKEY_LOCAL_MACHINE và HKEY_CURRENT_USER:
        - HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_name}
        - HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_name}
        """
        if not exe_name.endswith(".exe"):
            candidates = [f"{exe_name}.exe", exe_name]
        else:
            candidates = [exe_name]

        for candidate in candidates:
            for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                sub_key = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{candidate}"
                try:
                    with winreg.OpenKey(root_key, sub_key) as k:
                        raw_val, _ = winreg.QueryValueEx(k, "")
                        if raw_val:
                            clean_path = os.path.expandvars(str(raw_val).strip('"').strip())
                            if os.path.isfile(clean_path):
                                return clean_path
                except (FileNotFoundError, OSError):
                    continue
        return None

    def _find_in_candidate_paths(self, name: str, exe_name: str) -> Optional[str]:
        """
        BƯỚC 2: Kiểm tra danh sách các đường dẫn cài đặt khả thi trên các ổ đĩa (C:, D:...).
        Hỗ trợ tìm kiếm ứng dụng khi người dùng cài rải rác ở cả ổ C và ổ D.
        """
        candidate_paths: List[str] = []

        # 1. Thư mục hệ thống Windows
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        candidate_paths.append(os.path.join(system_root, "System32", exe_name))
        candidate_paths.append(os.path.join(system_root, exe_name))

        # 2. Danh sách các ổ đĩa khả dụng trên máy tính
        available_drives = [f"{d}:" for d in ("C", "D") if os.path.exists(f"{d}:")]

        # 3. Đường dẫn chuyên biệt cho các phần mềm phổ biến thường gặp
        known_subpaths: Dict[str, List[str]] = {
            "chrome": [r"Google\Chrome\Application\chrome.exe"],
            "google chrome": [r"Google\Chrome\Application\chrome.exe"],
            "edge": [r"Microsoft\Edge\Application\msedge.exe"],
            "msedge": [r"Microsoft\Edge\Application\msedge.exe"],
            "word": [
                r"Microsoft Office\root\Office16\WINWORD.EXE",
                r"Microsoft Office\Office16\WINWORD.EXE",
                r"Microsoft Office\Office15\WINWORD.EXE",
            ],
            "winword": [
                r"Microsoft Office\root\Office16\WINWORD.EXE",
                r"Microsoft Office\Office16\WINWORD.EXE",
            ],
            "excel": [
                r"Microsoft Office\root\Office16\EXCEL.EXE",
                r"Microsoft Office\Office16\EXCEL.EXE",
                r"Microsoft Office\Office15\EXCEL.EXE",
            ],
            "coccoc": [
                r"CocCoc\Browser\Application\browser.exe",
            ],
            "cốc cốc": [
                r"CocCoc\Browser\Application\browser.exe",
            ],
            "notepad++": [
                r"Notepad++\notepad++.exe",
            ],
            "spotify": [
                r"Spotify\Spotify.exe",
            ],
            "antigravity": [
                r"Antigravity IDE\Antigravity IDE.exe",
            ],
            "revo uninstaller": [
                r"VS Revo Group\Revo Uninstaller Pro\RevoUninPro.exe",
                r"VS Revo Group\Revo Uninstaller\RevoUnin.exe",
            ],
            "revo": [
                r"VS Revo Group\Revo Uninstaller Pro\RevoUninPro.exe",
                r"VS Revo Group\Revo Uninstaller\RevoUnin.exe",
            ],
        }

        # Quét theo subpaths chuyên biệt qua các ổ đĩa
        if name in known_subpaths:
            for sub in known_subpaths[name]:
                for drive in available_drives:
                    candidate_paths.append(os.path.join(drive, r"\Program Files", sub))
                    candidate_paths.append(os.path.join(drive, r"\Program Files (x86)", sub))
                candidate_paths.append(os.path.expandvars(rf"%LOCALAPPDATA%\{sub}"))
                candidate_paths.append(os.path.expandvars(rf"%APPDATA%\{sub}"))

        # 4. Quét tổng quát qua các thư mục gốc phổ biến trên từng ổ đĩa
        base_folders = [
            r"Program Files",
            r"Program Files (x86)",
            r"Games",
            r"Apps",
            r"Software",
            r"Programs",
        ]
        for drive in available_drives:
            for folder in base_folders:
                candidate_paths.append(os.path.join(drive, folder, exe_name))
                candidate_paths.append(os.path.join(drive, folder, name, exe_name))
                candidate_paths.append(os.path.join(drive, folder, name.capitalize(), exe_name))

        # Kiểm tra sự tồn tại của từng đường dẫn ứng viên
        for path in candidate_paths:
            if os.path.isfile(path):
                return path

        return None

    def _handle_open_app(self, action: Dict[str, Any]) -> None:
        """
        Xử lý mở ứng dụng theo thứ tự ưu tiên:
        1. Các ứng dụng đặc biệt (Settings, Microsoft Store, GitHub).
        2. Registry (App Paths) trong HKLM và HKCU.
        3. Đường dẫn mặc định (DEFAULT_APP_PATHS) hoặc candidate paths.
        4. Dự phòng AppOpener (cho app UWP/Store).
        5. PATH hệ thống.
        Nếu không tìm thấy, báo lỗi rõ ràng.
        """
        name = action.get("name", "").strip().lower()
        if not name:
            raise ValueError("Không có tên ứng dụng cần mở.")

        exe_name = self.APP_MAP.get(name, f"{name}.exe" if not name.endswith(".exe") else name)
        print(f"[Action] Đang tìm kiếm và mở ứng dụng: '{name}'...")

        # Hỗ trợ mở Cài đặt (Settings) Windows
        if name in ("settings", "cài đặt"):
            try:
                os.startfile("ms-settings:")
                print(f"[Action] [✓] Đã mở Cài đặt (Settings) hệ thống Windows.")
                return
            except Exception as exc:
                print(f"[Action] [!] Lỗi khi mở Settings: {exc}")

        # Hỗ trợ mở Microsoft Store
        if name in ("microsoft store", "store", "chợ ứng dụng"):
            try:
                os.startfile("ms-windows-store:")
                print(f"[Action] [✓] Đã mở Microsoft Store.")
                return
            except Exception as exc:
                print(f"[Action] [!] Lỗi khi mở Microsoft Store: {exc}")

        # Hỗ trợ mở GitHub
        if name == "github":
            github_desktop = os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop\GitHubDesktop.exe")
            if os.path.isfile(github_desktop):
                try:
                    os.startfile(github_desktop)
                    print(f"[Action] [✓] Đã mở GitHub Desktop.")
                    return
                except Exception:
                    pass
            try:
                webbrowser.open("https://github.com")
                print(f"[Action] [✓] Đã mở GitHub trên trình duyệt.")
                return
            except Exception as exc:
                print(f"[Action] [!] Lỗi khi mở GitHub: {exc}")

        # Hỗ trợ mở YouTube
        if name in ("youtube", "du túp", "du tu be"):
            try:
                webbrowser.open("https://www.youtube.com")
                print(f"[Action] [✓] Đã mở YouTube trên trình duyệt.")
                return
            except Exception as exc:
                print(f"[Action] [!] Lỗi khi mở YouTube: {exc}")

        # =========================================================================
        # BƯỚC 1: TRUY VẤN REGISTRY (App Paths)
        # =========================================================================
        registry_path = self._find_app_in_registry(exe_name)
        if registry_path and os.path.exists(registry_path):
            try:
                os.startfile(registry_path)
                print(f"[Action] [✓] Đã mở thành công '{name}' từ Registry: {registry_path}")
                return
            except Exception as exc:
                print(f"[Action] [!] Lỗi khi mở từ Registry '{registry_path}': {exc}")

        # =========================================================================
        # BƯỚC 2: KIỂM TRA ĐƯỜNG DẪN MẶC ĐỊNH / DANH SÁCH ỨNG VIÊN
        # =========================================================================
        default_path = self.DEFAULT_APP_PATHS.get(name)
        if default_path and os.path.isfile(default_path):
            try:
                os.startfile(default_path)
                print(f"[Action] [✓] Đã mở thành công '{name}' từ đường dẫn mặc định: {default_path}")
                return
            except Exception as exc:
                print(f"[Action] [!] Lỗi khi mở từ default path '{default_path}': {exc}")

        candidate_path = self._find_in_candidate_paths(name, exe_name)
        if candidate_path and os.path.exists(candidate_path):
            try:
                os.startfile(candidate_path)
                print(f"[Action] [✓] Đã mở thành công '{name}' từ đường dẫn ứng viên: {candidate_path}")
                return
            except Exception as exc:
                print(f"[Action] [!] Lỗi khi mở từ candidate path '{candidate_path}': {exc}")

        # =========================================================================
        # BƯỚC 3: DỰ PHÒNG APPOPENER (cho app UWP / Store - match_closest=False)
        # =========================================================================
        ao = get_app_opener()
        if ao is not None:
            try:
                available_apps = ao.give_appnames()
                exact_app_name = None
                for app_key in available_apps:
                    if app_key.strip().lower() == name:
                        exact_app_name = app_key
                        break

                if exact_app_name:
                    ao.open(exact_app_name, match_closest=False, throw_error=True)
                    print(f"[Action] [✓] Đã mở thành công '{exact_app_name}' qua AppOpener.")
                    return
                else:
                    ao.open(name, match_closest=False, throw_error=True)
                    print(f"[Action] [✓] Đã mở thành công '{name}' qua AppOpener.")
                    return
            except Exception as exc:
                print(f"[Action] [!] AppOpener không mở được '{name}': {exc}")

        # =========================================================================
        # BƯỚC 4: THỬ QUA PATH HỆ THỐNG
        # =========================================================================
        try:
            os.startfile(exe_name)
            print(f"[Action] [✓] Đã mở thành công '{name}' ({exe_name}) qua PATH hệ thống.")
            return
        except Exception:
            pass

        # =========================================================================
        # BƯỚC 5: TẬN DỤNG LỆNH "START" CỦA WINDOWS (Start Menu, Store Apps, AppData)
        # =========================================================================
        print(f"[Action] Đang thử khởi chạy qua lệnh 'start' của Windows: '{name}'...")
        start_candidates = [name]
        if exe_name and exe_name != name:
            start_candidates.append(exe_name)

        for cand in start_candidates:
            try:
                subprocess.Popen(
                    f'start "" "{cand}"',
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print(f"[Action Cảnh báo] Không thể chạy lệnh start cho '{cand}': {e}")

        # Chờ 2 giây để kiểm tra xem tiến trình có thực sự chạy hay không (bằng psutil)
        time.sleep(2.0)
        if self._is_process_running(name, exe_name):
            print(f"[Action] [✓] Đã mở thành công '{name}' qua lệnh 'start' của Windows.")
            return

        # NẾU SAU 2 GIÂY APP VẪN KHÔNG CHẠY: In cảnh báo ra log, không hiện popup
        app_display = name.capitalize()
        err_msg = f"Ứng dụng '{app_display}' chưa được cài đặt trên máy tính hoặc không thể khởi chạy."
        print(f"[Action Cảnh báo] [✗] {err_msg}")
        return

    def _is_process_running(self, name: str, exe_name: str = "") -> bool:
        """
        Kiểm tra xem tiến trình của ứng dụng có đang chạy trên Windows hay không bằng psutil.
        """
        if psutil is None:
            return False

        targets = set()
        if name:
            targets.add(name.lower().strip())
            targets.add(name.lower().replace(" ", ""))
        if exe_name:
            clean_exe = exe_name.lower().replace(".exe", "").strip()
            targets.add(clean_exe)
            targets.add(clean_exe.replace(" ", ""))

        try:
            for proc in psutil.process_iter(["name"]):
                try:
                    pname = (proc.info.get("name") or "").lower()
                    pbase = pname.replace(".exe", "")
                    for target in targets:
                        if target == pbase or target in pname:
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as exc:
            print(f"[Action Cảnh báo] Lỗi kiểm tra tiến trình psutil: {exc}")
        return False

    def _handle_close_app(self, action: Dict[str, Any]) -> None:
        """
        Xử lý đóng/tắt ứng dụng bằng lệnh taskkill.
        """
        name = action.get("name", "").strip().lower()
        if not name:
            raise ValueError("Không có tên ứng dụng cần đóng.")

        exe_name = self.APP_MAP.get(name, name)
        if not exe_name.endswith(".exe"):
            exe_name = f"{exe_name}.exe"

        print(f"[Action] Đang đóng ứng dụng: '{name}' ({exe_name})...")
        try:
            subprocess.run(
                ["taskkill", "/IM", exe_name, "/F"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[Action] [✓] Đã đóng ứng dụng: {name}")
        except Exception as exc:
            print(f"[Action] [!] Lỗi khi đóng ứng dụng {name}: {exc}")

    def _handle_search_web(self, action: Dict[str, Any]) -> None:
        """
        Xử lý tìm kiếm web qua Google bằng thư viện webbrowser.
        """
        query = action.get("query", "").strip()
        if not query:
            raise ValueError("Từ khóa tìm kiếm không được để trống.")

        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded_query}"

        print(f"[Action] Đang mở trình duyệt tìm kiếm: '{query}'...")
        webbrowser.open(search_url)
        print(f"[Action] [✓] Đã mở tìm kiếm Google thành công: {search_url}")

    def _handle_screenshot(self, action: Dict[str, Any]) -> None:
        """
        Xử lý chụp ảnh màn hình bằng PIL.ImageGrab và lưu vào thư mục Pictures.
        """
        if ImageGrab is None:
            raise RuntimeError("Chưa cài đặt thư viện Pillow! Vui lòng chạy: pip install Pillow")

        # Đảm bảo thư mục Pictures tồn tại
        self.pictures_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = self.pictures_dir / filename

        print(f"[Action] Đang chụp ảnh toàn màn hình...")
        screenshot = ImageGrab.grab()
        screenshot.save(filepath)
        print(f"[Action] [✓] Đã lưu ảnh chụp màn hình tại: {filepath}")

    def _handle_shutdown(self, action: Dict[str, Any]) -> None:
        """
        Xử lý tắt máy tính sau 10 giây.
        """
        print("[Action] [!] CẢNH BÁO: Lệnh tắt máy đã được kích hoạt!")
        print("[Action] [!] Máy tính sẽ tắt sau 10 giây. Để hủy lệnh, mở CMD gõ: shutdown /a")
        try:
            subprocess.Popen(
                ["shutdown", "/s", "/t", "10"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            print(f"[Action] [✗ Lỗi lệnh shutdown]: {exc}")

    def _handle_lock_screen(self, action: Dict[str, Any]) -> None:
        """
        Xử lý khóa màn hình máy tính (tương đương tổ hợp phím Windows + L).
        """
        print("[Action] Đang thực hiện khóa màn hình máy tính (Win+L)...")
        try:
            import ctypes
            res = ctypes.windll.user32.LockWorkStation()
            if res != 0:
                print("[Action] [✓] Đã khóa màn hình thành công.")
                return
        except Exception as exc:
            print(f"[Action] Cảnh báo ctypes: {exc}")

        # Fallback qua rundll32
        try:
            subprocess.Popen(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("[Action] [✓] Đã gửi lệnh khóa màn hình qua rundll32.")
        except Exception as exc:
            print(f"[Action] [✗ Lỗi khóa màn hình]: {exc}")

    def _handle_restart(self, action: Dict[str, Any]) -> None:
        """
        Xử lý khởi động lại máy tính (hẹn giờ 10 giây).
        """
        timeout = int(action.get("timeout", 10))
        print(f"[Action] [!] CẢNH BÁO: Lệnh khởi động lại máy tính đã được kích hoạt!")
        print(f"[Action] [!] Máy tính sẽ restart sau {timeout} giây. Để hủy lệnh, mở CMD gõ: shutdown /a")
        try:
            subprocess.Popen(
                ["shutdown", "/r", "/t", str(timeout)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[Action] [✓] Đã lên lịch khởi động lại máy sau {timeout} giây.")
        except Exception as exc:
            print(f"[Action] [✗ Lỗi lệnh restart]: {exc}")

    def _handle_open_explorer(self, action: Dict[str, Any]) -> None:
        """
        Xử lý mở File Explorer (trình duyệt thư mục/tệp tin của Windows).
        """
        path = action.get("path", "").strip()
        print("[Action] Đang mở File Explorer...")
        try:
            if path and os.path.exists(path):
                subprocess.Popen(
                    f'explorer.exe "{path}"',
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    "explorer.exe",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            print("[Action] [✓] Đã mở File Explorer thành công.")
        except Exception as exc:
            print(f"[Action] [✗ Lỗi mở File Explorer]: {exc}")

    def _handle_open_drive(self, action: Dict[str, Any]) -> None:
        """
        Xử lý mở ổ đĩa Windows (C:\\, D:\\...) bằng os.startfile.
        Ví dụ: "mở ổ d", "mở ổ c" -> os.startfile("D:\\") hoặc os.startfile("C:\\")
        """
        raw_drive = str(action.get("drive", "")).strip().upper()
        # Trích xuất ký tự ổ đĩa (C, D, E...)
        match = re.search(r"([A-Z])", raw_drive)
        if match:
            drive_letter = match.group(1)
            drive_path = f"{drive_letter}:\\"
        else:
            drive_path = raw_drive if raw_drive.endswith("\\") else f"{raw_drive}\\"

        print(f"[Action] Đang mở ổ đĩa: {drive_path}...")
        if os.path.exists(drive_path):
            try:
                os.startfile(drive_path)
                print(f"[Action] [✓] Đã mở ổ đĩa '{drive_path}' thành công.")
            except Exception as exc:
                print(f"[Action] [✗ Lỗi khi mở ổ đĩa {drive_path}]: {exc}")
                raise
        else:
            msg = f"Ổ đĩa '{drive_path}' không tồn tại trên hệ thống!"
            print(f"[Action] [✗ Cảnh báo] {msg}")
            raise FileNotFoundError(msg)

    def _handle_open_folder(self, action: Dict[str, Any]) -> None:
        """
        Xử lý mở thư mục hệ thống (Pictures, Downloads, Documents...) bằng os.startfile.
        Ví dụ:
            - "mở bít trơ", "mở ảnh" -> os.startfile(os.path.expanduser("~\\Pictures"))
            - "mở đao lốt", "mở tải về" -> os.startfile(os.path.expanduser("~\\Downloads"))
            - "mở tài liệu" -> os.startfile(os.path.expanduser("~\\Documents"))
        """
        raw_folder = str(action.get("folder") or action.get("name") or "").strip().lower()

        # Bảng ánh xạ thư mục phổ biến và phiên âm tiếng Việt
        folder_map = {
            # Pictures
            "pictures": os.path.expanduser("~\\Pictures"),
            "bít trơ": os.path.expanduser("~\\Pictures"),
            "bít thơ": os.path.expanduser("~\\Pictures"),
            "pic trơ": os.path.expanduser("~\\Pictures"),
            "ảnh": os.path.expanduser("~\\Pictures"),
            "hình ảnh": os.path.expanduser("~\\Pictures"),

            # Downloads
            "downloads": os.path.expanduser("~\\Downloads"),
            "đao lốt": os.path.expanduser("~\\Downloads"),
            "đao nốt": os.path.expanduser("~\\Downloads"),
            "đao lát": os.path.expanduser("~\\Downloads"),
            "tải về": os.path.expanduser("~\\Downloads"),
            "tải xuống": os.path.expanduser("~\\Downloads"),

            # Documents
            "documents": os.path.expanduser("~\\Documents"),
            "đốc cu mần": os.path.expanduser("~\\Documents"),
            "tài liệu": os.path.expanduser("~\\Documents"),
            "văn bản": os.path.expanduser("~\\Documents"),

            # Desktop / Music / Videos
            "desktop": os.path.expanduser("~\\Desktop"),
            "màn hình chính": os.path.expanduser("~\\Desktop"),
            "music": os.path.expanduser("~\\Music"),
            "nhạc": os.path.expanduser("~\\Music"),
            "videos": os.path.expanduser("~\\Videos"),
            "video": os.path.expanduser("~\\Videos"),
        }

        target_dir = folder_map.get(raw_folder)
        if not target_dir:
            target_dir = os.path.expanduser(f"~\\{raw_folder.capitalize()}")

        print(f"[Action] Đang mở thư mục: {target_dir}...")
        if os.path.exists(target_dir):
            try:
                os.startfile(target_dir)
                print(f"[Action] [✓] Đã mở thư mục '{target_dir}' thành công.")
            except Exception as exc:
                print(f"[Action] [✗ Lỗi khi mở thư mục {target_dir}]: {exc}")
                raise
        else:
            msg = f"Thư mục '{target_dir}' không tồn tại!"
            print(f"[Action] [✗ Cảnh báo] {msg}")
            raise FileNotFoundError(msg)

    def _handle_volume(self, action: Dict[str, Any]) -> None:
        """
        Xử lý điều chỉnh âm lượng hệ thống bằng pycaw:
        - Nếu có key 'percentage' (0 đến 100): đặt âm lượng hệ thống về đúng mức đó.
        - Nếu không có 'percentage': dùng 'direction' ('up' / 'down') để tăng/giảm 10%.
        """
        volume_endpoint = self._get_volume_endpoint()
        current_scalar = volume_endpoint.GetMasterVolumeLevelScalar()
        old_pct = round(current_scalar * 100)

        # 1. Trường hợp đặt âm lượng tuyệt đối theo phần trăm (percentage)
        if "percentage" in action and action["percentage"] is not None:
            raw_pct = action["percentage"]
            if isinstance(raw_pct, str):
                raw_pct = raw_pct.replace("%", "").strip()
            try:
                target_pct = float(raw_pct)
            except (ValueError, TypeError):
                raise ValueError(f"Giá trị percentage âm lượng không hợp lệ: '{action.get('percentage')}'")

            # Đảm bảo giới hạn trong khoảng từ 0 đến 100
            clamped_pct = max(0.0, min(100.0, target_pct))
            new_scalar = clamped_pct / 100.0
            volume_endpoint.SetMasterVolumeLevelScalar(new_scalar, None)
            new_pct = round(clamped_pct)
            print(f"[Action] [✓] Đã đặt âm lượng hệ thống về: {new_pct}% (âm lượng trước đó: {old_pct}%)")
            return

        # 2. Trường hợp tăng/giảm tương đối theo direction ("up" hoặc "down")
        direction = str(action.get("direction", "up")).strip().lower()
        step = float(action.get("step", 0.1))  # Mỗi nấc thay đổi mặc định 10%

        if direction == "up":
            new_scalar = min(1.0, current_scalar + step)
            direction_vn = "TĂNG"
        elif direction == "down":
            new_scalar = max(0.0, current_scalar - step)
            direction_vn = "GIẢM"
        else:
            raise ValueError(f"Hướng điều chỉnh âm lượng không hợp lệ: '{direction}' (chỉ nhận 'up' hoặc 'down').")

        volume_endpoint.SetMasterVolumeLevelScalar(new_scalar, None)
        new_pct = round(new_scalar * 100)
        print(f"[Action] [✓] Đã {direction_vn} âm lượng: {old_pct}% -> {new_pct}%")

    def _handle_wifi(self, action: Dict[str, Any]) -> None:
        """
        Xử lý bật/tắt Wi-Fi bằng lệnh netsh interface set interface "Wi-Fi".
        """
        state = str(action.get("state", "on")).strip().lower()
        enable = state in ("on", "enable", "enabled", "bật", "true", "1")
        admin_arg = "admin=ENABLED" if enable else "admin=DISABLED"
        action_name = "bật" if enable else "tắt"

        print(f"[Action] Đang thực hiện {action_name} Wi-Fi...")
        try:
            cmd = f'netsh interface set interface "Wi-Fi" {admin_arg}'
            subprocess.run(
                cmd,
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[Action] [✓] Đã gửi lệnh {action_name} Wi-Fi thành công.")
        except Exception as exc:
            print(f"[Action] [✗ Lỗi điều khiển Wi-Fi]: {exc}")

    def _handle_bluetooth(self, action: Dict[str, Any]) -> None:
        """
        Xử lý bật/tắt Bluetooth bằng PowerShell Start-Service / Stop-Service bthserv.
        """
        state = str(action.get("state", "on")).strip().lower()
        enable = state in ("on", "enable", "enabled", "bật", "true", "1")
        action_name = "bật" if enable else "tắt"

        ps_cmd = "Start-Service bthserv" if enable else "Stop-Service bthserv -Force"
        print(f"[Action] Đang thực hiện {action_name} Bluetooth...")
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[Action] [✓] Đã gửi lệnh {action_name} Bluetooth thành công.")
        except Exception as exc:
            print(f"[Action] [✗ Lỗi điều khiển Bluetooth]: {exc}")

    def _handle_brightness(self, action: Dict[str, Any]) -> None:
        """
        Xử lý tăng/giảm/đặt độ sáng màn hình bằng screen-brightness-control:
        - percentage: Đặt độ sáng tuyệt đối (0 - 100%).
        - direction: Tăng ("up") hoặc Giảm ("down") theo step (mặc định 10%).
        """
        if sbc is None:
            print("[Action Cảnh báo] Thư viện screen-brightness-control chưa được cài đặt!")
            return

        try:
            current_brightness_list = sbc.get_brightness()
            current_val = current_brightness_list[0] if current_brightness_list else 50
        except Exception:
            current_val = 50

        try:
            if "percentage" in action and action["percentage"] is not None:
                raw_pct = action["percentage"]
                if isinstance(raw_pct, str):
                    raw_pct = raw_pct.replace("%", "").strip()
                target_pct = max(0, min(100, round(float(raw_pct))))
                sbc.set_brightness(target_pct)
                print(f"[Action] [✓] Đã đặt độ sáng màn hình về: {target_pct}% (trước đó: {current_val}%)")
                return

            direction = str(action.get("direction", "up")).strip().lower()
            step = action.get("step", 10)
            try:
                step_val = int(step)
            except Exception:
                step_val = 10

            if direction == "up":
                target_pct = min(100, current_val + step_val)
                sbc.set_brightness(target_pct)
                print(f"[Action] [✓] Đã TĂNG độ sáng màn hình: {current_val}% -> {target_pct}%")
            elif direction == "down":
                target_pct = max(0, current_val - step_val)
                sbc.set_brightness(target_pct)
                print(f"[Action] [✓] Đã GIẢM độ sáng màn hình: {current_val}% -> {target_pct}%")
            else:
                print(f"[Action Cảnh báo] Hướng điều chỉnh độ sáng không hợp lệ: {direction}")
        except Exception as exc:
            print(f"[Action] [✗ Lỗi điều khiển độ sáng màn hình]: {exc}")

    def _handle_unknown(self, action: Dict[str, Any]) -> None:
        """
        Xử lý khi câu lệnh không xác định hoặc không hiểu.
        """
        print("Xin lỗi, tôi không hiểu lệnh này.")

    def execute(self, actions: List[Dict[str, Any]]) -> None:
        """
        Thực thi tuần tự danh sách các action.
        Bọc mỗi action trong khối try/except độc lập để nếu 1 action gặp lỗi
        thì vòng lặp vẫn tiếp tục thực thi các action tiếp theo.

        Args:
            actions: Danh sách các dict mô tả hành động (ví dụ từ brain.py).
        """
        if not actions or not isinstance(actions, list):
            print("[Action] Danh sách action trống hoặc không hợp lệ.")
            return

        total = len(actions)
        print(f"\n[ActionExecutor] Bắt đầu thực thi {total} hành động:")

        for index, item in enumerate(actions, 1):
            if not isinstance(item, dict):
                print(f"[Action] [✗ Bỏ qua] Phần tử thứ {index} không phải là dict: {item}")
                continue

            action_type = item.get("action", "unknown").strip().lower()
            print(f"\n--- [Hành động {index}/{total}: '{action_type}'] ---")

            try:
                if action_type == "open_app":
                    self._handle_open_app(item)
                elif action_type == "close_app":
                    self._handle_close_app(item)
                elif action_type == "search_web":
                    self._handle_search_web(item)
                elif action_type == "screenshot":
                    self._handle_screenshot(item)
                elif action_type == "shutdown":
                    self._handle_shutdown(item)
                elif action_type == "lock_screen":
                    self._handle_lock_screen(item)
                elif action_type == "restart":
                    self._handle_restart(item)
                elif action_type == "open_explorer":
                    self._handle_open_explorer(item)
                elif action_type == "open_drive":
                    self._handle_open_drive(item)
                elif action_type == "open_folder":
                    self._handle_open_folder(item)
                elif action_type == "volume":
                    self._handle_volume(item)
                elif action_type == "wifi":
                    self._handle_wifi(item)
                elif action_type == "bluetooth":
                    self._handle_bluetooth(item)
                elif action_type == "brightness":
                    self._handle_brightness(item)
                elif action_type == "unknown":
                    self._handle_unknown(item)
                else:
                    print(f"[Action] [!] Hành động không được hỗ trợ: '{action_type}'")
                    self._handle_unknown(item)

            except Exception as exc:
                # Bắt lỗi độc lập từng action, in lỗi và vẫn tiếp tục vòng lặp
                print(f"[Action] [✗ Lỗi thực thi '{action_type}']: {exc}")

        print(f"\n[ActionExecutor] Hoàn thành toàn bộ {total} hành động.\n")


# Khối mã chạy thử nghiệm trực tiếp
if __name__ == "__main__":
    print("=" * 65)
    print("  KIỂM TRA BỘ THỰC THI HÀNH ĐỘNG (ACTION EXECUTOR)")
    print("=" * 65)

    executor = ActionExecutor()

    # Danh sách các action mẫu thử nghiệm
    test_actions: List[Dict[str, Any]] = [
        # 1. Điều chỉnh âm lượng (pycaw) - Tuyệt đối & Tương đối
        {"action": "volume", "percentage": 50},
        {"action": "volume", "direction": "up"},
        {"action": "volume", "direction": "down"},

        # 2. Tìm kiếm web (webbrowser)
        {"action": "search_web", "query": "thời tiết đà nẵng hôm nay"},

        # 3. Mở ứng dụng (Kiểm tra Chrome -> Registry, Notepad -> Registry, Zalo -> Special Path)
        {"action": "open_app", "name": "chrome"},
        {"action": "open_app", "name": "notepad"},
        {"action": "open_app", "name": "zalo"},

        # 4. Thử nghiệm mở app không tồn tại (đảm bảo không mở nhầm app bừa bãi)
        {"action": "open_app", "name": "app_khong_ton_tai_12345"},

        # 5. Chụp màn hình (PIL.ImageGrab)
        {"action": "screenshot"},

        # 6. Mở File Explorer, Ổ đĩa, Thư mục
        {"action": "open_explorer"},
        {"action": "open_drive", "drive": "C"},
        {"action": "open_drive", "drive": "D"},
        {"action": "open_folder", "folder": "pictures"},
        {"action": "open_folder", "folder": "downloads"},
        {"action": "open_folder", "folder": "documents"},

        # 7. Lệnh không hiểu
        {"action": "unknown"},
    ]

    print("\n--- Thực thi danh sách action mẫu: ---")
    executor.execute(test_actions)

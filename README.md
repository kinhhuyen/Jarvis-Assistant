# 🎙️ Tèo Assistant (Trợ lý ảo AI Desktop) — v1.1.0

> **Trợ lý ảo AI tiếng Việt thế hệ mới trên Windows** — Hoạt động ngầm dưới khay hệ thống (System Tray), đánh thức tức thì bằng giọng nói qua từ khóa chuẩn duy nhất **"Hey Tèo"** (Vosk Offline Grammar), mở mọi ứng dụng siêu tốc (**Fast Path < 0.1s** & **Windows `start` Shell**), hỗ trợ **Tự khởi động cùng Windows**, **Chọn Microphone tùy biến**, **Ghi log xoay vòng `teo_debug.log` bắt bệnh từ xa**, bảo vệ độc quyền Micro (Single Instance Guard) và tự phục hồi dữ liệu thông minh (Auto-Recovery).

---

## 🌟 Điểm mới trong phiên bản v1.1.0 (Bản Đại Tu)

1. **🌐 Lệnh hệ thống mở rộng & Phân biệt rõ Độ Sáng / Âm Lượng:**
   - Hỗ trợ bật/tắt Wi-Fi (`netsh interface set interface "Wi-Fi"`), bật/tắt Bluetooth (`Start-Service / Stop-Service bthserv`).
   - Điều khiển tăng/giảm/đặt độ sáng màn hình (`screen-brightness-control`).
   - Phân biệt tuyệt đối: có chữ "sáng" -> `brightness`, có chữ "âm lượng" -> `volume`.
2. **🪟 Ẩn hoàn toàn cửa sổ CMD & Chặn Popup lỗi:**
   - Mọi tiến trình `subprocess` được gắn cờ `CREATE_NO_WINDOW`, `stdout=DEVNULL, stderr=DEVNULL`. Lỗi chỉ ghi vào log, không gây popup gián đoạn.
3. **⏱️ Cơ chế Timeout 5s chống treo App:**
   - Luồng Worker được trang bị Timeout 5 giây. Nếu xử lý tác vụ quá thời gian, tự động hủy tác vụ treo và reset luồng Microphone.
4. **🛡️ Bộ lọc âm lượng RMS > 300 & Cooldown 2s chống kích hoạt nhầm:**
   - Bộ lọc năng lượng âm thanh RMS chỉ đưa vào Vosk khi âm lượng đủ lớn (> 300), kết hợp Cooldown 2 giây sau mỗi lần kích hoạt để triệt tiêu kích hoạt nhầm bởi tiếng ồn môi trường hay tiếng hát.
5. **🔤 Từ điển phiên âm tiếng Anh nâng cao (RapidFuzz >80%):**
   - Bổ sung `PHONETIC_DICT` và so khớp mờ siêu tốc (>80%) trước khi gọi LLM cho các phần mềm như Word ("quật", "guốt"), Antigravity ("an ti gra vơ ti", "an ti"), Revo Uninstaller ("rề vô", "in sờ to lơ"), Chrome ("chôm").

---

## 🚀 Các tính năng cốt lõi (Core Features)

### 1. 🗣️ Đánh thức bằng giọng nói siêu nhạy (Vosk Wake Word + Grammar)
- **Mô hình Offline cục bộ:** Sử dụng mô hình `vosk-model-small-vn-0.4` chạy hoàn toàn trên máy tính, không cần GPU, bảo mật dữ liệu tuyệt đối.
- **Công nghệ Vosk Grammar (Giới hạn từ vựng):** Khóa không gian từ vựng Kaldi chỉ trong phạm vi từ khóa chuẩn: `"Hey Tèo"`, `[unk]`. Triệt tiêu hoàn toàn hiện tượng nhận nhầm tạp âm hoặc lời chào *"alo"*, *"hê lô"*.
- **Bộ lọc Regex ranh giới từ:** Sử dụng `\b(hey tèo)\b` ngăn ngừa kích hoạt nhầm với các từ đồng âm/vần (như *"bánh bèo"*, *"kẹo kéo"*, *"theo lời"*).
- **Cơ chế nhường Micro đa luồng:** Tự động ngắt stream Wake Word (`pause`) để STT thu âm lệnh rõ nét, sau đó tự phục hồi (`resume`) sau khi xử lý xong lệnh.

### 2. ⚡ Mở mọi ứng dụng tốc độ cao (Fast Path & Windows `start`)
- **Fast Path tức thì (< 0.1s):** Khớp ngay các lệnh mở app quen thuộc qua biểu thức chính quy mà không tốn tài nguyên gọi mô hình ngôn ngữ lớn (LLM).
- **Windows `start` Fallback:** Tự động gọi cơ chế khởi chạy thông minh của Windows để mở các ứng dụng cài qua Windows Store (TikTok, Instagram, Spotify...) hay UWP apps.
- **Giám sát tiến trình bằng `psutil`:** Xác thực tiến trình app đã khởi chạy thành công sau 2 giây; nếu chưa cài đặt, báo lỗi tường minh ra giao diện và file log.

### 3. 🎛️ Lựa chọn Microphone linh hoạt & Bền bỉ
- **Quét thiết bị thông minh:** Dùng `sounddevice` quét các cổng âm thanh đầu vào, tự động kiểm tra `sd.check_input_settings` với chuẩn 16kHz mono.
- **Lưu trữ bền vững:** Lưu cấu hình vào `config.json`, tự động đối chiếu theo ID và tên thiết bị khi cắm lại cổng USB khác.
- **Tự phục hồi kết nối:** Nếu Micro đang dùng bị rút đột ngột, hệ thống tự động fallback về Micro mặc định hệ thống mà không làm crash app.

### 4. 🚀 Khởi động cùng Windows (Autostart Registry)
- Quản lý qua Windows Registry tại đường dẫn: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`.
- Bật/tắt chỉ với 1 cú click chuột phải vào biểu tượng System Tray (có dấu tích ✓ trực quan).

### 5. 📄 Bắt bệnh từ xa với file Log xoay vòng (`teo_debug.log`)
- Do bản đóng gói `.exe` ẩn cửa sổ console đen (`console=False`), toàn bộ thông báo `print()`, log Vosk thời gian thực và exception đều được chuyển hướng qua `RotatingFileHandler` vào file `teo_debug.log` đặt cạnh file `.exe`.
- Dung lượng giới hạn 3MB, tự động sao lưu xoay vòng tối đa 2 file cũ, không lo tràn ổ đĩa.
- Nhấp trực tiếp vào menu *"Mở file Log (teo_debug.log)"* để mở nhanh bằng Notepad.

### 6. 🛡️ Bảo vệ chống mở trùng lặp (Single Instance Guard)
- **Cơ chế Dual-Lock:** Kết hợp **Windows Named Mutex** (`Local\TeoAssistant_SingleInstance_Mutex`) và **Localhost Socket Binding** (`127.0.0.1:65432`) được thực thi ngay tại dòng đầu tiên của chương trình.
- **Phản hồi siêu tốc:** Nếu người dùng vô tình nhấp đúp mở app lần 2, tiến trình mới phát hiện trong vòng **50ms**, in ra thông báo và thoát ngay lập tức (`sys.exit(0)`), tránh hoàn toàn việc tranh chấp Micro.

### 7. 🔄 Tự phục hồi dữ liệu bộ nhớ (Auto-Recovery)
- Module [`memory_manager.py`](file:///d:/Tools/VoicePilot/memory_manager.py) tự động bảo vệ khi đọc `memory.json`.
- Khi file bị lỗi cấu trúc do copy nhầm hoặc mất điện: Tự động sao lưu ra `.bak` và ghi đè file rỗng `{}` chuẩn UTF-8, đảm bảo ứng dụng không bao giờ bị văng.

### 8. ⚡ Nhận diện giọng nói Hybrid (Google STT + Vosk Offline)
- **Online (Google STT):** Tốc độ nhận diện lệnh nhanh chóng (< 1s) với độ chuẩn xác ngôn ngữ tự nhiên cao.
- **Offline (Vosk STT):** Tự động chuyển đổi ngoại tuyến khi mất Internet.
- **Thu âm thông minh:** Hỗ trợ kích hoạt rảnh tay qua Wake Word lẫn phím tắt **Push-to-Talk** (`Ctrl + Space`) chống cắt âm với đệm trễ an toàn 350ms.

### 9. 🔮 Giao diện phát sáng Glow Orb (PyQt6 Translucent Overlay)
- Cửa sổ không viền (**Frameless**), luôn nổi trên cùng (**Always on Top**), nền trong suốt (**Translucent**).
- Vòng tròn phát sáng gradient Cyan/Blue huyền ảo kèm nhịp thở 60 FPS và dòng trạng thái động (*"Tèo đang lắng nghe..."*, *"Đang thực thi lệnh..."*).

---

## 📂 Cấu trúc thư mục dự án

```text
VoicePilot/
│
├── app_tray.py               # [Entry Point] Khay hệ thống, Autostart, Menu Micro, điều phối toàn bộ app
├── ui_overlay.py             # Giao diện Glow Orb phát sáng bằng PyQt6 (Frameless, Always on Top)
├── wake_word_engine.py       # Bộ lắng nghe Wake Word ("Hey Tèo") bằng Vosk Offline Grammar & chọn Micro
├── stt_engine.py             # Module nhận diện giọng nói Hybrid (Google STT + Vosk Offline) & chọn Micro
├── brain.py                  # Bộ não Hybrid (Fast Path Regex < 0.1s, Cache, Slow Path routing)
├── actions.py                # Bộ thực thi hành động hệ thống (Registry, Windows start shell, Volume...)
├── memory_manager.py         # Quản lý bộ nhớ đệm lệnh và tự phục hồi khi JSON hỏng (Auto-Recovery)
├── auto_learn.py             # Bộ tự học offline 3 tầng validation, chuẩn hóa phiên âm
├── utils.py                  # Đường dẫn động, ghi log xoay vòng, Registry Autostart & Quản lý Micro
│
├── model/                    # Thư mục mô hình Vosk Offline tiếng Việt (vosk-model-small-vn)
├── config.json               # Cấu hình Micro và tùy chọn cá nhân
├── memory.json               # Cơ sở dữ liệu bộ nhớ đệm câu lệnh (Memory Cache)
├── learned_phonetics.json    # Từ điển tự học từ lóng / phiên âm tên ứng dụng
├── offline_learning.json     # Từ điển tự học ánh xạ âm thanh Vosk -> Lệnh chuẩn
├── teo_debug.log             # Nhật ký hoạt động chi tiết thời gian thực
│
├── TeoAssistant.spec         # File cấu hình đóng gói PyInstaller chuyên dụng v1.3.1
├── requirements.txt          # Danh sách thư viện Python cần thiết
├── test_hybrid_system.py     # Suite kiểm thử tự động toàn diện STT, Brain, Actions
└── test_phase5_wake_overlay.py # Suite kiểm thử tự động Wake Word Vosk Grammar & Overlay
```

---

## 🛠️ Hướng dẫn sử dụng

### Cách 1: Chạy trực tiếp từ file thực thi `.exe` (Khuyên dùng)
1. Truy cập thư mục phân phối:
   ```text
   dist/TeoAssistant/
   ```
2. Khởi chạy file: **`TeoAssistant.exe`**
3. Ứng dụng sẽ xuất hiện dưới dạng biểu tượng chữ **T** tỏa sáng ở góc dưới bên phải màn hình (**System Tray**).
4. Nói **"Hey Tèo"** để đánh thức trợ lý và ra lệnh!
5. **Cấu hình nhanh:** Nhấp chuột phải vào biểu tượng khay hệ thống để:
   - Tích chọn: **Khởi động cùng Windows**.
   - Vào mục **Cấu hình Micro** để chọn đúng Micro của tai nghe/webcam nếu máy có nhiều micro.
   - Nhấp **Mở file Log (teo_debug.log)** để kiểm tra trạng thái hoạt động.

---

### Cách 2: Chạy trực tiếp từ mã nguồn Python

#### 1. Yêu cầu môi trường:
- Hệ điều hành: Windows 10 / Windows 11 (64-bit).
- Python: Phiên bản `3.10` đến `3.14`.
- Microphone đang hoạt động tốt.

#### 2. Cài đặt các thư viện phụ thuộc:
```bash
pip install -r requirements.txt
```

#### 3. Chạy thử nghiệm độc lập Wake Word (Xem Log Debug Vosk):
```bash
python wake_word_engine.py
```

#### 4. Khởi chạy toàn bộ ứng dụng:
```bash
python app_tray.py
```

---

## 📦 Hướng dẫn Đóng gói thành file `.exe` bằng PyInstaller

Dự án đã tích hợp sẵn file cấu hình chuyên dụng [`TeoAssistant.spec`](file:///d:/Tools/VoicePilot/TeoAssistant.spec) tối ưu theo chế độ **ONEDIR**:

```bash
python -m PyInstaller TeoAssistant.spec --clean --noconfirm
```

Sau khi hoàn tất, thư mục sản phẩm sẽ nằm tại `dist/TeoAssistant/` bao gồm:
- `TeoAssistant.exe`: File chạy chính (ẩn hoàn toàn cửa sổ đen console).
- `_internal/`: Toàn bộ runtime, DLLs của PyQt6, Vosk, PortAudio và mô hình tiếng Việt đã nén.
- `config.json`, `memory.json`, `offline_learning.json`, `learned_phonetics.json`: Các file dữ liệu nằm cạnh file `.exe`.
- `teo_debug.log`: File log tự động sinh ra khi chạy ứng dụng.

---

## 💬 Danh sách câu lệnh mẫu

| Thể loại | Ví dụ câu lệnh bạn có thể nói |
|---|---|
| **Đánh thức (Wake Word)** | *"Hey Tèo"* |
| **Mở ứng dụng siêu tốc** | *"Mở TikTok"*, *"Mở Word"*, *"Mở Chrome"*, *"Bật Zalo"*, *"Mở Notepad"*, *"Mở Spotify"* |
| **Lệnh ghép** | *"Mở Chrome và mở Zalo"*, *"Tắt Edge rồi mở Discord"* |
| **Âm lượng** | *"Tăng âm lượng lên 80%"*, *"Giảm âm lượng xuống 30%"*, *"Tắt tiếng"* |
| **Tìm kiếm Web** | *"Tìm kiếm giá vàng hôm nay"*, *"Thời tiết Đà Nẵng hôm nay thế nào"* |
| **Hệ thống** | *"Chụp màn hình"*, *"Khóa màn hình"*, *"Mở thư mục Downloads"* |

---

## 📄 Bản quyền & Đóng góp
Dự án mã nguồn mở phục vụ cộng đồng học tập và tối ưu năng suất làm việc trên Windows. Mọi đóng góp (Pull Request, Issue) đều được chào đón nồng nhiệt!

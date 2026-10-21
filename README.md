# 🎙️ Tèo Assistant (Trợ lý ảo AI Desktop) — v1.1.0

> **Trợ lý ảo AI tiếng Việt thế hệ mới trên Windows** — Hoạt động ngầm dưới khay hệ thống (System Tray), đánh thức tức thì bằng giọng nói qua từ khóa **"Hey Tèo"** / **"Tèo ơi"** (Vosk Offline Grammar), bảo vệ độc quyền Micro (Single Instance Guard), tự phục hồi dữ liệu thông minh (Auto-Recovery) và sở hữu giao diện phát sáng **Glow Orb** huyền ảo phong cách Siri.

---

## 🌟 Giới thiệu

**Tèo Assistant (Phiên bản v1.1.0)** là giải pháp trợ lý điều khiển máy tính bằng giọng nói hoàn chỉnh, tối ưu hóa 100% cho người dùng Việt Nam trên hệ điều hành Windows 10/11. Ứng dụng được thiết kế với các tiêu chí cốt lõi:
- **Chạy ngầm nhẹ nhàng:** Hoạt động dưới thanh tác vụ Windows (System Tray), tiêu tốn tối thiểu tài nguyên CPU/RAM.
- **Đánh thức rảnh tay (Hands-Free):** Nhận diện từ khóa **"Hey Tèo"** hoặc **"Tèo ơi"** không cần chạm bàn phím hay chuột.
- **Bảo vệ độc quyền Micro (Single Instance Guard):** Tự động phát hiện nếu app đã chạy ngầm và lập tức thoát trong vòng 50ms, triệt tiêu hoàn toàn lỗi tranh chấp Microphone.
- **Tự phục hồi dữ liệu (Auto-Recovery):** Tự động sao lưu và tái tạo file dữ liệu `memory.json` khi bị lỗi cấu trúc, đảm bảo app không bao giờ bị văng (Crash).
- **Giao diện Glow Orb mờ ảo:** Hiệu ứng vòng tròn phát sáng trong suốt (PyQt6 Translucent Overlay) nổi giữa màn hình kèm nhịp thở sống động.
- **Kiến trúc STT Hybrid:** Phản hồi câu lệnh trực tuyến qua Google STT (< 1s) và tự động chuyển sang mô hình Vosk Offline khi mất kết nối mạng.

---

## 🚀 Các tính năng cốt lõi (Core Features)

### 1. 🗣️ Đánh thức bằng giọng nói siêu nhạy (Vosk Wake Word + Grammar)
- **Mô hình Offline cục bộ:** Sử dụng mô hình `vosk-model-small-vn-0.4` chạy hoàn toàn trên máy tính, không cần GPU, bảo mật dữ liệu tuyệt đối.
- **Công nghệ Vosk Grammar (Giới hạn từ vựng):** Khóa không gian từ vựng Kaldi chỉ trong phạm vi các câu gọi: `"Hey Tèo"`, `"Tèo ơi"`, `"Ê Tèo"`, `"Hê Tèo"`, `"Này Tèo"`, `"Chào Tèo"`, `"Tèo"`, `[unk]`. Điều này giúp triệt tiêu hoàn toàn tình trạng Vosk nhận nhầm tiếng ồn thành các từ lạ.
- **Bộ lọc Regex ranh giới từ:** Sử dụng `\b(hey tèo|hê tèo|này tèo|chào tèo|ê tèo|tèo ơi|tèo|teo)\b` ngăn ngừa kích hoạt nhầm với các từ đồng âm/vần (như *"bánh bèo"*, *"kẹo kéo"*, *"theo lời"*).
- **Log Debug thời gian thực:** Hiển thị trực tiếp mọi âm thanh nhận diện được trên màn hình console để người dùng dễ dàng căn chỉnh khoảng cách và âm lượng Micro.
- **Cơ chế nhường Micro đa luồng:** Tự động ngắt stream Wake Word (`pause`) để STT thu âm lệnh rõ nét, sau đó tự phục hồi (`resume`) sau khi xử lý xong lệnh.

### 2. 🛡️ Bảo vệ chống mở trùng lặp (Single Instance Guard)
- **Cơ chế Dual-Lock:** Kết hợp **Windows Named Mutex** (`Local\TeoAssistant_SingleInstance_Mutex`) và **Localhost Socket Binding** (`127.0.0.1:65432`) được thực thi ngay tại dòng đầu tiên của chương trình (trước khi nạp bất kỳ thư viện nặng nào).
- **Phản hồi siêu tốc:** Nếu người dùng vô tình nhấp đúp mở app lần 2:
  - Tiến trình mới phát hiện app đang chạy trong vòng **50ms**.
  - In ra thông báo: `"Tèo Assistant đang chạy ngầm!"`.
  - Tự động đóng tiến trình (`sys.exit(0)`), nhường trọn vẹn microphone cho app đang chạy.

### 3. 🔄 Tự phục hồi dữ liệu bộ nhớ (Auto-Recovery)
- Module [`memory_manager.py`](file:///d:/Tools/VoicePilot/memory_manager.py) được trang bị cơ chế tự bảo vệ khi đọc `memory.json`.
- Khi người dùng copy-paste nhầm hoặc file bị hỏng do mất điện đột ngột:
  - Tự động tạo file sao lưu `memory.json.corrupt_<timestamp>.bak`.
  - Tự động ghi đè lại file rỗng `{}` chuẩn UTF-8, giúp hệ thống tiếp tục vận hành mượt mà mà **không bị văng app (Crash)**.

### 4. ⚡ Nhận diện giọng nói Hybrid (Google STT + Vosk Offline)
- **Online (Google STT):** Tốc độ nhận diện lệnh nhanh chóng (< 1s) với độ chuẩn xác ngôn ngữ tự nhiên cao.
- **Offline (Vosk STT):** Tự động chuyển đổi ngoại tuyến khi mất Internet.
- **Thu âm thông minh:** Hỗ trợ cả kích hoạt rảnh tay qua Wake Word (tự phát hiện khoảng lặng VAD) lẫn phím tắt **Push-to-Talk** (`Ctrl + Space`) chống cắt âm với đệm trễ an toàn 350ms.

### 5. 🧠 Bộ não đa tầng (Hybrid Brain & Memory Cache)
- **Fast Path (Regex Engine):** Khớp ngay các lệnh điều khiển thông dụng (mở app, chỉnh âm lượng, tìm kiếm, khóa máy) với độ trễ xấp xỉ **0ms**.
- **Memory Cache:** Tự động ghi nhớ câu lệnh thành công vào `memory.json`, lần sau nói lại phản hồi trong vòng **< 1ms**.
- **Slow Path & Verbatim Protection:** Trích xuất nguyên văn từ khóa tìm kiếm (*"giá vàng hôm nay"*, *"thời tiết Đà Nẵng"*), chống ảo giác và chặn các app ngoài Whitelist an toàn.

### 6. 📚 Tự học từ vựng & Sửa lỗi chính tả (Auto-Learning 3 Tầng)
- So sánh sai khác giữa Vosk Offline và Google STT trong luồng ngầm để tự học từ vựng vào `offline_learning.json`.
- **Bộ lọc 3 tầng nghiêm ngặt:**
  - *Độ tương đồng ngữ âm:* Ngưỡng tối thiểu ≥ 0.5 (loại bỏ ảo giác tạp âm).
  - *Chênh lệch số từ:* Độ lệch từ ≤ 2 từ (ngăn Vosk bịa câu dài khi mic ồn).
  - *Bảo vệ tên ứng dụng Whitelist:* Tách chuẩn từng vế câu ghép, tránh gán nhầm từ lóng.
  - *Hàng đợi FIFO:* Duy trì tối đa 100 cặp từ vựng tối ưu nhất.

### 7. 🔮 Giao diện phát sáng Glow Orb (PyQt6 Translucent Overlay)
- Cửa sổ không viền (**Frameless**), luôn nổi trên cùng (**Always on Top**), nền trong suốt (**Translucent**).
- Vòng tròn phát sáng gradient Cyan/Blue huyền ảo kèm nhịp thở 60 FPS và dòng trạng thái động (*"Tèo đang lắng nghe..."*, *"Đang thực thi lệnh..."*).

---

## 📂 Cấu trúc thư mục dự án

```text
VoicePilot/
│
├── app_tray.py               # [Entry Point] Khay hệ thống, Single Instance Guard, điều phối toàn bộ app
├── ui_overlay.py             # Giao diện Glow Orb phát sáng bằng PyQt6 (Frameless, Always on Top)
├── wake_word_engine.py       # Bộ lắng nghe Wake Word ("Hey Tèo") bằng Vosk Offline Grammar
├── stt_engine.py             # Module nhận diện giọng nói Hybrid (Google STT + Vosk Offline)
├── brain.py                  # Bộ não Hybrid (Fast Path Regex, Cache, Slow Path routing)
├── actions.py                # Bộ thực thi hành động hệ thống (Registry App, Volume, Web Search...)
├── memory_manager.py         # Quản lý bộ nhớ đệm lệnh và tự phục hồi khi JSON hỏng (Auto-Recovery)
├── auto_learn.py             # Bộ tự học offline 3 tầng validation, chuẩn hóa phiên âm
├── utils.py                  # Xử lý đường dẫn động (sys._MEIPASS vs Source Code)
│
├── model/                    # Thư mục mô hình Vosk Offline tiếng Việt (vosk-model-small-vn)
├── memory.json               # Cơ sở dữ liệu bộ nhớ đệm câu lệnh (Memory Cache)
├── learned_phonetics.json    # Từ điển tự học từ lóng / phiên âm tên ứng dụng
├── offline_learning.json     # Từ điển tự học ánh xạ âm thanh Vosk -> Lệnh chuẩn
│
├── TeoAssistant.spec         # File cấu hình đóng gói PyInstaller chuyên dụng v1.1.0
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
4. Nói **"Hey Tèo"** hoặc **"Tèo ơi"** để đánh thức trợ lý và ra lệnh!

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

Dự án đã tích hợp sẵn file cấu hình chuyên dụng [`TeoAssistant.spec`](file:///d:/Tools/VoicePilot/TeoAssistant.spec) tối ưu theo chế độ **ONEDIR** (đã loại bỏ toàn bộ thư viện nặng không cần thiết):

```bash
python -m PyInstaller TeoAssistant.spec --clean --noconfirm
```

Sau khi hoàn tất, thư mục sản phẩm sẽ nằm tại `dist/TeoAssistant/` bao gồm:
- `TeoAssistant.exe`: File chạy chính (ẩn hoàn toàn cửa sổ đen console).
- `_internal/`: Toàn bộ runtime, DLLs của PyQt6, Vosk, PortAudio và mô hình tiếng Việt đã nén.
- `memory.json`, `offline_learning.json`, `learned_phonetics.json`: Các file cơ sở dữ liệu học tập liên tục được lưu trữ cạnh file `.exe`.

---

## 💬 Danh sách câu lệnh mẫu

| Thể loại | Ví dụ câu lệnh bạn có thể nói |
|---|---|
| **Đánh thức (Wake Word)** | *"Hey Tèo"*, *"Tèo ơi"*, *"Ê Tèo"*, *"Này Tèo"*, *"Chào Tèo"* |
| **Mở ứng dụng** | *"Mở Chrome"*, *"Bật Zalo"*, *"Mở Notepad"*, *"Mở Discord"* |
| **Lệnh ghép** | *"Mở Chrome và mở Zalo"*, *"Tắt Edge rồi mở Discord"* |
| **Âm lượng** | *"Tăng âm lượng lên 80%"*, *"Giảm âm lượng xuống 30%"*, *"Tắt tiếng"* |
| **Tìm kiếm Web** | *"Tìm kiếm giá vàng hôm nay"*, *"Thời tiết Đà Nẵng hôm nay thế nào"* |
| **Hệ thống** | *"Chụp màn hình"*, *"Khóa màn hình"*, *"Mở thư mục Downloads"* |

---

## 📄 Bản quyền & Đóng góp
Dự án mã nguồn mở phục vụ cộng đồng học tập và tối ưu năng suất làm việc trên Windows. Mọi đóng góp (Pull Request, Issue) đều được chào đón nồng nhiệt!

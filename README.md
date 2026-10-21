# 🎙️ Jarvis Assistant (Echo Desktop AI)

> **Trợ lý ảo AI thế hệ mới trên Windows** — Hoạt động ngầm dưới khay hệ thống (System Tray), đánh thức tức thì bằng giọng nói (Wake Word), sở hữu giao diện phát sáng **Glow Orb** huyền ảo phong cách Siri và cơ chế tự học ngoại tuyến thông minh.

---

## 🌟 Giới thiệu

**Jarvis Assistant** (tên nội bộ *Echo Assistant*) là giải pháp trợ lý điều khiển máy tính bằng giọng nói hoàn chỉnh dành cho hệ điều hành Windows. Ứng dụng được thiết kế để:
- Chạy ngầm 100% tài nguyên nhẹ nhàng trên thanh tác vụ (System Tray).
- Kích hoạt rảnh tay (Hands-Free) khi nghe câu lệnh gọi **"Hey Jarvis"** hoặc **"Alexa"**.
- Hiển thị giao diện **Glow Orb** tròn phát sáng mờ ảo ở giữa màn hình với hiệu ứng nhịp thở (Breathing Animation) sống động bằng PyQt6.
- Kết hợp nhận diện online siêu tốc (<1s) và offline độc lập khi mất mạng, liên tục tự học các câu lệnh và cách phát âm quen thuộc của người dùng.

---

## 🚀 Các tính năng cốt lõi

### 1. 🗣️ Đánh thức bằng giọng nói (Wake Word Engine)
- Sử dụng thư viện **OpenWakeWord** chạy trên nền tảng **ONNX Runtime** (hoàn toàn cục bộ, miễn phí, không tốn GPU).
- Hỗ trợ các từ khóa chuẩn: `"Hey Jarvis"` và `"Alexa"`.
- Cơ chế quản lý luồng thông minh: Tự động tạm dừng (`pause`) khi phát hiện từ khóa để nhường Micro cho bộ nhận diện câu lệnh, sau đó tự phục hồi (`resume`) sau khi xử lý xong nhằm loại bỏ xung đột PortAudio.

### 2. ⚡ Kiến trúc Hybrid STT (Speech-to-Text)
- **Online (Google STT):** Độ chính xác cao, phản hồi câu lệnh thần tốc (< 1s) cho Bộ não giải mã.
- **Offline (Vosk Speech Engine):** Tự động chuyển đổi sang mô hình Vosk Offline tiếng Việt khi mất kết nối mạng.
- **Thu âm linh hoạt:** Hỗ trợ cả kích hoạt rảnh tay qua Wake Word (tự phát hiện khoảng lặng VAD) lẫn phím tắt **Push-to-Talk** (`Ctrl + Space`) chống cắt âm cuối với đệm trễ an toàn 350ms.

### 3. 🧠 Bộ não đa tầng (Hybrid Brain & Memory Cache)
- **Fast Path (Regex Engine):** Khớp ngay các lệnh phổ biến (mở ứng dụng, tăng giảm âm lượng, tìm kiếm, khóa màn hình) với độ trễ gần như bằng **0ms**.
- **Memory Cache (Bộ nhớ đệm thông minh):** Tự động ghi nhớ các câu lệnh đã thực thi thành công vào `memory.json`. Lần sau khi nói lại, hệ thống trả về hành động tức thì (< 1ms).
- **Slow Path (LLM Fallback & Verbatim Protection):** Kết nối LLM cục bộ (Ollama) cho các câu nói phức tạp hoặc câu ghép, đồng thời bảo vệ nguyên văn các truy vấn tìm kiếm ("thời tiết", "giá vàng") không bị bóp méo.

### 4. 📚 Cơ chế Tự học & Sửa lỗi chính tả (Auto-Learning)
- Tự động so sánh sự sai lệch giữa kết quả nghe của Vosk (offline) và Google STT (online) trong luồng ngầm để tự học từ vựng vào `offline_learning.json`.
- **Bộ lọc 3 tầng nghiêm ngặt (Validation):**
  - *Độ tương đồng ngữ âm (Phonetic Similarity):* Dùng `difflib.SequenceMatcher`, loại bỏ ngay các ảo giác lệch âm (ratio < 0.5).
  - *Chênh lệch số từ:* Ngăn Vosk tự bịa ra câu dài lan man khi môi trường ồn (chênh lệch tối đa ≤ 2 từ).
  - *Ngăn chặn gán sai ngữ cảnh:* Bảo vệ tên app chuẩn trong Whitelist, chỉ học từ lóng khi nằm cùng cụm lệnh đơn.
  - *Cơ chế FIFO:* Tự động duy trì tối đa 100 cặp từ vựng tối ưu nhất.

### 5. 🔮 Giao diện Glow Orb mờ ảo (PyQt6 Translucent Overlay)
- Cửa sổ không viền (**Frameless**), luôn nổi lên trên (**Always on Top**), nền trong suốt tuyệt đối (**Translucent**).
- Vòng sáng đa lớp vẽ bằng vector `QPainter` + `QRadialGradient` với bảng màu Cyan/Deep Sky Blue huyền ảo.
- Hiệu ứng nhịp thở 60 FPS cùng dòng chữ trạng thái động (*"Đang lắng nghe..."*, *"Đang phân tích..."*, v.v.).

### 6. 🛡️ Khởi chạy ứng dụng an toàn qua Windows Registry
- Quét thông minh qua `App Paths` trong **Windows Registry** kết hợp danh sách đường dẫn phần mềm chuẩn.
- Mở chính xác Chrome, Microsoft Edge, Zalo, Discord, Notepad, VS Code... mà không lo mở nhầm các tệp lạ hoặc làm chậm ổ cứng do quét đệ quy.
- Điều khiển âm lượng hệ thống chuẩn xác theo phần trăm qua `pycaw`.

---

## 📂 Cấu trúc thư mục dự án

```text
VoicePilot/
│
├── app_tray.py               # [Entry Point] Khay hệ thống, quản lý QThread và điều phối toàn bộ app
├── ui_overlay.py             # Giao diện Glow Orb phát sáng bằng PyQt6 (Frameless, Always on Top)
├── wake_word_engine.py       # Bộ lắng nghe Wake Word ("Hey Jarvis") bằng OpenWakeWord ONNX
├── stt_engine.py             # Module nhận diện giọng nói Hybrid (Google STT + Vosk Offline)
├── brain.py                  # Bộ não điều phối Hybrid (Fast Path Regex, Cache, LLM routing)
├── actions.py                # Bộ thực thi hành động hệ thống (Registry App, Volume, Web Search...)
├── memory_manager.py         # Quản lý bộ nhớ đệm lệnh và tìm kiếm mờ (Fuzzy Matching)
├── auto_learn.py             # Bộ tự học offline, lọc ảo giác và chuẩn hóa phiên âm
├── utils.py                  # Xử lý đường dẫn động (sys._MEIPASS vs Source Code)
│
├── model/                    # Thư mục mô hình Vosk Offline tiếng Việt (vosk-model-small-vn)
├── memory.json               # Dữ liệu bộ nhớ đệm câu lệnh (Memory Cache)
├── learned_phonetics.json    # Từ điển tự học từ lóng / phiên âm tên ứng dụng
├── offline_learning.json     # Từ điển tự học ánh xạ âm thanh Vosk -> Lệnh chuẩn
│
├── jarvis_build.spec         # File cấu hình đóng gói PyInstaller chuyên dụng
├── requirements.txt          # Danh sách thư viện Python cần thiết
└── test_hybrid_system.py     # Suite kiểm thử tự động toàn diện hệ thống
```

---

## 🛠️ Hướng dẫn sử dụng

### Cách 1: Sử dụng file chạy trực tiếp (.exe) — Không cần cài Python
1. Tải hoặc truy cập thư mục phân phối:
   ```text
   dist/JarvisAssistant/
   ```
2. Khởi chạy file: **`JarvisAssistant.exe`**
3. Ứng dụng sẽ xuất hiện dưới dạng một biểu tượng hình Orb ở góc dưới bên phải màn hình (**System Tray**).
4. Nói **"Hey Jarvis"** hoặc **"Alexa"** để bắt đầu ra lệnh.

---

### Cách 2: Chạy trực tiếp từ mã nguồn Python

#### 1. Yêu cầu môi trường:
- Hệ điều hành: Windows 10 / Windows 11 (64-bit).
- Python: Phiên bản `3.10` đến `3.14`.
- Microphone đang hoạt động tốt.

#### 2. Cài đặt các thư viện phụ thuộc:
```bash
git clone https://github.com/your-repo/jarvis-assistant.git
cd jarvis-assistant

# Cài đặt tất cả thư viện cần thiết
pip install -r requirements.txt
```

#### 3. Khởi chạy ứng dụng:
```bash
python app_tray.py
```

---

## 📦 Hướng dẫn Đóng gói thành file `.exe` bằng PyInstaller

Dự án đã tích hợp sẵn file cấu hình [`jarvis_build.spec`](file:///d:/Tools/VoicePilot/jarvis_build.spec) tối ưu theo chế độ **ONEDIR**:

```bash
# Biên dịch và đóng gói tự động
python -m PyInstaller jarvis_build.spec --clean --noconfirm
```

Sau khi hoàn tất, thư mục sản phẩm sẽ nằm tại `dist/JarvisAssistant/` bao gồm:
- `JarvisAssistant.exe`: File chạy chính.
- `_internal/`: Toàn bộ runtime, DLLs của PyQt6, Vosk, PortAudio và các mô hình AI đã nén.
- `memory.json`, `offline_learning.json`, `learned_phonetics.json`: Các file cơ sở dữ liệu học tập liên tục được lưu trữ cạnh file `.exe`.

---

## 💬 Danh sách câu lệnh mẫu

| Thể loại | Ví dụ câu lệnh bạn có thể nói |
|---|---|
| **Mở ứng dụng** | *"Mở Chrome"*, *"Bật Zalo"*, *"Mở Notepad"*, *"Mở Discord"* |
| **Lệnh ghép** | *"Mở Chrome và mở Zalo"*, *"Tắt Edge rồi mở Discord"* |
| **Âm lượng** | *"Tăng âm lượng lên 80%"*, *"Giảm âm lượng xuống 30%"*, *"Tắt tiếng"* |
| **Tìm kiếm Web** | *"Tìm kiếm giá vàng hôm nay"*, *"Thời tiết Đà Nẵng hôm nay thế nào"* |
| **Hệ thống** | *"Chụp màn hình"*, *"Khóa màn hình"*, *"Mở thư mục Downloads"* |

---

## 📄 Bản quyền & Đóng góp
Dự án được phát triển với mục tiêu mã nguồn mở, phục vụ cộng đồng học tập và tối ưu năng suất làm việc trên Windows. Mọi đóng góp (Pull Request, Issue) đều được chào đón nồng nhiệt!

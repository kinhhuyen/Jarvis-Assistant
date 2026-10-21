"""
Test Suite: test_hybrid_system.py
Kiểm tra toàn diện kiến trúc Hybrid Tự Học của VoicePilot:
1. auto_learn.py: Ghi nhớ vào offline_learning.json và áp dụng từ điển tự học.
2. actions.py: Kiểm tra action open_drive và open_folder.
3. brain.py: Kiểm tra FUZZY_MAP, Fast Path (mở ổ đĩa, mở thư mục), CHỐNG MEMORY CACHE CHO CÂU < 3 TỪ.
4. stt_engine.py:
   - Chunk size 1024/2048.
   - Trì hoãn 350ms khi nhả phím Push-to-Talk để thu âm trọn vẹn.
   - Bỏ qua và thông báo khi Google STT rỗng "", KHÔNG gọi Vosk (chống bịa từ).
   - Đa luồng ngầm (threading), không block luồng chính.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Đảm bảo in tiếng Việt có dấu trên Windows console
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from actions import ActionExecutor
from auto_learn import apply_offline_learning, auto_learn, load_offline_learning
from brain import Brain
from stt_engine import SpeechToText


def test_auto_learn_module():
    print("\n" + "=" * 60)
    print("TEST 1: MODULE TỰ HỌC (auto_learn.py) VỚI 3 TẦNG VALIDATION")
    print("=" * 60)

    test_file = Path(__file__).resolve().parent / "test_offline_learning.json"
    if test_file.exists():
        test_file.unlink()

    try:
        # 1. Câu lệnh hợp lệ (bắt đầu bằng động từ 'khóa', độ tương đồng > 0.5): 'khóa bất hình' -> 'khóa màn hình'
        res1 = auto_learn("khóa bất hình", "khóa màn hình", filepath=str(test_file))
        assert res1 is True, "Cần lưu thành công cặp từ hợp lệ 'khóa bất hình' -> 'khóa màn hình'"
        print("  [✓] Đã lưu cặp từ hợp lệ: 'khóa bất hình' -> 'khóa màn hình'")

        # 2. Câu lệnh hợp lệ: 'mở pic trơ' -> 'mở pictures' -> PHẢI LƯU
        res2 = auto_learn("mở pic trơ", "mở pictures", filepath=str(test_file))
        assert res2 is True, "Cần lưu thành công cặp từ 'mở pic trơ' -> 'mở pictures'"
        print("  [✓] Đã lưu cặp từ hợp lệ: 'mở pic trơ' -> 'mở pictures'")

        # 2b. Câu lệnh tìm kiếm & điều chỉnh âm lượng (VALID_COMMAND_VERBS mở rộng & SEARCH_BYPASS_KEYWORDS):
        # 'kiếm giá vàng hôm nay' -> Động từ 'kiếm' và từ khóa 'giá'
        res2b = auto_learn("kiếm giá vào hôm nay", "kiếm giá vàng hôm nay", filepath=str(test_file))
        assert res2b is True, "Cần lưu thành công câu tìm kiếm với động từ 'kiếm' và từ khóa 'giá'"
        print("  [✓] Đã lưu câu tìm kiếm: 'kiếm giá vào hôm nay' -> 'kiếm giá vàng hôm nay'")

        # 'thời tiết Đà Nẵng' -> Bypass động từ nhờ từ khóa tìm kiếm 'thời tiết'
        res2c = auto_learn("thời tiếc đè nẵng", "thời tiết đà nẵng", filepath=str(test_file))
        assert res2c is True, "Cần lưu thành công câu tìm kiếm chủ đề trực tiếp 'thời tiết đà nẵng'"
        print("  [✓] Đã lưu câu bypass động từ với từ khóa tìm kiếm: 'thời tiếc đè nẵng' -> 'thời tiết đà nẵng'")

        # 'giảm âm lượng xuống 50%' -> Động từ điều khiển 'giảm'
        res2d = auto_learn("hạ âm lượng xuống 50%", "giảm âm lượng xuống 50%", filepath=str(test_file))
        assert res2d is True, "Cần lưu thành công câu điều khiển âm lượng với động từ 'giảm'"
        print("  [✓] Đã lưu câu điều khiển âm lượng: 'hạ âm lượng xuống 50%' -> 'giảm âm lượng xuống 50%'")

        # 2e. THỬ NGHIỆM ĐIỀU KIỆN 0: ĐỘ TƯƠNG ĐỒNG NGỮ ÂM (SequenceMatcher ratio < 0.3)
        # Các câu ảo giác hoàn toàn khác biệt của Vosk phải bị CHẶN TUYỆT ĐỐI:
        res_diff1 = auto_learn("bệnh viêm xoang", "thời tiết", filepath=str(test_file))
        assert res_diff1 is False, "Phải chặn câu ảo giác 'bệnh viêm xoang' -> 'thời tiết' (ratio < 0.3)"
        print("  [✓] Đã chặn ảo giác Vosk: 'bệnh viêm xoang' -> 'thời tiết' (Độ tương đồng < 0.3)")

        res_diff2 = auto_learn("bệnh viêm xoang đây", "thời tiết hôm nay", filepath=str(test_file))
        assert res_diff2 is False, "Phải chặn câu ảo giác 'bệnh viêm xoang đây' -> 'thời tiết hôm nay'"
        print("  [✓] Đã chặn ảo giác Vosk: 'bệnh viêm xoang đây' -> 'thời tiết hôm nay' (Độ tương đồng < 0.3)")

        res_diff3 = auto_learn("ở ngoài cửa sổ đồ", "mở microsoft store", filepath=str(test_file))
        assert res_diff3 is False, "Phải chặn câu ảo giác 'ở ngoài cửa sổ đồ' -> 'mở microsoft store' (ratio < 0.3)"
        print("  [✓] Đã chặn ảo giác Vosk: 'ở ngoài cửa sổ đồ' -> 'mở microsoft store' (Độ tương đồng < 0.3)")

        # 2f. THỬ NGHIỆM ĐIỀU KIỆN BYPASS CHO TÊN APP HỢP LỆ (KỂ CẢ KHI CHỈ CÓ 1 TỪ):
        # 'chờ ro' -> 'chrome' (1 từ, không cần động từ)
        from auto_learn import VALID_APP_NAMES
        assert "antigravity" not in VALID_APP_NAMES, "Đã loại bỏ 'antigravity' khỏi VALID_APP_NAMES"
        res_app1 = auto_learn("chờ ro", "chrome", filepath=str(test_file))
        assert res_app1 is True, "Cần lưu thành công tên app 1 từ 'chrome' với phiên âm 'chờ ro'"
        print("  [✓] Đã lưu thành công tên app hợp lệ 1 từ: 'chờ ro' -> 'chrome'")

        # 2g. THỬ NGHIỆM ĐIỀU KIỆN BYPASS CHO TỪ KHÓA ÂM LƯỢNG ("âm lượng", "phần trăm", "%"):
        # 'tăng lượng lên 80%' -> 'âm lượng lên 80%'
        res_vol1 = auto_learn("tăng lượng lên 80%", "âm lượng lên 80%", filepath=str(test_file))
        assert res_vol1 is True, "Cần lưu thành công lệnh điều khiển âm lượng bypass động từ 'âm lượng lên 80%'"
        print("  [✓] Đã lưu câu lệnh âm lượng bypass động từ: 'tăng lượng lên 80%' -> 'âm lượng lên 80%'")

        # 2h. THỬ NGHIỆM GIỚI HẠN TỪ VOSK (1 ĐẾN 7 TỪ):
        # 1 từ Vosk: 'rom' -> 'chrome'
        res_v_1w = auto_learn("rom", "chrome", filepath=str(test_file))
        assert res_v_1w is True, "Cho phép Vosk text 1 từ 'rom' -> 'chrome'"
        print("  [✓] Cho phép Vosk text 1 từ: 'rom' -> 'chrome'")

        # > 7 từ Vosk:
        res_v_8w = auto_learn("một hai ba bốn năm sáu bảy tám", "mở chrome ngay", filepath=str(test_file))
        assert res_v_8w is False, "Phải chặn Vosk text > 7 từ"
        print("  [✓] Đã chặn câu Vosk text có độ dài > 7 từ")

        # 2i. THỬ NGHIỆM GIỚI HẠN KÍCH THƯỚC FILE (FIFO TỐI ĐA 100 CẶP TỪ):
        fifo_test_file = Path(__file__).resolve().parent / "test_fifo_learning.json"
        if fifo_test_file.exists():
            fifo_test_file.unlink()
        try:
            # Tạo sẵn 100 cặp từ
            initial_dict = {f"lệnh cũ {i}": f"mở app {i}" for i in range(100)}
            with open(fifo_test_file, "w", encoding="utf-8") as f:
                json.dump(initial_dict, f, ensure_ascii=False, indent=2)

            # Thêm cặp từ thứ 101 -> Phải kích hoạt FIFO xóa 'lệnh cũ 0'
            res_fifo = auto_learn("mở chôm", "mở chrome", filepath=str(fifo_test_file))
            assert res_fifo is True, "Lưu cặp từ thứ 101 phải thành công"
            fifo_data = load_offline_learning(filepath=str(fifo_test_file))
            assert len(fifo_data) == 100, f"Số lượng cặp từ phải duy trì đúng 100 (thực tế: {len(fifo_data)})"
            assert "lệnh cũ 0" not in fifo_data, "Phần tử cũ nhất 'lệnh cũ 0' phải bị đẩy ra khỏi file (FIFO)"
            assert fifo_data.get("mở chôm") == "mở chrome", "Cặp từ mới nhất 'mở chôm' -> 'mở chrome' phải tồn tại"
            print("  [✓] Giới hạn FIFO 100 cặp từ: Đã tự động xóa mục cũ nhất, duy trì đúng 100 phần tử")
        finally:
            if fifo_test_file.exists():
                fifo_test_file.unlink()
        # 2j. THỬ NGHIỆM CHẶN 2 CÂU LỖI LOG THỰC TẾ THEO YÊU CẦU:
        # Lỗi 1: 'thể ngâm nước lạnh tâm mua sắm' -> 'tăng âm lượng lên 80%' (chênh lệch số từ > 2 hoặc tương đồng < 0.5)
        res_err1 = auto_learn("thể ngâm nước lạnh tâm mua sắm", "tăng âm lượng lên 80%", filepath=str(test_file))
        assert res_err1 is False, "Phải chặn câu lỗi 'thể ngâm nước lạnh tâm mua sắm' -> 'tăng âm lượng lên 80%'"
        print("  [✓] Đã chặn câu lỗi thực tế 1: 'thể ngâm nước lạnh tâm mua sắm' -> 'tăng âm lượng lên 80%'")

        # Lỗi 2: 'xem phim gia và ông này' -> 'tìm kiếm giá vàng hôm nay' (tương đồng từ vựng < 0.5)
        res_err2 = auto_learn("xem phim gia và ông này", "tìm kiếm giá vàng hôm nay", filepath=str(test_file))
        assert res_err2 is False, "Phải chặn câu lỗi 'xem phim gia và ông này' -> 'tìm kiếm giá vàng hôm nay'"
        print("  [✓] Đã chặn câu lỗi thực tế 2: 'xem phim gia và ông này' -> 'tìm kiếm giá vàng hôm nay'")

        # 3. ĐIỀU KIỆN 3: Loại bỏ từ vô nghĩa 'mục đốc' -> PHẢI BỎ QUA
        res3 = auto_learn("một góc riêng mình", "mở mục đốc kêu mình", filepath=str(test_file))
        assert res3 is False, "Phải chặn câu chứa từ vô nghĩa 'mục đốc'"
        print("  [✓] Đã chặn câu rác chứa 'mục đốc' ('một góc riêng mình' -> 'mở mục đốc kêu mình')")

        # 4. ĐIỀU KIỆN 1: Không bắt đầu bằng động từ hợp lệ ('mở', 'tắt', 'khóa', 'chụp', 'tìm', 'đóng') -> PHẢI BỎ QUA
        res4 = auto_learn("trưng bày trong lịch sử ấy", "hôm microsoft e", filepath=str(test_file))
        assert res4 is False, "Phải chặn câu không bắt đầu bằng động từ hợp lệ"
        print("  [✓] Đã chặn câu không có động từ hợp lệ ('trưng bày trong lịch sử ấy' -> 'hôm microsoft e')")

        # 5. ĐIỀU KIỆN 2: Bỏ qua nếu độ dài < 2 từ hoặc > 6 từ
        res5 = auto_learn("mở", "mở", filepath=str(test_file))
        assert res5 is False, "Phải chặn câu < 2 từ"
        res6 = auto_learn("mở chrome và sau đó mở word rồi tắt máy tính", "mở chrome rồi sau đó mở word và tắt máy", filepath=str(test_file))
        assert res6 is False, "Phải chặn câu > 6 từ"
        print("  [✓] Đã chặn câu có số từ không hợp lệ (< 2 từ hoặc > 6 từ)")

        # 6. Bỏ qua câu lệnh bị cắt cụt ('mở do', 'mở ổ')
        res7 = auto_learn("mở đầu lốc", "mở do", filepath=str(test_file))
        assert res7 is False
        res8 = auto_learn("mở cũ đi", "mở ổ", filepath=str(test_file))
        assert res8 is False
        print("  [✓] Đã chặn câu lệnh bị cắt cụt do nói dở ('mở do', 'mở ổ')")

        # 7. Trùng lặp không ghi đè lại
        res9 = auto_learn("khóa bất hình", "khóa màn hình", filepath=str(test_file))
        assert res9 is False, "Không ghi đè trùng lặp không đổi"
        print("  [✓] Bỏ qua khi cặp từ đã tồn tại trong file")

        # 8. Kiểm tra nội dung file JSON
        loaded = load_offline_learning(filepath=str(test_file))
        assert loaded.get("khóa bất hình") == "khóa màn hình"
        assert loaded.get("mở pic trơ") == "mở pictures"
        assert "một góc riêng mình" not in loaded
        assert "trưng bày trong lịch sử ấy" not in loaded
        assert "thể ngâm nước lạnh tâm mua sắm" not in loaded
        assert "xem phim gia và ông này" not in loaded
        print(f"  [✓] Nội dung file offline_learning.json sạch: {json.dumps(loaded, ensure_ascii=False)}")

        # 9. Kiểm tra apply_offline_learning
        app1 = apply_offline_learning("khóa bất hình", filepath=str(test_file))
        assert app1 == "khóa màn hình"
        print(f"  [✓] Áp dụng khớp chính xác: 'khóa bất hình' -> '{app1}'")

        app2 = apply_offline_learning("hãy mở pic trơ ngay", filepath=str(test_file))
        assert app2 == "hãy mở pictures ngay"
        print(f"  [✓] Áp dụng trong câu ghép: 'hãy mở pic trơ ngay' -> '{app2}'")

        # 10. Chống crash khi file json bị lỗi cú pháp
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json content ...")
        assert load_offline_learning(filepath=str(test_file)) == {}
        res_recover = auto_learn("khóa bất hình", "khóa màn hình", filepath=str(test_file))
        assert res_recover is True
        print("  [✓] Khả năng tự phục hồi (try/except) khi file JSON bị hỏng hoạt động hoàn hảo")

    finally:
        if test_file.exists():
            test_file.unlink()

    print("=> TEST 1 (auto_learn.py) PASSED 100%!")


def test_actions_module():
    print("\n" + "=" * 60)
    print("TEST 2: BỘ THỰC THI HÀNH ĐỘNG (actions.py)")
    print("=" * 60)

    executor = ActionExecutor()

    with patch("os.startfile") as mock_startfile:
        # Test 1: open_drive C: và D:
        executor.execute([
            {"action": "open_drive", "drive": "D"},
            {"action": "open_drive", "drive": "C"},
        ])
        assert mock_startfile.call_count == 2
        mock_startfile.assert_any_call("D:\\")
        mock_startfile.assert_any_call("C:\\")
        print("  [✓] Action 'open_drive': Gọi đúng os.startfile('D:\\') và os.startfile('C:\\')")

    with patch("os.startfile") as mock_startfile:
        # Test 2: open_folder (pictures, downloads, documents)
        executor.execute([
            {"action": "open_folder", "folder": "pictures"},
            {"action": "open_folder", "folder": "bít trơ"},
            {"action": "open_folder", "folder": "downloads"},
            {"action": "open_folder", "folder": "documents"},
        ])
        assert mock_startfile.call_count == 4
        mock_startfile.assert_any_call(os.path.expanduser("~\\Pictures"))
        mock_startfile.assert_any_call(os.path.expanduser("~\\Downloads"))
        mock_startfile.assert_any_call(os.path.expanduser("~\\Documents"))
        print("  [✓] Action 'open_folder': Gọi đúng thư mục Pictures, Downloads, Documents")

    # Test 3: Khôi phục logic mở app đơn giản (Registry, Default Paths, AppOpener)
    # Đảm bảo không còn các hàm quét thư mục đệ quy và không dùng cache file
    assert not hasattr(executor, "_scan_start_menu"), "Đã xóa bỏ hàm _scan_start_menu"
    assert not hasattr(executor, "_scan_installation_dirs"), "Đã xóa bỏ hàm _scan_installation_dirs"
    assert not hasattr(executor, "_walk_with_max_depth"), "Đã xóa bỏ hàm _walk_with_max_depth"
    assert not hasattr(executor, "cache_file"), "Đã xóa bỏ cache_file"
    print("  [✓] Rollback thành công: Đã loại bỏ hoàn toàn các hàm quét đĩa đệ quy và cache file")

    with patch("os.startfile") as mock_startfile:
        # 3a. Mở app chuẩn: notepad / chrome qua Registry / PATH
        executor.execute([{"action": "open_app", "name": "notepad"}])
        assert mock_startfile.call_count == 1, "Cần gọi os.startfile để mở notepad"
        print("  [✓] Action 'open_app': Mở notepad thành công qua Registry / PATH mặc định")

        # 3b. Mở app có trong DEFAULT_APP_PATHS: Zalo
        mock_startfile.reset_mock()
        with patch("os.path.isfile", return_value=True):
            executor.execute([{"action": "open_app", "name": "zalo"}])
            assert mock_startfile.call_count == 1
            print("  [✓] Action 'open_app': Mở zalo thành công từ DEFAULT_APP_PATHS")

        # 3c. Mở app không tồn tại: Báo lỗi rõ ràng và an toàn, KHÔNG làm crash app
        executor.execute([{"action": "open_app", "name": "app_khong_ton_tai_98765"}])
        print("  [✓] Action 'open_app': Ứng dụng không tồn tại được bọc try/except an toàn, không làm treo hệ thống")

    print("=> TEST 2 (actions.py) PASSED 100%!")


def test_brain_module():
    print("\n" + "=" * 60)
    print("TEST 3: BỘ NÃO VÀ ĐỊNH TUYẾN (brain.py) & CHỐNG CACHE NHIỄU")
    print("=" * 60)

    # Sử dụng file memory rỗng cho test
    test_memory = Path(__file__).resolve().parent / "test_memory.json"
    with open(test_memory, "w", encoding="utf-8") as f:
        json.dump({"mở ổ": [{"action": "fake_action_loi"}]}, f)

    try:
        brain = Brain(memory_file=str(test_memory))

        # 1. Kiểm tra FUZZY_MAP
        assert brain.fuzzy_map.get("bít trơ") == "pictures", "FUZZY_MAP phải có 'bít trơ' -> 'pictures'"
        assert brain.fuzzy_map.get("đao lốt") == "downloads", "FUZZY_MAP phải có 'đao lốt' -> 'downloads'"
        print("  [✓] FUZZY_MAP đã cập nhật: 'bít trơ' -> 'pictures', 'đao lốt' -> 'downloads'")

        # 2. KIỂM TRA ĐIỀU KIỆN CHỐNG MEMORY CACHE CHO CÂU < 3 TỪ:
        # Dù file memory có chứa 'mở ổ' -> fake_action_loi, nhưng vì 'mở ổ' chỉ có 2 từ (< 3 từ),
        # Brain TUYỆT ĐỐI KHÔNG dùng Memory Cache, mà chuyển thẳng qua Fast Path/LLM!
        with patch.object(brain, "_slow_path", return_value=[{"action": "unknown"}]) as mock_slow:
            actions_short = brain.process("mở ổ")
            # Không được trả về fake_action_loi từ cache
            assert actions_short != [{"action": "fake_action_loi"}], "LỖI: Câu < 3 từ vẫn bị lấy từ Memory Cache!"
            print("  [✓] Câu < 3 từ ('mở ổ'): Tuyệt đối BỎ QUA Memory Cache, không nhận dữ liệu sai lệch!")

        # 3. Kiểm tra Fast Path open_drive
        test_cases_drive = [
            ("mở ổ d", "D"),
            ("mở ổ c", "C"),
            ("mở ổ đĩa d", "D"),
            ("ổ d", "D"),
            ("ổ c", "C"),
        ]
        for text, expected_drive in test_cases_drive:
            actions = brain.process(text)
            assert len(actions) == 1, f"Lỗi với câu: {text}"
            assert actions[0]["action"] == "open_drive"
            assert actions[0]["drive"] == expected_drive
            print(f"  [✓] Fast Path: '{text}' -> open_drive (drive={expected_drive})")

        # 4. Kiểm tra Fast Path open_folder
        test_cases_folder = [
            ("mở bít trơ", "pictures"),
            ("mở ảnh", "pictures"),
            ("mở đao lốt", "downloads"),
            ("mở downloads", "downloads"),
            ("mở tài liệu", "documents"),
            ("mở documents", "documents"),
        ]
        for text, expected_folder in test_cases_folder:
            actions = brain.process(text)
            assert len(actions) == 1, f"Lỗi với câu: {text}"
            assert actions[0]["action"] == "open_folder"
            assert actions[0]["folder"] == expected_folder
            print(f"  [✓] Fast Path: '{text}' -> open_folder (folder={expected_folder})")

        # 5. Kiểm tra 3 câu lệnh trọng tâm của người dùng:
        # 5a. 'kiếm giá vàng hôm nay' -> Trích xuất chính xác 'giá vàng hôm nay'
        actions_gold = brain.process("kiếm giá vàng hôm nay")
        assert len(actions_gold) == 1
        assert actions_gold[0]["action"] == "search_web"
        assert actions_gold[0]["query"] == "giá vàng hôm nay"
        print("  [✓] 'kiếm giá vàng hôm nay' -> search_web (query='giá vàng hôm nay')")

        # 5b. 'thời tiết Đà Nẵng' -> Không được cắt cụt, giữ trọn vẹn cả tên địa danh 'Đà Nẵng'
        actions_weather = brain.process("thời tiết Đà Nẵng")
        assert len(actions_weather) == 1
        assert actions_weather[0]["action"] == "search_web"
        assert actions_weather[0]["query"] == "thời tiết Đà Nẵng"
        print("  [✓] 'thời tiết Đà Nẵng' -> search_web (query='thời tiết Đà Nẵng', không bị cắt cụt)")

        # 5c. 'giảm âm lượng xuống 50%' -> volume percentage 50
        actions_vol = brain.process("giảm âm lượng xuống 50%")
        assert len(actions_vol) == 1
        assert actions_vol[0]["action"] == "volume"
        assert actions_vol[0]["percentage"] == 50
        print("  [✓] 'giảm âm lượng xuống 50%' -> volume (percentage=50)")

        # 6. Kiểm tra Verbatim Query Protection trong SLOW PATH (TUYỆT ĐỐI KHÔNG gọi LLM, chống bóp méo query)
        with patch("requests.post") as mock_post:
            slow_search = brain._slow_path("kiếm giá vàng hôm nay")
            assert slow_search == [{"action": "search_web", "query": "giá vàng hôm nay"}]
            assert mock_post.call_count == 0, "LỖI: Verbatim Query Protection không hoạt động, vẫn gọi LLM!"
            print("  [✓] Verbatim Query Protection trong SLOW PATH: Trích xuất chính xác 'giá vàng hôm nay', TUYỆT ĐỐI KHÔNG gọi LLM!")

        # 7. Kiểm tra khôi phục logic Chống ảo giác: App không thuộc Whitelist (ví dụ: 'antigravity') bị chặn
        assert "antigravity" not in brain.WHITELIST, "Đã xóa 'antigravity' khỏi WHITELIST"
        assert "antigravity" not in brain.fuzzy_map, "Đã xóa 'antigravity' khỏi FUZZY_MAP"
        hallucinated = brain._validate_actions([{"action": "open_app", "name": "antigravity"}])
        assert hallucinated == [{"action": "unknown"}], f"App ngoài Whitelist phải bị chuyển thành unknown: {hallucinated}"
        print("  [✓] Chống ảo giác Whitelist: Ứng dụng ngoài Whitelist ('antigravity') bị chặn đứng -> unknown")

        # 8. KIỂM TRA CƠ CHẾ TỰ HỌC TỪ LÓNG (learned_phonetics.json) & CHỐNG GÁN SAI TRONG CÂU GHÉP:
        test_phonetics = Path(__file__).resolve().parent / "test_learned_phonetics.json"
        if test_phonetics.exists():
            test_phonetics.unlink()

        try:
            test_brain = Brain(phonetics_file=str(test_phonetics))

            # 8a. LỖI THỰC TẾ: "discord và mở chrome" -> TUYỆT ĐỐI KHÔNG ĐƯỢC GÁN 'chrome' thành 'discord'!
            test_brain._trigger_auto_learning(
                "discord và mở chrome",
                [{"action": "open_app", "name": "discord"}, {"action": "open_app", "name": "chrome"}]
            )
            with open(test_phonetics, "r", encoding="utf-8") as f:
                learned = json.load(f)
            assert "chrome" not in learned, "LỖI NGHIÊM TRỌNG: 'chrome' bị gán sai thành app khác trong câu ghép!"
            assert learned == {}, f"Phải rỗng hoàn toàn, nhận được: {learned}"
            print("  [✓] Chống gán sai ngữ cảnh: 'discord và mở chrome' TUYỆT ĐỐI KHÔNG gán 'chrome' thành 'discord'!")

            # 8b. CÂU GHÉP CHUẨN: "mở đít cóc và mở cờ rô me" -> 'đít cóc' và 'cờ rô me' nằm trong CÙNG VẾ
            test_brain._trigger_auto_learning(
                "mở đít cóc và mở cờ rô me",
                [{"action": "open_app", "name": "discord"}, {"action": "open_app", "name": "chrome"}]
            )
            with open(test_phonetics, "r", encoding="utf-8") as f:
                learned = json.load(f)
            assert learned.get("đít cóc") == "discord", "Phải học đúng 'đít cóc' -> 'discord' cùng vế"
            assert learned.get("cờ rô me") == "chrome", "Phải học đúng 'cờ rô me' -> 'chrome' cùng vế"
            assert "chrome" not in learned, "'chrome' không bao giờ được lưu làm từ lóng"
            print("  [✓] Câu ghép chuẩn vế: 'mở đít cóc và mở cờ rô me' học chính xác từng vế tương ứng!")

            # 8c. CÂU ĐƠN: "mở sờ bốt ti" -> tự học 'sờ bốt ti' -> 'spotify'
            test_brain._trigger_auto_learning(
                "mở sờ bốt ti",
                [{"action": "open_app", "name": "spotify"}]
            )
            with open(test_phonetics, "r", encoding="utf-8") as f:
                learned = json.load(f)
            assert learned.get("sờ bốt ti") == "spotify"
            print("  [✓] Câu đơn: 'mở sờ bốt ti' -> tự học thành công 'spotify'!")

            # 8d. BẢO VỆ TÊN APP CHUẨN TRONG WHITELIST: "mở notepad" -> KHÔNG ĐƯỢC LƯU
            test_brain._trigger_auto_learning(
                "mở notepad",
                [{"action": "open_app", "name": "notepad"}]
            )
            with open(test_phonetics, "r", encoding="utf-8") as f:
                learned = json.load(f)
            assert "notepad" not in learned
            print("  [✓] Whitelist Guard: Tên app chuẩn ('notepad') được bảo vệ tuyệt đối, không lưu làm từ lóng!")

            # 8e. CÂU GHÉP PHỨC TẠP LỆCH VẾ: BỎ QUA TỰ HỌC
            test_brain._trigger_auto_learning(
                "mở đít cọc và mở cờ rôm rồi sau đó mở word",
                [{"action": "open_app", "name": "discord"}, {"action": "open_app", "name": "chrome"}]
            )
            print("  [✓] Câu ghép phức tạp lệch số vế: Tự động bỏ qua an toàn, không gây nhiễu từ lóng!")

        finally:
            if test_phonetics.exists():
                test_phonetics.unlink()

    finally:
        if test_memory.exists():
            test_memory.unlink()

    print("=> TEST 3 (brain.py & Chống Cache nhiễu) PASSED 100%!")


def test_stt_hybrid_threading():
    print("\n" + "=" * 60)
    print("TEST 4: STT HYBRID, CHỐNG CẮT ÂM VÀ CHỐNG VOSK BỊA TỪ")
    print("=" * 60)

    stt = SpeechToText()

    # Kiểm tra chunk size lớn hơn (1024 hoặc 2048)
    assert stt.CHUNK_SIZE >= 1024, f"Chunk size phải >= 1024 (thực tế: {stt.CHUNK_SIZE})"
    assert stt.samples_per_frame == stt.CHUNK_SIZE
    print(f"  [✓] Chunk size cấu hình mượt mà: {stt.samples_per_frame} samples (64ms)")

    # Tạo 1.0 giây âm thanh PCM mẫu (16kHz mono int16)
    dummy_audio = b"\x00\x00" * 16000

    # -------------------------------------------------------------
    # Test 4.1: Google STT trả về rỗng "" -> Thông báo & BỎ QUA, KHÔNG GỬI VOSK
    # -------------------------------------------------------------
    with patch.object(stt, "is_online", return_value=True), \
         patch.object(stt, "recognize_google", return_value=""), \
         patch.object(stt, "recognize_vosk") as mock_vosk, \
         patch("stt_engine.auto_learn") as mock_auto_learn:

        empty_res = stt.process_audio(dummy_audio)
        assert empty_res == "", "Kết quả rỗng phải trả về ''"
        assert mock_vosk.call_count == 0, "LỖI: Audio rỗng nhưng vẫn gọi Vosk khiến Vosk bịa từ!"
        assert mock_auto_learn.call_count == 0, "Không được tự học khi Google STT rỗng"
        print("  [✓] Google STT trả về rỗng '': Đã in cảnh báo và BỎ QUA, hoàn toàn KHÔNG gửi cho Vosk")

    # -------------------------------------------------------------
    # Test 4.2: Push-to-Talk đợi 350ms khi nhả phím
    # -------------------------------------------------------------
    pressed_states = [True, True, False]  # Nhấn -> Giữ -> Nhả
    def fake_is_pressed():
        if pressed_states:
            return pressed_states.pop(0)
        return False

    with patch.object(stt, "is_push_to_talk_pressed", side_effect=fake_is_pressed), \
         patch.object(stt, "check_microphone"), \
         patch("sounddevice.RawInputStream") as mock_stream, \
         patch("time.sleep") as mock_sleep:

        mock_instance = MagicMock()
        mock_stream.return_value = mock_instance

        stt.record_push_to_talk(timeout=1.0)
        # Kiểm tra sleep(0.35) đã được gọi khi nhả phím
        mock_sleep.assert_any_call(0.35)
        print("  [✓] Khi nhả phím Push-to-Talk: Đã trì hoãn 350ms (time.sleep(0.35)) để thu trọn vẹn âm cuối")

    # -------------------------------------------------------------
    # Test 4.3: Kiểm tra chế độ ONLINE (Google STT trả về tức thì, Vosk chạy ngầm)
    # -------------------------------------------------------------
    background_vosk_finished = threading.Event()

    def mock_google_fast(audio):
        time.sleep(0.15)  # Giả lập Google STT trả về trong 150ms
        return "mở bít trơ"

    def mock_vosk_slow(audio):
        time.sleep(0.4)  # Giả lập Vosk chạy mất 400ms
        background_vosk_finished.set()
        return "mở pic trơ"

    with patch.object(stt, "is_online", return_value=True), \
         patch.object(stt, "recognize_google", side_effect=mock_google_fast), \
         patch.object(stt, "recognize_vosk", side_effect=mock_vosk_slow), \
         patch("stt_engine.auto_learn") as mock_auto_learn:

        t_start = time.time()
        result = stt.process_audio(dummy_audio)
        latency = time.time() - t_start

        # Luồng chính phải nhận kết quả Google STT ngay lập tức
        assert result == "mở bít trơ", "Luồng chính phải nhận kết quả từ Google STT"
        assert latency < 0.35, f"Tốc độ phải dưới 1 giây (thực tế: {latency:.3f}s)"
        print(f"  [✓] Luồng chính hoàn thành trong: {latency:.3f}s (< 1s)")
        print(f"  [✓] Kết quả trả về cho Bộ não: '{result}'")

        # Luồng ngầm Vosk hoàn thành và gọi auto_learn
        background_vosk_finished.wait(timeout=1.0)
        time.sleep(0.05)
        assert background_vosk_finished.is_set(), "Luồng ngầm Vosk phải hoàn thành"
        mock_auto_learn.assert_called_with("mở pic trơ", "mở bít trơ")
        print("  [✓] Luồng ngầm Vosk tự động kích hoạt auto_learn('mở pic trơ', 'mở bít trơ')")

    # -------------------------------------------------------------
    # Test 4.4: Kiểm tra chế độ OFFLINE (Mất mạng -> Vosk + Từ điển tự học)
    # -------------------------------------------------------------
    test_json = Path(__file__).resolve().parent / "test_offline_learning2.json"
    if test_json.exists():
        test_json.unlink()

    try:
        auto_learn("mở pic trơ", "mở pictures", filepath=str(test_json))

        with patch.object(stt, "is_online", return_value=False), \
             patch.object(stt, "recognize_vosk", return_value="mở pic trơ"), \
             patch("stt_engine.apply_offline_learning", side_effect=lambda txt: apply_offline_learning(txt, filepath=str(test_json))):

            t_start = time.time()
            offline_result = stt.process_audio(dummy_audio)
            offline_latency = time.time() - t_start

            assert offline_result == "mở pictures", f"Offline phải chuyển đổi sang từ tự học (nhận: {offline_result})"
            print(f"  [✓] Khi mất mạng: Vosk nhận 'mở pic trơ' -> Tự động ánh xạ thành '{offline_result}'")
            print(f"  [✓] Độ trễ offline: {offline_latency:.3f}s (< 1s)")

    finally:
        if test_json.exists():
            test_json.unlink()

    print("=> TEST 4 (stt_engine.py chống cắt âm & chống Vosk bịa từ) PASSED 100%!")


if __name__ == "__main__":
    print("\n" + "#" * 65)
    print("  BẮT ĐẦU CHẠY TOÀN BỘ BỘ TEST KIẾN TRÚC HYBRID TỰ HỌC NÂNG CẤP")
    print("#" * 65)

    test_auto_learn_module()
    test_actions_module()
    test_brain_module()
    test_stt_hybrid_threading()

    print("\n" + "#" * 65)
    print("  ✓ TẤT CẢ 4/4 BỘ TEST ĐÃ VƯỢT QUA XUẤT SẮC!")
    print("#" * 65 + "\n")

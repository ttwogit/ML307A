# HƯỚNG DẪN ĐỌC TỌA ĐỘ GPS TỪ MODULE ML307A

Tệp Python `read_gps.py` hỗ trợ đọc vị trí GPS từ module **China Mobile OneMO ML307A (4G Cat.1 + GNSS)** qua giao tiếp Serial, tương thích 100% trên cả **PC (Windows / Linux / macOS)** và **Android (Termux qua cáp USB OTG)**.

---

## 1. Cơ chế hoạt động & Tập lệnh AT (dựa trên `Command.txt`)

Module ML307A hỗ trợ tập lệnh AT cho bộ thu định vị GNSS:
- `AT`: Kiểm tra kết nối nối tiếp với module.
- `ATI` / `AT+CGMM`: Xác định phiên bản phần cứng và firmware module.
- `AT+MGNSS?`: Kiểm tra trạng thái nguồn bộ thu GNSS (`1` = Bật, `0` = Tắt).
- `AT+MGNSS=1`: Bật nguồn hệ thống định vị vệ tinh GNSS (GPS + BeiDou + GLONASS).
- `AT+MGNSS=0`: Tắt bộ thu GNSS khi dừng chương trình (tiết kiệm điện năng).
- **Luồng bản tin NMEA**: Sau khi bật `AT+MGNSS=1`, module tự động đẩy các bản tin chuẩn `$GNGGA`, `$GNRMC`, `$GPGSA`, `$BDGSA`,... ra cổng Serial mỗi giây. Chương trình phân tích các bản tin này để tính toán tọa độ, độ cao, tốc độ, số vệ tinh và tạo link Google Maps.

---

## 2. Cài đặt thư viện yêu cầu

Yêu cầu duy nhất là thư viện `pyserial`:

### Trên PC (Windows / Linux / macOS):
```bash
pip install pyserial
```

### Trên Android (Termux):
```bash
pkg update
pkg install python
pip install pyserial
```

---

## 3. Hướng dẫn chạy chương trình

### Cách 1: Tự động dò tìm cổng (khuyên dùng)
```bash
python read_gps.py
```
Chương trình sẽ tự động quét danh sách cổng kết nối (COM trên Windows, /dev/ttyUSB* trên Linux/Termux) và hiển thị menu cho bạn chọn.

### Cách 2: Chỉ định cổng trực tiếp
- **Trên Windows (Ví dụ COM9):**
  ```bash
  python read_gps.py -p COM9
  ```
- **Trên Linux hoặc Termux Android:**
  ```bash
  python3 read_gps.py -p /dev/ttyUSB0
  ```
  *(hoặc `/dev/ttyACM0` tùy theo chip chuyển đổi USB-to-UART)*

---

## 4. Các tùy chọn nâng cao (Arguments)

| Tham số | Ý nghĩa | Ví dụ |
| :--- | :--- | :--- |
| `-p`, `--port` | Tên cổng Serial | `-p COM9` hoặc `-p /dev/ttyUSB0` |
| `-b`, `--baud` | Tốc độ Baud (mặc định: 115200) | `-b 115200` |
| `--clear` | Cố định giao diện bảng, xóa màn hình mỗi lần cập nhật | `python read_gps.py --clear` |
| `--raw` | In trực tiếp các chuỗi NMEA thô từ module | `python read_gps.py --raw` |
| `--save <file.csv>` | Tự động ghi lại các tọa độ GPS thu được vào file CSV | `python read_gps.py --save gps_log.csv` |
| `--keep-gnss` | Giữ bộ thu GNSS tiếp tục bật sau khi thoát chương trình | `python read_gps.py --keep-gnss` |

---

## 5. Lưu ý quan trọng khi dùng trên Termux (Android)

1. **Kết nối phần cứng:** Sử dụng cáp **USB OTG** cắm từ điện thoại Android vào cổng USB/UART của module.
2. **Quyền truy cập cổng Serial trên Android:**
   - Hầu hết các adapter USB-to-UART (CH340, CP2102, FT232, PL2303, STM32 Virtual COM) khi cắm qua OTG trên thiết bị có quyền root sẽ tạo thiết bị tại `/dev/ttyUSB0` hoặc `/dev/ttyACM0`.
   - Nếu gặp lỗi `Permission Denied`, hãy cấp quyền đọc/ghi bằng lệnh:
     ```bash
     su -c 'chmod 666 /dev/ttyUSB0'
     ```
3. **Bắt sóng vệ tinh:**
   - Khi ở trong nhà kín hoặc phòng bê tông, tín hiệu vệ tinh GPS có thể bị chặn (hiển thị `CHƯA ĐỊNH VỊ`).
   - Hãy đưa ăng-ten GPS ra ngoài trời thoáng hoặc sát cửa sổ. Quá trình bắt sóng lần đầu (Cold Start) thường mất từ 30 giây đến 2 phút.

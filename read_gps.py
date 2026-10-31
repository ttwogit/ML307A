#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HỆ THỐNG ĐỌC VỊ TRÍ GPS TỪ MODULE ML307A QUA CỔNG SERIAL
Tương thích hoàn toàn trên:
- PC (Windows, Linux, macOS)
- Android (Termux qua cáp USB OTG)

Tập lệnh AT sử dụng từ Command.txt:
- AT          : Kiểm tra giao tiếp
- ATI         : Đọc thông tin phiên bản module ML307A
- AT+MGNSS?   : Kiểm tra trạng thái bộ thu GNSS
- AT+MGNSS=1  : Bật nguồn định vị vệ tinh GNSS
- AT+MGNSS=0  : Tắt nguồn GNSS (tiết kiệm năng lượng khi thoát)
- NMEA Stream : Đọc bản tin chuẩn $GNGGA, $GNRMC, $GPGGA,...
"""

import sys
import os
import time
import glob
import argparse
from datetime import datetime

# Đảm bảo terminal hiển thị đúng tiếng Việt có dấu (UTF-8) trên cả Windows và Termux
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("\n[!] LỖI: Chưa cài đặt thư viện 'pyserial'.")
    print("    Vui lòng cài đặt bằng lệnh:")
    print("    pip install pyserial\n")
    print("    Trên Termux (Android):")
    print("    pkg install python && pip install pyserial\n")
    sys.exit(1)


class GPSData:
    """Lớp lưu trữ và xử lý dữ liệu vị trí GPS"""
    def __init__(self):
        self.lat_decimal = None
        self.lon_decimal = None
        self.lat_dir = None
        self.lon_dir = None
        self.altitude = None
        self.speed_kmh = None
        self.course = None
        self.satellites = 0
        self.fix_quality = 0      # 0: No fix, 1: GPS SPS, 2: DGPS, 4: RTK Fixed, 5: RTK Float
        self.fix_status = "V"      # 'A' = Valid (Hợp lệ), 'V' = Void / Warning (Chưa khóa)
        self.utc_time = None
        self.date = None
        self.hdop = None
        self.last_update = None

    @property
    def is_fixed(self):
        """Kiểm tra xem GPS đã định vị thành công hay chưa"""
        return (self.fix_status == "A" or self.fix_quality > 0) and self.lat_decimal is not None

    @property
    def maps_url(self):
        """Tạo đường link Google Maps xem trực tiếp vị trí"""
        if self.lat_decimal is not None and self.lon_decimal is not None:
            return f"https://www.google.com/maps?q={self.lat_decimal:.6f},{self.lon_decimal:.6f}"
        return None


def convert_nmea_coord(raw_coord, direction):
    """
    Chuyển đổi tọa độ từ định dạng NMEA (ddmm.mmmm hoặc dddmm.mmmm)
    sang Decimal Degrees (độ thập phân).
    Ví dụ: '2101.5543', 'N'  ->  21.025905
           '10547.8832', 'E' -> 105.798053
    """
    if not raw_coord or not direction:
        return None
    try:
        val = float(raw_coord)
        deg = int(val // 100)
        minutes = val % 100
        decimal_val = deg + (minutes / 60.0)
        if direction.upper() in ['S', 'W']:
            decimal_val = -decimal_val
        return decimal_val
    except (ValueError, TypeError):
        return None


def verify_nmea_checksum(sentence):
    """Xác thực Checksum NMEA (phép XOR của các ký tự nằm giữa $ và *)"""
    sentence = sentence.strip()
    if not sentence.startswith('$') or '*' not in sentence:
        return False
    try:
        body, ck_hex = sentence[1:].split('*', 1)
        calc_ck = 0
        for char in body:
            calc_ck ^= ord(char)
        return f"{calc_ck:02X}".upper() == ck_hex[:2].upper()
    except Exception:
        return False


def parse_nmea_sentence(sentence, gps_data):
    """Phân tích các bản tin NMEA chuẩn ($GNGGA, $GNRMC, $GPGGA, v.v.)"""
    sentence = sentence.strip()
    if not sentence.startswith('$'):
        return False

    # Xác thực Checksum nếu có
    if '*' in sentence and not verify_nmea_checksum(sentence):
        return False

    body = sentence[1:].split('*')[0]
    parts = body.split(',')
    tag = parts[0].upper()
    msg_type = tag[-3:] if len(tag) >= 3 else tag

    updated = False

    # 1. Bản tin RMC (Vận tốc, hướng, tọa độ, trạng thái khóa A/V)
    if msg_type == "RMC" and len(parts) >= 10:
        utc_str = parts[1]
        status = parts[2].upper()
        raw_lat = parts[3]
        lat_dir = parts[4]
        raw_lon = parts[5]
        lon_dir = parts[6]
        speed_knots = parts[7]
        course_deg = parts[8]
        date_str = parts[9]

        gps_data.fix_status = status
        if utc_str:
            gps_data.utc_time = utc_str
        if date_str:
            gps_data.date = date_str

        if status == 'A' and raw_lat and raw_lon:
            gps_data.lat_decimal = convert_nmea_coord(raw_lat, lat_dir)
            gps_data.lon_decimal = convert_nmea_coord(raw_lon, lon_dir)
            gps_data.lat_dir = lat_dir
            gps_data.lon_dir = lon_dir

            if speed_knots:
                try:
                    gps_data.speed_kmh = float(speed_knots) * 1.852
                except ValueError:
                    pass

            if course_deg:
                try:
                    gps_data.course = float(course_deg)
                except ValueError:
                    pass
        gps_data.last_update = time.time()
        updated = True

    # 2. Bản tin GGA (Số vệ tinh, độ cao, sai số HDOP, loại Fix)
    elif msg_type == "GGA" and len(parts) >= 10:
        utc_str = parts[1]
        raw_lat = parts[2]
        lat_dir = parts[3]
        raw_lon = parts[4]
        lon_dir = parts[5]
        quality_str = parts[6]
        sats_str = parts[7]
        hdop_str = parts[8]
        alt_str = parts[9]

        if utc_str:
            gps_data.utc_time = utc_str

        try:
            gps_data.fix_quality = int(quality_str) if quality_str else 0
        except ValueError:
            pass

        try:
            gps_data.satellites = int(sats_str) if sats_str else 0
        except ValueError:
            pass

        try:
            gps_data.hdop = float(hdop_str) if hdop_str else None
        except ValueError:
            pass

        try:
            gps_data.altitude = float(alt_str) if alt_str else None
        except ValueError:
            pass

        if gps_data.fix_quality > 0 and raw_lat and raw_lon:
            gps_data.lat_decimal = convert_nmea_coord(raw_lat, lat_dir)
            gps_data.lon_decimal = convert_nmea_coord(raw_lon, lon_dir)
            gps_data.lat_dir = lat_dir
            gps_data.lon_dir = lon_dir

        gps_data.last_update = time.time()
        updated = True

    return updated


def list_available_ports():
    """Tự động phát hiện các cổng kết nối Serial trên PC và Termux"""
    ports = []
    # Quét qua pyserial
    try:
        found = serial.tools.list_ports.comports()
        for p in found:
            ports.append((p.device, p.description))
    except Exception:
        pass

    # Quét các đường dẫn Linux / Android / Termux
    existing = [p[0] for p in ports]
    extra_paths = (
        glob.glob("/dev/ttyUSB*") +
        glob.glob("/dev/ttyACM*") +
        glob.glob("/dev/ttyS*") +
        glob.glob("/dev/rfcomm*")
    )
    for path in extra_paths:
        if path not in existing:
            ports.append((path, "USB/Serial Converter"))

    return ports


def select_serial_port(preferred_port=None):
    """Chọn hoặc nhập cổng Serial"""
    if preferred_port:
        return preferred_port

    ports = list_available_ports()
    if not ports:
        print("[!] Không tìm thấy cổng Serial tự động.")
        print("    - Windows: COM1, COM2, COM9...")
        print("    - Termux / Linux: /dev/ttyUSB0, /dev/ttyACM0...")
        return input("-> Nhập cổng Serial thủ công: ").strip() or None

    if len(ports) == 1:
        port_dev, desc = ports[0]
        print(f"[*] Tìm thấy 1 cổng kết nối: {port_dev} ({desc})")
        ans = input(f"-> Sử dụng cổng này? [Y/n]: ").strip().lower()
        if ans in ['', 'y', 'yes']:
            return port_dev

    print("\nDanh sách cổng Serial khả dụng:")
    for i, (port_dev, desc) in enumerate(ports, start=1):
        print(f"  [{i}] {port_dev} - {desc}")
    print(f"  [{len(ports)+1}] Nhập cổng thủ công")

    while True:
        choice = input(f"-> Chọn số (1-{len(ports)+1}): ").strip()
        if choice.isdigit():
            c = int(choice)
            if 1 <= c <= len(ports):
                return ports[c - 1][0]
            elif c == len(ports) + 1:
                return input("-> Nhập tên cổng: ").strip() or None
        print("[!] Vui lòng chọn lại số hợp lệ.")


def send_at_command(ser, cmd, timeout=0.8):
    """Gửi một lệnh AT tới module và nhận danh sách phản hồi"""
    ser.reset_input_buffer()
    cmd_bytes = (cmd + "\r\n").encode("utf-8")
    ser.write(cmd_bytes)
    time.sleep(0.08)

    start_time = time.time()
    response = []
    while time.time() - start_time < timeout:
        line = ser.readline().decode("latin1", errors="ignore").strip()
        if line:
            response.append(line)
            if "OK" in line or "ERROR" in line:
                break
    return response


def initialize_ml307a(ser):
    """
    Khởi tạo module ML307A theo tài liệu Command.txt:
    1. Kiểm tra kết nối AT
    2. Đọc phiên bản phần cứng/firmware (ATI)
    3. Kiểm tra trạng thái GNSS (AT+MGNSS?)
    4. Bật GNSS nếu chưa bật (AT+MGNSS=1)
    """
    print("[*] Đang kiểm tra kết nối với module ML307A...")
    resp = send_at_command(ser, "AT", timeout=0.4)
    if not any("OK" in r for r in resp):
        resp = send_at_command(ser, "AT", timeout=0.4)

    # Đọc model info
    info = send_at_command(ser, "ATI", timeout=0.4)
    info_lines = [l for l in info if l and "OK" not in l and "ATI" not in l]
    if info_lines:
        print(f"[*] Module nhận diện: {' | '.join(info_lines)}")

    # Kiểm tra trạng thái GNSS
    print("[*] Kiểm tra trạng thái GNSS (AT+MGNSS?)...")
    gnss_resp = send_at_command(ser, "AT+MGNSS?", timeout=0.6)
    gnss_on = any("+MGNSS: 1" in r for r in gnss_resp)

    if not gnss_on:
        print("[*] GNSS đang tắt. Đang gửi lệnh bật: AT+MGNSS=1 ...")
        send_at_command(ser, "AT+MGNSS=1", timeout=1.0)
        time.sleep(1.0)
        check = send_at_command(ser, "AT+MGNSS?", timeout=0.6)
        if any("+MGNSS: 1" in r for r in check):
            print("[+] Kích hoạt GNSS thành công! Module đang nhận tín hiệu vệ tinh.")
        else:
            print("[*] Đã gửi lệnh kích hoạt GNSS (AT+MGNSS=1).")
    else:
        print("[+] GNSS đã sẵn sàng và đang hoạt động.")


def format_gps_dashboard(gps, raw_line=None, show_raw=False):
    """Tạo bảng giao diện hiển thị tọa độ GPS đẹp mắt"""
    if gps.is_fixed:
        quality_map = {
            1: "ĐÃ KHÓA VỊ TRÍ (GPS Standard 2D/3D)",
            2: "ĐÃ KHÓA VỊ TRÍ (DGPS/SBAS)",
            4: "ĐÃ KHÓA VỊ TRÍ (RTK Fixed)",
            5: "ĐÃ KHÓA VỊ TRÍ (RTK Float)"
        }
        fix_label = quality_map.get(gps.fix_quality, "ĐÃ KHÓA VỊ TRÍ (Hợp lệ)")
    else:
        fix_label = "CHƯA ĐỊNH VỊ (Đang tìm kiếm vệ tinh ngoài trời...)"

    lat_str = f"{gps.lat_decimal:.6f}° {gps.lat_dir or ''}" if gps.lat_decimal is not None else "Đang chờ..."
    lon_str = f"{gps.lon_decimal:.6f}° {gps.lon_dir or ''}" if gps.lon_decimal is not None else "Đang chờ..."
    alt_str = f"{gps.altitude:.1f} m" if gps.altitude is not None else "---"
    spd_str = f"{gps.speed_kmh:.2f} km/h" if gps.speed_kmh is not None else "---"
    course_str = f"{gps.course:.1f}°" if gps.course is not None else "---"
    hdop_str = f"{gps.hdop:.2f}" if gps.hdop is not None else "---"

    time_str = "---"
    if gps.utc_time and len(gps.utc_time) >= 6:
        hh = gps.utc_time[0:2]
        mm = gps.utc_time[2:4]
        ss = gps.utc_time[4:6]
        time_str = f"{hh}:{mm}:{ss} UTC"

    date_str = "---"
    if gps.date and len(gps.date) == 6:
        dd = gps.date[0:2]
        mo = gps.date[2:4]
        yy = "20" + gps.date[4:6]
        date_str = f"{dd}/{mo}/{yy}"

    lines = [
        "",
        "=" * 65,
        "             HỆ THỐNG ĐỌC TỌA ĐỘ GPS (ML307A)",
        "=" * 65,
        f" Trạng thái định vị : {fix_label}",
        f" Vệ tinh kết nối    : {gps.satellites} vệ tinh",
        f" Vĩ độ (Latitude)   : {lat_str}",
        f" Kinh độ (Longitude): {lon_str}",
        f" Độ cao (Altitude)  : {alt_str}",
        f" Tốc độ di chuyển   : {spd_str}",
        f" Hướng di chuyển    : {course_str}",
        f" Sai số vị trí HDOP : {hdop_str}",
        f" Ngày & Giờ         : {date_str} - {time_str}",
    ]
    if gps.maps_url:
        lines.append(f" Link Google Maps   : {gps.maps_url}")
    else:
        lines.append(" Link Google Maps   : [Sẽ hiển thị khi nhận đủ tín hiệu vệ tinh]")
    lines.append("=" * 65)
    lines.append(" [Nhấn Ctrl + C để dừng chương trình]")

    if show_raw and raw_line:
        lines.append(f" [NMEA Raw]: {raw_line}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Đọc vị trí GPS từ module ML307A qua cổng Serial (Tương thích PC & Termux)"
    )
    parser.add_argument("-p", "--port", type=str, default=None,
                        help="Cổng Serial (VD: COM9 trên Windows, /dev/ttyUSB0 trên Termux/Linux)")
    parser.add_argument("-b", "--baud", type=int, default=115200,
                        help="Tốc độ Baudrate (mặc định: 115200)")
    parser.add_argument("--raw", action="store_true",
                        help="In chuỗi bản tin NMEA thô ra màn hình")
    parser.add_argument("--save", type=str, default=None,
                        help="Lưu tọa độ vào file CSV (VD: gps_data.csv)")
    parser.add_argument("--keep-gnss", action="store_true",
                        help="Không gửi lệnh tắt GNSS khi thoát chương trình")
    parser.add_argument("--clear", action="store_true",
                        help="Xóa màn hình trước mỗi lần cập nhật để bảng hiển thị cố định")
    args = parser.parse_args()

    port = select_serial_port(args.port)
    if not port:
        print("[!] Không có cổng nào được chọn. Đã kết thúc.")
        return

    print(f"\n[*] Đang mở kết nối tới cổng {port} ({args.baud} bps)...")
    try:
        ser = serial.serial_for_url(port, baudrate=args.baud, timeout=1.0)
    except Exception as e:
        print(f"[!] Không thể mở cổng {port}: {e}")
        if "Permission" in str(e) or "denied" in str(e).lower():
            print("    -> Trên Termux/Linux: Hãy cấp quyền truy cập:")
            print(f"       su -c 'chmod 666 {port}'")
        return

    # Khởi tạo module ML307A & kích hoạt GNSS
    initialize_ml307a(ser)

    gps = GPSData()
    last_print = 0
    csv_file = None

    if args.save:
        try:
            file_exists = os.path.exists(args.save) and os.path.getsize(args.save) > 0
            csv_file = open(args.save, "a", encoding="utf-8")
            if not file_exists:
                csv_file.write("timestamp,date,utc_time,latitude,longitude,altitude,speed_kmh,satellites,fix_quality,maps_url\n")
            print(f"[+] Dữ liệu sẽ được tự động ghi vào: {args.save}")
        except Exception as e:
            print(f"[!] Không thể mở file ghi: {e}")

    print("\n[*] Đang lắng nghe dữ liệu GPS từ module...")
    print("    (Mẹo: Đặt ăng-ten GPS ở nơi thoáng ngoài trời hoặc sát cửa sổ để bắt vệ tinh nhanh nhất)\n")

    try:
        while True:
            raw_line = ser.readline().decode("latin1", errors="ignore").strip()
            if not raw_line:
                continue

            # Phân tích dòng bản tin NMEA
            if raw_line.startswith('$'):
                parse_nmea_sentence(raw_line, gps)
                now = time.time()

                # Cập nhật thông tin hiển thị mỗi giây
                if now - last_print >= 1.0:
                    last_print = now

                    if args.clear:
                        # ANSI clear screen & home cursor
                        sys.stdout.write("\033[H\033[J")
                        sys.stdout.flush()

                    dashboard_text = format_gps_dashboard(gps, raw_line=raw_line, show_raw=args.raw)
                    print(dashboard_text)

                    # Ghi tọa độ hợp lệ ra file CSV
                    if csv_file and gps.is_fixed and gps.lat_decimal is not None:
                        ts = datetime.now().isoformat()
                        csv_file.write(
                            f"{ts},{gps.date or ''},{gps.utc_time or ''},{gps.lat_decimal:.6f},"
                            f"{gps.lon_decimal:.6f},{gps.altitude or ''},{gps.speed_kmh or ''},"
                            f"{gps.satellites},{gps.fix_quality},{gps.maps_url}\n"
                        )
                        csv_file.flush()

            elif "+MGNSSLOC:" in raw_line and args.raw:
                print(f" [MGNSSLOC]: {raw_line}")

    except KeyboardInterrupt:
        print("\n\n[*] Người dùng bấm ngắt (Ctrl + C)...")
    finally:
        if csv_file:
            csv_file.close()

        if not args.keep_gnss:
            print("[*] Gửi lệnh tắt GNSS để tiết kiệm năng lượng (AT+MGNSS=0)...")
            try:
                send_at_command(ser, "AT+MGNSS=0", timeout=1.0)
                print("[+] Đã tắt GNSS an toàn.")
            except Exception:
                pass

        try:
            ser.close()
            print("[+] Đã đóng kết nối cổng Serial.")
        except Exception:
            pass


if __name__ == "__main__":
    main()

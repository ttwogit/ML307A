#!/data/data/com.termux/files/usr/bin/bash
# Script hỗ trợ chạy GPS trên Termux tự động cấp quyền và chọn chế độ

echo "================================================="
echo "       KHỞI CHẠY GPS ML307A TRÊN TERMUX         "
echo "================================================="
echo "Chọn phương thức kết nối:"
echo " [1] USB OTG trực tiếp (/dev/ttyUSB0 hoặc /dev/ttyACM0 - Cần Root)"
echo " [2] Qua TCP Socket Bridge (socket://localhost:8888 - Không cần Root)"
echo " [3] Sửa lỗi thư viện pyserial (Cài đặt lại sạch sẽ)"
echo "================================================="
read -p "-> Lựa chọn của bạn (1/2/3): " choice

if [ "$choice" = "1" ]; then
    echo "[*] Đang thử cấp quyền đọc/ghi cho cổng USB Serial..."
    su -c "chmod 666 /dev/ttyUSB* /dev/ttyACM* 2>/dev/null"
    
    # Tìm cổng khả dụng
    PORT=""
    if [ -e /dev/ttyUSB0 ]; then
        PORT="/dev/ttyUSB0"
    elif [ -e /dev/ttyACM0 ]; then
        PORT="/dev/ttyACM0"
    fi

    if [ -n "$PORT" ]; then
        echo "[+] Tìm thấy cổng: $PORT"
        python read_gps.py -p "$PORT"
    else
        echo "[*] Quét tự động bằng Python..."
        python read_gps.py
    fi

elif [ "$choice" = "2" ]; then
    read -p "Nhập cổng Port (Mặc định 8888): " port_num
    port_num=${port_num:-8888}
    echo "[*] Đang kết nối tới Socket Bridge: socket://localhost:$port_num ..."
    python read_gps.py -p "socket://localhost:$port_num"

elif [ "$choice" = "3" ]; then
    echo "[*] Đang gỡ bỏ gói cũ và cài đặt lại pyserial chuẩn..."
    pip uninstall -y serial pyserial 2>/dev/null
    pip install pyserial
    echo "[+] Đã cài xong pyserial. Bạn hãy chạy lại script!"
else
    echo "Lựa chọn không hợp lệ."
fi

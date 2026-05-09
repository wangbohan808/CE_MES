import serial
import serial.tools.list_ports

from test_tool import test

port_list = []
baud_rate = 115200


def serial_open(ser, port, ser_timeout):
    # [WEIGH-106] dev==106 时走下方 9600 分支（与 101/104/105 一致）
    if ser.is_open:
        print("串口本身已经打开")
        return 0
    try:
        ser.port = port
        # [WEIGH-106] 106 与 101/104/105 相同：电子秤/仪表 9600 8N1
        if (test.load_cfg.dev == "101" or test.load_cfg.dev == "104"
                or test.load_cfg.dev == "105" or test.load_cfg.dev == "106"):
            ser.baudrate = 9600
        else:
            ser.baudrate = 115200
        ser.timeout = ser_timeout
        ser.open()  # 打开串口
        print(port, "open comm success", ser.is_open)
        if ser.is_open:
            return 0
        else:
            return 1
    except serial.SerialException as e:
        print(f"打开串口失败: {e}")
        return 255


def serial_close(ser):
    if ser.is_open:
        print("close " + str(ser.name))
        ser.close()


def get_serial_list():
    global port_list
    port_list = serial.tools.list_ports.comports()  # 行为
    for port in port_list:
        print("发现串口 ：" + str(port.name) + " id: " + str(port.pid))
    return port_list

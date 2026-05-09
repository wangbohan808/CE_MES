import time

from myserial import use_serial
from test_tool import test
import serial
import queue
from ui import MainFrame
import applog

# 创建测试串口
test_ser = serial.Serial()
test_rx_q = queue.Queue()
test_tx_q = queue.Queue()

# 串口ID优先选择列表（与 serial.tools.list_ports 中 port.pid 一致，为 USB PID 十进制）
com_id_list = [
    29987,    # CH340（0x7523）
    60000,    # CP210x（如 0xEA60）
    8963,     # [WEIGH-106] Prolific PL2303（硬件 ID USB\VID_067B&PID_2303，0x2303）
]


def test_serial_send(dat):
    log = None
    dis_str = "tx: "
    if MainFrame.main_frame.logger:
        log = MainFrame.main_frame.logger.get_logger()
    if test_tx_q.full() is not True:
        test_tx_q.put(dat)
        print("发送串口数据：", end=' ')
        for hex_dat in dat:
            dis_str += str(hex(hex_dat)) + " "
            print(str(hex(hex_dat)), end=' ')
        print("\n end")
        if log:
            log.info(dis_str)


def test_serial_receive():
    if test_rx_q.empty() is not True:
        return test_rx_q.get()
    else:
        return None


def test_serial_process():
    test_serial_rx_run()
    test_serial_tx_run()
    time.sleep(0.01)


def test_serial_tx_run():
    if test_tx_q.empty() is not True:
        dat = test_tx_q.get()
        print(dat)
        if dat is not None:
            try:
                test_ser.write(dat)  # 将字符串编码为字节并发送
                # print("send " + str(dat))
            except serial.SerialException as e:
                print(f"串口写入数据失败：{e}")
                use_serial.serial_close(test_ser)
            finally:
                # 关闭串口
                if "test_ser" in locals() and test_ser.is_open:
                    print("串口已关闭。")


def test_serial_rx_run():
    if test_ser.is_open:
        try:
            dat = test_ser.read()
            if dat != b'':
                dat = dat + test_ser.read(256)
                if test_rx_q.full() is not True:
                    test_rx_q.put(dat)
        except serial.SerialException as e:
            close_test_com()
            print(f"Serial connection error: {e}")
        except Exception as e:
            close_test_com()
            print(f"An unexpected error occurred: {e}")


def open_test_com():
    # [WEIGH-106] dev==106 时使用与耐压仪相同的 open 参数
    port_list = use_serial.get_serial_list()
    com = ""
    com_id = -1

    for port in port_list:
        if test.load_cfg.com != "":
            if port.name == test.load_cfg.com:
                com = port.name
                com_id = port.pid
                break
        else:
            com = port.name
            com_id = port.pid
            if com_id in com_id_list:  # 优先使用已知串口
                break
    print("name: "+str(com))
    print(("id: "+str(com_id)))
    ret = False
    if com != "":
        # [WEIGH-106] 106 与耐压仪相同：稍长 timeout 便于读行
        if (test.load_cfg.dev == "101" or test.load_cfg.dev == "104"
                or test.load_cfg.dev == "105" or test.load_cfg.dev == "106"):
            ret_value = use_serial.serial_open(test_ser, com, 0.05)
        else:
            ret_value = use_serial.serial_open(test_ser, com, 0.01)
        if ret_value == 0:
            ret = True
    return ret


def close_test_com():
    use_serial.serial_close(test_ser)


def get_test_com_open_state():
    if test_ser.is_open:
        return True
    else:
        return False









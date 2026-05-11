#  耐压测试
import time
import wx
from ui import MainFrame
from myserial import test_serial
from tool_box import tool
from test_tool import test
from test_tool import encode_rules
from mes import mes_run
from datetime import datetime
# 打高压测试主任务

test_cmd_data = (0x11, 0x08, 0x02, 0x00, 0x54)
reset_cmd_data = (0x11, 0x08, 0x02, 0x00, 0x52)
ret_status_dirt = {
    0: "耐压测试通过",
    1: "耐压测试终止",
    2: "耐压漏电过大",
    3: "耐压漏电过小",
    4: "耐压电弧失败",
    5: "耐压测试崩溃",
    6: "绝缘测试通过",
    7: "绝缘测试终止",
    8: "绝缘电阻过大",
    9: "绝缘电阻过小"
}

ret_test_type_dirt = {
    0: "耐压测试",
    1: "绝缘测试",
    2: "先耐压后绝缘测试",
    3: "先绝缘后耐压测试",
}

# 测试电流
test_res_cur = "0"


def test_process():
    global test_res_cur

    sn_list = test.get_sn_collect_res()
    # 等待SN输入
    if test.is_sn_up_enable():
        print("等待条码")
        return
    if len(sn_list) != 1:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, first="获取条码数量异常：", color=wx.RED)
        test.test_work_state = "idle"
        return
    sn = sn_list[0]
    encode_res = encode_rules.match_sn_encoding_rules(dev=test.load_cfg.dev, sn=sn)
    if encode_res is not True:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="SN编码异常 NG：" + sn, color=wx.RED)
        test.test_work_state = "idle"
        return

    res = mes_run.check_sn_is_ok(sn)

    if res is False:
        test.test_work_state = "idle"
        return
    print("k 开始测试")
    wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试", color=wx.RED)
    # 复位->启动测试->等待结果
    # 发送复位命令
    tool.clear_queue(test_serial.test_rx_q)

    send_dat = bytes(reset_cmd_data)
    print("发送复位命令")
    test_serial.test_serial_send(send_dat)
    time.sleep(0.5)
    print("发送测试命令")
    send_dat = bytes(test_cmd_data)
    test_serial.test_serial_send(send_dat)
    time.sleep(0.1)

    # 等待测试结果
    ret = tool.conditional_sleep(10, check_state_change_or_serial_rx_msg, 0.1)

    if ret is False:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试超时", color=wx.RED)
    elif check_state_change():
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试停止", color=wx.RED)
    elif check_serial_receive_msg():
        ret = withstand_data_handle()
        end_time = datetime.now()
        if ret == "OK":
            mes_run.add_report(name="打高压测试", result="OK",
                               value=test_res_cur, val_max="5mA", val_min="0mA")
            send_res = mes_run.send_report(test.test_start_time, end_time, sn, "OK")
            if send_res is True:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="打高压测试 PASS", color=wx.GREEN)
        else:
            mes_run.add_report(name="打高压测试", result="NG",
                               value=test_res_cur, val_max="5mA", val_min="0mA")
            send_res = mes_run.send_report(test.test_start_time, end_time, sn, "NG")
            if send_res is True:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="打高压测试 NG",
                             third=ret, color=wx.RED)

    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试异常", color=wx.RED)

    test.test_work_state = "idle"


# 治具类型，ZCtek  型号： ZC7122D 交直流耐电压/绝缘测试仪
def test_mode_zc7122d_process():
    global test_res_cur
    log = None
    if MainFrame.main_frame.logger:
        log = MainFrame.main_frame.logger.get_logger()

    sn_list = test.get_sn_collect_res()
    # 等待SN输入
    if test.is_sn_up_enable():
        print("等待条码")
        return
    if len(sn_list) != 1:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, first="获取条码数量异常：", color=wx.RED)
        test.test_work_state = "idle"
        return
    sn = sn_list[0]
    encode_res = encode_rules.match_sn_encoding_rules(dev=test.load_cfg.dev, sn=sn)
    if encode_res is not True:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, sencod="SN编码异常 NG：" + sn, color=wx.RED)
        test.test_work_state = "idle"
        return

    res = mes_run.check_sn_is_ok(sn)

    if res is False:
        test.test_work_state = "idle"
        return
    print("k 开始测试")
    wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试", color=wx.RED)

    # 检查电压上下限 3000V -> 读取频率上下限 49.5-50.5 -> 启动测试 -> 读取电流上下限 -> 读取测试结果 -> 停止测试
    # 发送复位命令
    tool.clear_queue(test_serial.test_rx_q)
    # 停止测试
    cmd_data = "STOP\r\n"
    if log:
        log.info("send: " + cmd_data)
    send_bytes_data = cmd_data.encode()  # 默认编码为UTF-8, 兼容 'ascii'
    test_serial.test_serial_send(send_bytes_data)
    time.sleep(0.1)
    get_str_from_ser()

    # 读取电压上下限 3000V
    cmd_data = ":SOUR:SAFE:STEP 1:AC:LEV?\r\n"
    if log:
        log.info("send: " + cmd_data)
    send_bytes_data = cmd_data.encode()  # 默认编码为UTF-8, 兼容 'ascii'
    # print("发送测试命令", cmd_data)
    test_serial.test_serial_send(send_bytes_data)
    tool.conditional_sleep(1, check_state_change_or_serial_rx_msg, 0.1)
    ret_str = get_str_from_ser()
    if log:
        log.info("rx: " + ret_str)
    value_vol = int(ret_str.strip())  # 3000
    # 读取频率上下限 49.5 - 50.5
    cmd_data = ":SOUR:SAFE:STEP 1:AC:TIME:FREQ?\r\n"
    if log:
        log.info("send: " + cmd_data)
    send_bytes_data = cmd_data.encode()  # 默认编码为UTF-8, 兼容 'ascii'
    test_serial.test_serial_send(send_bytes_data)
    tool.conditional_sleep(1, check_state_change_or_serial_rx_msg, 0.1)
    ret_str = get_str_from_ser()
    if log:
        log.info("rx: " + ret_str)
    value_hz = float(ret_str.strip())  # 50
    if value_vol != 3000 or value_hz < 49.5 or value_hz > 50.5:
        dis_str = f"参数或通讯异常，电压：{value_vol} ，频率：{value_hz}"
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, sencod=dis_str + sn, color=wx.RED)
        test.test_work_state = "idle"
        return
    # 启动测试 START\r\n
    cmd_data = "START\r\n"
    if log:
        log.info("send: " + cmd_data)
    send_bytes_data = cmd_data.encode()  # 默认编码为UTF-8, 兼容 'ascii'
    test_serial.test_serial_send(send_bytes_data)
    # tool.conditional_sleep(4, check_state_change_or_serial_rx_msg, 0.1)
    time.sleep(4)
    ret_str = get_str_from_ser()
    if log:
        log.info("rx: " + ret_str)

    # 读取电流上下限 0.1 - 5
    cmd_data = ":TEST:FETCH?\r\n"
    if log:
        log.info("send: " + cmd_data)
    send_bytes_data = cmd_data.encode()  # 默认编码为UTF-8, 兼容 'ascii'
    test_serial.test_serial_send(send_bytes_data)
    tool.conditional_sleep(1, check_state_change_or_serial_rx_msg, 0.1)
    ret_str = get_str_from_ser()
    if log:
        log.info("rx: " + ret_str)

    result_str = ret_str.strip()
    parts = result_str.split(",")
    end_time = datetime.now()
    if len(parts) >= 4:
        if log:
            log.info(f"parts:{parts}")
        str_vol = parts[0].strip()
        str_type = parts[1].strip()
        str_i = parts[2].strip()
        str_i_num = float(str_i.replace("mA", "").strip())
        str_res = int(parts[3].strip())
        if log:
            log.info(f"电压：{str_vol}，类型：{str_type}，电流：{str_i}，电流值：{str_i_num}，结果：{str_res}")
        if str_vol == "3.000kV" and str_type == "AC" and 0.1 <= str_i_num <= 5.0 and str_res == 1:
            ret = "OK"
        else:
            ret = "NG"
        if ret == "OK":
            test_res_cur = result_str
            mes_run.add_report(name="打高压测试", result="OK",
                               value=test_res_cur, val_max="5mA", val_min="0.1mA")
            send_res = mes_run.send_report(test.test_start_time, end_time, sn, "OK")
            if send_res is True:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="打高压测试 PASS", color=wx.GREEN)
        else:
            test_res_cur = result_str
            mes_run.add_report(name="打高压测试", result="NG",
                               value=test_res_cur, val_max="5mA", val_min="0.1mA")
            send_res = mes_run.send_report(test.test_start_time, end_time, sn, "NG")
            if send_res is True:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="打高压测试 NG",
                             third=ret, color=wx.RED)
    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试结果通讯异常", color=wx.RED)

    test.test_work_state = "idle"




# 治具类型，ZCtek  型号： ZC7122D 交直流耐电压/绝缘测试仪
def test_mode_new_zc7122d_process():
    global test_res_cur
    log = None
    if MainFrame.main_frame.logger:
        log = MainFrame.main_frame.logger.get_logger()

    sn_list = test.get_sn_collect_res()
    # 等待SN输入
    if test.is_sn_up_enable():
        print("等待条码")
        return
    if len(sn_list) != 1:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, first="获取条码数量异常：", color=wx.RED)
        test.test_work_state = "idle"
        return
    sn = sn_list[0]
    encode_res = encode_rules.match_sn_encoding_rules(dev=test.load_cfg.dev, sn=sn)
    if encode_res is not True:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, sencod="SN编码异常 NG：" + sn, color=wx.RED)
        test.test_work_state = "idle"
        return

    res = mes_run.check_sn_is_ok(sn)

    if res is False:
        test.test_work_state = "idle"
        return
    print("k 开始测试")
    wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试", color=wx.RED)

    # 检查电压上下限 3000V -> 读取频率上下限 49.5-50.5 -> 启动测试 -> 读取电流上下限 -> 读取测试结果 -> 停止测试
    # 发送复位命令
    tool.clear_queue(test_serial.test_rx_q)
    # 启动测试 START\r\n
    cmd_data = "START\r\n"
    if log:
        log.info("send: " + cmd_data)
    send_bytes_data = cmd_data.encode()  # 默认编码为UTF-8, 兼容 'ascii'
    test_serial.test_serial_send(send_bytes_data)
    # tool.conditional_sleep(4, check_state_change_or_serial_rx_msg, 0.1)
    time.sleep(5.5)
    ret_str = get_str_from_ser()
    if log:
        log.info("rx: " + ret_str)

    # 读取电流上下限 0.1 - 5
    cmd_data = ":TEST:FETCH?\r\n"
    if log:
        log.info("send: " + cmd_data)
    send_bytes_data = cmd_data.encode()  # 默认编码为UTF-8, 兼容 'ascii'
    test_serial.test_serial_send(send_bytes_data)
    tool.conditional_sleep(1, check_state_change_or_serial_rx_msg, 0.1)
    ret_str = get_str_from_ser()
    if log:
        log.info("rx: " + ret_str)

    result_str = ret_str.strip()
    parts = result_str.split(",")
    end_time = datetime.now()
    if len(parts) >= 4:
        if log:
            log.info(f"parts:{parts}")
        str_vol = parts[0].strip()
        str_type = parts[1].strip()
        str_i = parts[2].strip()
        str_i_num = float(str_i.replace("mA", "").strip())
        str_res = int(parts[3].strip())
        if log:
            log.info(f"电压：{str_vol}，类型：{str_type}，电流：{str_i}，电流值：{str_i_num}，结果：{str_res}")
        if str_vol == "3.640kV" and str_type == "AC" and 0.05 <= str_i_num <= 5.0 and str_res == 1:
            ret = "OK"
        else:
            ret = "NG"
        if ret == "OK":
            test_res_cur = result_str
            mes_run.add_report(name="打高压测试", result="OK",
                               value=test_res_cur, val_max="5mA", val_min="0.1mA")
            send_res = mes_run.send_report(test.test_start_time, end_time, sn, "OK")
            if send_res is True:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="打高压测试 PASS", color=wx.GREEN)
        else:
            test_res_cur = result_str
            mes_run.add_report(name="打高压测试", result="NG",
                               value=test_res_cur, val_max="5mA", val_min="0.1mA")
            send_res = mes_run.send_report(test.test_start_time, end_time, sn, "NG")
            if send_res is True:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="打高压测试 NG",
                             third=ret, color=wx.RED)
    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试结果通讯异常", color=wx.RED)

    test.test_work_state = "idle"
    test.clear_sn_save_list()





def check_state_change(cur_state="running"):
    return cur_state != test.test_work_state


def check_state_change_or_barcode_change(cur_state="running"):
    if cur_state != test.test_work_state or test.barcode_q.empty() is not True:
        return True
    else:
        return False


def check_state_change_or_serial_rx_msg(cur_state="running"):
    if cur_state != test.test_work_state:
        return True
    if test_serial.test_rx_q.empty() is not True:
        return True
    return False


def check_serial_receive_msg():
    return test_serial.test_rx_q.empty() is not True


def get_str_from_ser():
    if test_serial.test_rx_q.empty() is True:
        print("get_str_from_ser 数据为空")
        return ""
    decoded_string = ""
    while test_serial.test_rx_q.empty() is not True:
        byte_data = test_serial.test_rx_q.get()
        # 字节序列转字符串
        decoded_string += byte_data.decode('utf-8')  # 指定编码格式
    return decoded_string


# 检测数据，提取有效信息
def withstand_data_handle():
    global test_res_cur

    if test_serial.test_rx_q.empty() is True:
        print("withstand_data_handle 数据为空")
        return "未收到治具测试结果"

    mes_run.clear_report()
    data = test_serial.test_rx_q.get()
    if len(data) == 12 and data[0] == 0x5A and data[1] == 0x59:
        status = data[2]
        display_str = ret_status_dirt.get(int(status), "耐压测试，未知返回")
        test_type = tool.extract_bits(data[3], 7, 8)
        if tool.check_bit(data[3], 5):
            ac_dc = "AC"
        else:
            ac_dc = "DC"

        vol = int(data[4]) * 256 + int(data[5])
        vol *= 10
        bytes_data = bytes((data[9], data[8], data[7], data[6]))
        cur = tool.bytes_to_float(bytes_data)
        s_cur = format(cur/100, ".3f") + "mA"
        print(s_cur)
        test_res_cur = s_cur
        print("打高压测试，" + display_str + ":" + ac_dc + "，电压：" + str(vol)+"V", "，电流：" + s_cur)
        display_str = "打高压测试，" + display_str + ":" + ac_dc + "，电压：" + str(vol)+"V", "，电流：" + s_cur
        if status == 0x00:  # 测试通过
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="打高压测试 PASS", color=wx.GREEN)
            return "OK"
        else:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second=display_str, color=wx.RED)
            return display_str
    else:
        print("打高压治具 收到无效数据")
        return "打高压治具，收到无效数据"



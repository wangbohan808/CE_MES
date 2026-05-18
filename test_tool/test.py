import time
import yaml
import re
from datetime import datetime

from myserial import test_serial
import wx
from ui import MainFrame
from test_tool import withstand_vol
from dataclasses import dataclass
from mes import mes_run
import queue
from tool_box import tool
from test_tool import bind_robot
from test_tool import excel
from test_tool import encode_rules
from mes import anker_mes
from database import sqlite_db
from test_tool import voice
from test_tool import sn_check
from test_tool import weigh_station  # [WEIGH-106] 称重工位 106
import applog


test_work_state = "init"
barcode_msg_update = False
test_ser_connect = False
error_display_str = ""
test_error_str = ""

# 定义使用双地检模式使能
TWO_CLIFF_SENSOR_MODE_EN = True


barcode_q = queue.Queue()  # 扫码枪数据
rx_sn_cmd_q = queue.Queue()  # 收到SN信息，模拟治具给治具处理模块发一条命令（dev < 100）
check_sn_enable = False  # 检测SN，当使用mes系统时，需要过站检测
check_sn_str = ""  # 保存过站码用于，上传记录

cliff_sn_dict = {
    "left": "",
    "right": ""
}

# 列表用于存储，主界面接收到的SN号
sn_save_list = []
# 更新 sn 使能开关
sn_up_enable = False

test_start_time = datetime.now()
test_end_time = datetime.now()


@dataclass
class LoadCfg:
    dev: str = "001"     # 测试类型编码
    com: str = ""        # 串口端口 如：'COM1'
    mes: str = "3"       # 是否使用mes
    mcu_ver: str = ""    # 集尘桶或集尘桶PCB软件版本
    test_tool: str = ""  # 治具名称或编码
    parts_sn_head: str = ""  # 103 配件纸盒条码头，前7位
    project_name: str = ""   # 项目代号
    # --- WEIGH-106-BEGIN: 称重工位 106 配置（见 WEIGH_STATION_106_SPEC.md）---
    weight_min_kg: float = 100.0
    weight_max_kg: float = 150.0
    weight_read_delay_sec: float = 1.0
    weight_read_timeout_sec: float = 2.0
    weigh_scheme: str = "1"  # "1" 固定限；"2" 前 weigh_pass_first_n 台直通后 μ±σ
    weigh_pass_first_n: int = 5
    # 方案二历史重量 JSON；相对路径相对 exe 目录（frozen）或当前工作目录
    weigh_history_json_path: str = "weigh_106_history.json"
    # --- WEIGH-106-END ---
    # #[RV30-PROTO] 基站 device_type=50 实时判据（config.yaml，与 doc/ce_mes_iteration/RV30_BASESTATION_PROTOCOL_AND_IMPLEMENTATION_SPEC.md 一致）
    rv30_charge_Hmin: int = 0
    rv30_charge_Hmax: int = 0
    rv30_charge_Lmin: int = 0
    rv30_charge_Lmax: int = 0
    rv30_suction_10pa_Hmin: int = 0
    rv30_suction_10pa_Hmax: int = 0
    rv30_suction_10pa_Lmin: int = 0
    rv30_suction_10pa_Lmax: int = 0
    rv30_freq_min: int = 0
    rv30_freq_max: int = 0
    rv30_ir_l: int = 0
    rv30_ir_lc: int = 0
    rv30_ir_rc: int = 0
    rv30_ir_r: int = 0
    rv30_dust_bag_expected: int = 0
    rv30_led_expected: int = 0


@dataclass
class DustThreshold:
    # 交流充电阈值
    cc_max: int = 0
    cc_min: int = 0
    # 阈值 ac 过载频率
    ac_lv_max: int = 0
    ac_lv_min: int = 0
    # 阈值 外接气压计 上线下线；吸力值，暂时未使用
    out_barometer_max: int = 0
    out_barometer_min: int = 0
    # 阈值 气压值小板 上线下线；检测尘满
    barometer_max: int = 0
    barometer_min: int = 0


dust_th = DustThreshold()
load_cfg = LoadCfg()

# #[RV30-PROTO] RV30 基站(device_type=50) 会话状态机常量（调优时只改 RV30_finished_product_mode 与下列变量）
RV30_SESS_IDLE = 0
RV30_SESS_WAIT_SN = 1
RV30_SESS_RUNNING = 2
RV30_SESS_FINISHED = 3
RV30_SESS_ABORTED = 4
rv30_session_state = RV30_SESS_IDLE
rv30_last_step = -1
rv30_max_step = 0  # [RV30-步骤4终判-WBH] 本轮实时数据到达过的最大治具步骤
rv30_89_mes_done = False
rv30_realtime_ng = False
rv30_last_p = None  # [up_test_ui_WBH] 最近一帧 0x77 解析结果，供结束帧刷新测试格
rv30_last_dust_notify = -1  # [RV30-尘袋步骤3-WBH] 防抖：上次已提示的 dust 状态
# #[RV30-PROTO-68-MOD] 0x68 数据区字节数（回充4+版本4+频率1+尘袋1+充电4+LED1+集尘4）；PNG 若版本为 3 字节则改为 18 并改 parse 下标
RV30_68_DATA_LEN = 19


def _rv30_u16_be(hi, lo):
    # #[RV30-PROTO-68-MOD] 协议 HH/LL 大端 16 位
    return (int(hi) & 0xFF) << 8 | (int(lo) & 0xFF)


# import sys
# import os

# def resource_path(relative_path):
#     """获取资源文件的绝对路径，兼容开发和打包"""
#     try:
#         # PyInstaller 创建的临时目录
#         base_path = sys._MEIPASS
#     except AttributeError:
#         base_path = os.path.abspath(".")
#     return os.path.join(base_path, relative_path)


import sys
import os

def resource_path(relative_path):
    """获取资源的绝对路径，兼容开发环境和 PyInstaller 打包后的环境"""
    if getattr(sys, 'frozen', False):
        # 打包后，资源文件被解压到 sys._MEIPASS 目录
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def test_run_process():
    # [WEIGH-106] running 态：elif int(load_cfg.dev)==106 -> weigh_station.process()
    global test_work_state
    global barcode_msg_update

    # 检测并更新串口显示
    check_ser_connect_and_up_ui()
    if error_handle():
        return
    # 对测试任务进行监控，比如开始结束等等
    check_process_run_state()
    # 串口数据处理
    if int(load_cfg.dev) < 100:  # 海能主板测试工具 dev 小于100
        barcode_check_process()
        test_serial_rx_data_handle()
    if test_work_state == "running":
        if int(load_cfg.dev) == 101:  # 打高压测试（耐压测试）
            withstand_vol.test_process()
        elif int(load_cfg.dev) == 100:  # 绑定前撞、电池、主机
            bind_robot.bind_sn_process()
            barcode_msg_update = False  # 清二维码更新标志，防止直接进入
        elif int(load_cfg.dev) == 102:  # 比较条码是否相同
            check_barcodes_match_process()
        elif int(load_cfg.dev) == 103:  # 配件纸盒SN检查工具
            sn_check.check_barcodes_of_parts_box_process()
        elif int(load_cfg.dev) == 104:  # 打高压测试，另外一款
            withstand_vol.test_mode_zc7122d_process()
        elif int(load_cfg.dev) == 105:
            withstand_vol.test_mode_new_zc7122d_process()
        elif int(load_cfg.dev) == 106:  # [WEIGH-106] 称重工位
            weigh_station.process()
    elif test_work_state == "idle":
        test_idle_work()
    elif test_work_state == "init":
        load_config()
        test_init_work()
        test_work_state = "idle"
    elif test_work_state == "stop":
        pass
    time.sleep(0.01)


def error_handle():
    # 如果基站配置异常不执行测试
    if anker_mes.is_station_cfg_error():
        wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                     second="工站配置异常，请配置正确，并重启测试软件", color=wx.RED)
        time.sleep(1)
        return True
    elif sqlite_db.db_error_state != "":
        wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                     second="数据库异常：" + str(sqlite_db.db_error_state), color=wx.RED)
        time.sleep(1)
        return True
    elif test_error_str != "":
        time.sleep(1)
        return True

    return False


def test_init_work():
    # [WEIGH-106] 106 分支：称重工位 idle 文案（见 elif dev==106）
    global test_work_state

    if int(load_cfg.dev) == 102 or int(load_cfg.dev) == 103:  # 条码比较, 配件纸箱条码检测工具
        if int(load_cfg.dev) == 102:
            voice.play_voice_init()
            sq_res = sqlite_db.open_sn_database("robot_sn")
            if sq_res[0] is False:
                voice.play_voice("db_error")

        else:  # 103
            voice.play_voice_init()
            sq_res = sqlite_db.open_sn_database("parts_sn")

        if sq_res[0]:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫条码", color=wx.RED)
        else:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="数据库打开异常，请检测后重启软件", color=wx.RED)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second=str(sq_res[1]), color=wx.RED)
            test_work_state = "stop"
            sqlite_db.db_error_state = str(sq_res[1])
        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item_size, num=3, size=42)
    elif int(load_cfg.dev) == 106:  # [WEIGH-106] 称重工位 idle 提示
        wlo = load_cfg.weight_min_kg
        whi = load_cfg.weight_max_kg
        if str(getattr(load_cfg, "weigh_scheme", "1")).strip() == "2":
            rng = (
                "方案二：前 {} 台直通；之后合格判据为 μ±σ（总体标准差）；"
                "直通段 MES 上下限仍为 {:.1f} ~ {:.1f} kg；历史文件 {}（config.yaml：weigh_history_json_path）。"
            ).format(
                int(getattr(load_cfg, "weigh_pass_first_n", 5)),
                wlo,
                whi,
                str(getattr(load_cfg, "weigh_history_json_path", "weigh_106_history.json")),
            )
        else:
            rng = "方案一：当前合格区间 {:.1f} ~ {:.1f} kg。".format(wlo, whi)
        wx.CallAfter(
            MainFrame.main_frame.up_notification_ui,
            first="称重工位：货物先放稳再上秤，再扫 SN。",
            second=rng,
            color=wx.RED,
        )
    elif int(load_cfg.dev) >= 100:  # 绑定主机、SN
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫主机条码开始测试", color=wx.RED)
    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请启动治具开始测试", color=wx.RED)

    if int(load_cfg.dev) == 100 or int(load_cfg.dev) == 102 or int(load_cfg.dev) == 103:
        wx.CallAfter(MainFrame.main_frame.up_open_ser_button_text, "启动/复位")


def test_idle_work():
    global test_work_state


def barcode_check_process():
    global check_sn_enable
    global check_sn_str
    global rv30_session_state
    global rv30_last_step
    global rv30_max_step
    global rv30_89_mes_done
    global rv30_realtime_ng

    if check_sn_enable and (barcode_q.empty() is not True):
        sn = barcode_q.get()
        str_list = [int(byte) for byte in sn.encode('utf-8')]
        if int(load_cfg.dev) == 5:  # 地检
            return
        elif int(load_cfg.dev) == 50:  # #[RV30-PROTO] 基站050：门闸失败先发 0x58 再发 0x89 0x03 并立即 MES NG，不等 0x88
            print("check sn: " + sn)
            encode_res = encode_rules.match_sn_encoding_rules(dev=load_cfg.dev, sn=str(sn))
            _txd = rv30_proto_tx_dev_byte()
            if encode_res is not True:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                             second="SN码异常，请检测：" + str(sn),
                             color=wx.RED)
                ser_send_data(dev=_txd, cmd=0x58, data=str_list)
                ser_send_data(dev=_txd, cmd=0x89, data=[0x03])
                check_sn_str = sn
                # rv30_proto_abort_mes_after_gate_fail()     # 这一步失败不需要上报
                check_sn_enable = False
                return
            res = mes_run.check_sn_is_ok(sn)
            check_sn_str = sn
            if res:
                ser_send_data(dev=_txd, cmd=0x57, data=str_list)
                rv30_session_state = RV30_SESS_RUNNING
                rv30_last_step = -1
                rv30_max_step = 0
                rv30_89_mes_done = False
                rv30_realtime_ng = False
            else:
                ser_send_data(dev=_txd, cmd=0x58, data=str_list)
                ser_send_data(dev=_txd, cmd=0x89, data=[0x03])
                # rv30_proto_abort_mes_after_gate_fail()
            check_sn_enable = False
            return
        elif 0 < int(load_cfg.dev) < 100:

            print("check sn: " + sn)
            encode_res = encode_rules.match_sn_encoding_rules(dev=load_cfg.dev, sn=str(sn))
            if encode_res is not True:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                             second="SN码异常，请检测：" + str(sn),
                             color=wx.RED)
                ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
                # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具扫码失败
                check_sn_enable = False
                return

        res = mes_run.check_sn_is_ok(sn)

        check_sn_str = sn
        if int(load_cfg.dev) < 100 and int(load_cfg.dev) != 5:  # 只处理夹具
            if res:
                ser_send_data(dev=int(load_cfg.dev), cmd=0x57, data=str_list)
                # ser_send_cmd(int(load_cfg.dev), 0x57)  # 回复夹具开始测试
            else:
                ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
                # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具开始测试

        check_sn_enable = False


def check_process_run_state():
    # [WEIGH-106] idle 下 dev==106 与 101 等同：barcode_msg_update 进入 running + start_sn_collect
    global test_work_state
    global barcode_msg_update
    global check_sn_str
    global test_start_time

    # 如果测试状态是空闲，打高压或绑码，扫码触发测试，
    # 如果是海能治具，由下位命令机触发
    if test_work_state == "idle":
        dev = int(load_cfg.dev)
        # [WEIGH-106] 106 与 101 等相同：扫码进入 running
        if dev == 100 or dev == 101 or dev == 102 or dev == 103 or dev == 104 or dev == 105 or dev == 106:
            if barcode_msg_update:  # 如果扫码枪收到条码，则进入运行状态
                test_start_time = datetime.now()
                test_work_state = "running"
                barcode_msg_update = False
                if barcode_q.qsize() == 1:
                    sn = barcode_q.get()
                else:
                    tool.clear_queue(barcode_q)
                    sn = ""
                if int(load_cfg.dev) == 100:
                    start_sn_collect(first="请扫主机条码：", second="请扫电池条码：",
                                     third="请扫前撞条码：", start_sn=sn)
                elif dev == 101 or dev == 104 or dev == 105:
                    start_sn_collect(first="请扫集尘桶条码：", start_sn=sn)
                    print("请扫集尘桶条码")
                elif dev == 106:  # [WEIGH-106] 单次扫码
                    start_sn_collect(first="请扫产品 SN：", start_sn=sn)
                elif int(load_cfg.dev) == 102:
                    start_sn_collect(first="请输入条码一：", second="请输入条码二：", start_sn=sn)
                elif int(load_cfg.dev) == 103:
                    start_sn_collect(first="请输入条码：", start_sn=sn)


# 串口打开、扫码枪收到,一帧数据,下位机发送开始测试命令


def read_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    return config



def get_config_path():
    """获取 config.yaml 的绝对路径（exe 同级目录或开发环境项目根目录）"""
    if getattr(sys, 'frozen', False):
        # 打包后，sys.executable 是 exe 的完整路径
        base_dir = os.path.dirname(sys.executable)
    else:
        # 开发环境，取当前工作目录（通常为项目根目录）
        base_dir = os.path.abspath(".")
    return os.path.join(base_dir, "config.yaml")

# 加载配置文件
def load_config():
    # [WEIGH-106] 读取 weight_min_kg / weight_max_kg / weight_read_*（见文件内 YAML 赋值处）
    # 读配置文件

    config_path = get_config_path()
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在：{config_path}")
    config = read_yaml(config_path)

    # # yaml_file_path = 'config.yaml'
    # # 读取并打印YAML文件内容
    # yaml_file_path = resource_path('config.yaml')   # 使用 resource_path
    # config = read_yaml(yaml_file_path)
    print(type(config), config)
    load_cfg.com = config.get('user_com', "")  # config['user_com']
    load_cfg.dev = config['device_type']
    load_cfg.mcu_ver = config.get('mcu_version', "")  # config['mcu_version']
    load_cfg.test_tool = config.get('test_tool', "治具未编码")  # 测试工具编码，暂不使用（海能mes）
    load_cfg.mes = config.get('use_mes', "3")  # 使用安克mes
    load_cfg.parts_sn_head = config.get('parts_sn_head', "")  # config['parts_sn_head']
    load_cfg.project_name = config.get('project_name', "C10B ")
    print(load_cfg.parts_sn_head)
    # [WEIGH-106] 称重上下限与读数时序（config.yaml 可选）
    load_cfg.weight_min_kg = float(config.get("weight_min_kg", load_cfg.weight_min_kg))
    load_cfg.weight_max_kg = float(config.get("weight_max_kg", load_cfg.weight_max_kg))
    load_cfg.weight_read_delay_sec = float(
        config.get("weight_read_delay_sec", load_cfg.weight_read_delay_sec))
    load_cfg.weight_read_timeout_sec = float(
        config.get("weight_read_timeout_sec", load_cfg.weight_read_timeout_sec))
    load_cfg.weigh_scheme = str(
        config.get("weigh_scheme", getattr(load_cfg, "weigh_scheme", "1"))
    ).strip() or "1"
    load_cfg.weigh_pass_first_n = int(
        config.get("weigh_pass_first_n", getattr(load_cfg, "weigh_pass_first_n", 5))
    )
    if load_cfg.weigh_pass_first_n < 3:
        load_cfg.weigh_pass_first_n = 3
    _whp = str(
        config.get(
            "weigh_history_json_path",
            getattr(load_cfg, "weigh_history_json_path", "weigh_106_history.json"),
        )
    ).strip()
    load_cfg.weigh_history_json_path = _whp or "weigh_106_history.json"

    # #[RV30-PROTO] 从 config.yaml 读取 RV30 判据（缺省 0 表示不启用该项比较）

    load_cfg.rv30_charge_Hmin = int(config.get("rv30_charge_Hmin", getattr(load_cfg, "rv30_charge_Hmin", 0)))
    load_cfg.rv30_charge_Hmax = int(config.get("rv30_charge_Hmax", getattr(load_cfg, "rv30_charge_Hmax", 0)))
    load_cfg.rv30_charge_Lmin = int(config.get("rv30_charge_Lmin", getattr(load_cfg, "rv30_charge_Lmin", 0)))
    load_cfg.rv30_charge_Lmax = int(config.get("rv30_charge_Lmax", getattr(load_cfg, "rv30_charge_Lmax", 0)))
    load_cfg.rv30_suction_10pa_Hmin = int(
        config.get("rv30_suction_10pa_Hmin", getattr(load_cfg, "rv30_suction_10pa_Hmin", 0)))
    load_cfg.rv30_suction_10pa_Hmax = int(
        config.get("rv30_suction_10pa_Hmax", getattr(load_cfg, "rv30_suction_10pa_Hmax", 0)))
    load_cfg.rv30_suction_10pa_Lmin = int(
        config.get("rv30_suction_10pa_Lmin", getattr(load_cfg, "rv30_suction_10pa_Lmin", 0)))
    load_cfg.rv30_suction_10pa_Lmax = int(
        config.get("rv30_suction_10pa_Lmax", getattr(load_cfg, "rv30_suction_10pa_Lmax", 0)))

    load_cfg.rv30_freq_min = int(config.get("rv30_freq_min", getattr(load_cfg, "rv30_freq_min", 0)))
    load_cfg.rv30_freq_max = int(config.get("rv30_freq_max", getattr(load_cfg, "rv30_freq_max", 0)))
    load_cfg.rv30_ir_l = int(config.get("rv30_ir_l", getattr(load_cfg, "rv30_ir_l", 0)))
    load_cfg.rv30_ir_lc = int(config.get("rv30_ir_lc", getattr(load_cfg, "rv30_ir_lc", 0)))
    load_cfg.rv30_ir_rc = int(config.get("rv30_ir_rc", getattr(load_cfg, "rv30_ir_rc", 0)))
    load_cfg.rv30_ir_r = int(config.get("rv30_ir_r", getattr(load_cfg, "rv30_ir_r", 0)))
    load_cfg.rv30_dust_bag_expected = int(
        config.get("rv30_dust_bag_expected", getattr(load_cfg, "rv30_dust_bag_expected", 0)))
    load_cfg.rv30_led_expected = int(
        config.get("rv30_led_expected", getattr(load_cfg, "rv30_led_expected", 0)))

    if is_com_port(load_cfg.com) is False:
        print("配置串口端口非法：" + load_cfg.com)
        load_cfg.com = ""
    else:
        print("配置串口端口为：" + load_cfg.com)

    if int(load_cfg.mes) < 1 or int(load_cfg.mes) > 3:
        print("mes配置异常：" + str(load_cfg.mes))
        load_cfg.mes = str(load_cfg.mes)
    else:
        load_cfg.mes = '002'


def is_com_port(port_name):
    # 定义正则表达式：COM 后跟 1 个或多个数字
    pattern = r"^COM\d+$"
    return re.match(pattern, port_name) is not None


def is_no_use_ser_dev(dev=0):
    if int(dev) == 100 or int(dev) == 102:
        return True
    else:
        return False


def check_ser_connect_and_up_ui():
    global test_ser_connect
    state_change = False

    # 没使用串口设备
    if is_no_use_ser_dev(int(load_cfg.dev)):
        return
    if test_ser_connect:
        if test_serial.test_ser.is_open is not True:
            state_change = True
            test_ser_connect = False
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="串口断开连接", color=wx.RED)
    else:
        if test_serial.test_ser.is_open is True:
            state_change = True
            test_ser_connect = True
            if int(load_cfg.dev) >= 100:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码，启动测试", color=wx.RED)
            else:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请启动治具开始测试", color=wx.RED)
    if state_change:
        wx.CallAfter(MainFrame.main_frame.up_connect_ui, "com_connect", test_ser_connect)
        if test_ser_connect:
            wx.CallAfter(MainFrame.main_frame.up_open_ser_button_text, "关闭串口")
        else:
            wx.CallAfter(MainFrame.main_frame.up_open_ser_button_text, "打开串口")


def test_serial_rx_data_handle():
    if test_serial.test_rx_q.empty() is not True:
        dat = test_serial.test_rx_q.get()
        log = None
        dis_str = "rx: "
        if MainFrame.main_frame.logger:
            log = MainFrame.main_frame.logger.get_logger()
        for hex_dat in dat:
            # print(hex_dat)
            dis_str += str(hex(hex_dat)) + " "
            test_rx_data_handle(hex_dat)
        if log:
            log.info(dis_str)
    # 模拟串口命令，方便所有逻辑都在一个函数里执行
    elif rx_sn_cmd_q.empty() is not True:
        sn_cmd = rx_sn_cmd_q.get()
        dev = load_cfg.dev
        cmd = sn_cmd.get("cmd", "")
        data = sn_cmd.get("msg", "")
        test_cmd_handle(dev, cmd, data)


pack_data_len = 0
check_dev = 0
check_cmd = 0
check_sum = 0
pack_data = []
check_data = []


# 检测数据合法性，并提取，设备、命令、数据，三个字段
def test_rx_data_handle(hex_dat):
    global pack_data
    global pack_data_len
    global check_dev
    global check_cmd
    global check_data
    global check_sum

    pack_data.append(hex_dat)

    if len(pack_data) == 1:
        if hex_dat == 0xA5:  # 帧头 A
            pack_data_len = 0
            check_dev = 0
            check_cmd = 0
            check_sum = 0
            check_data = []
        else:
            pack_data = []
    elif len(pack_data) == 2:  # 帧头 B
        if hex_dat == 0x5A:
            check_sum = 0
        else:
            pack_data = []
    elif len(pack_data) == 3:  # 数据长度
        pack_data_len = hex_dat
        check_sum += hex_dat
    elif len(pack_data) == 4:  # 设备类型
        check_dev = hex_dat
        check_sum += hex_dat
    elif len(pack_data) == 5:  # 命令字
        check_cmd = hex_dat
        check_sum += hex_dat
        check_data = []
    elif (len(pack_data) > 5) and (len(pack_data) <= pack_data_len + 3):
        check_data.append(hex_dat)
        check_sum += hex_dat
    elif len(pack_data) >= pack_data_len + 3:
        if check_sum % 256 == hex_dat:
            print("读取到一帧数据: ", end='')
            print(str(check_data))
            for d in pack_data:
                print(str(hex(d)), end=' ')
            print("")
            test_cmd_handle(check_dev, check_cmd, check_data)
            pack_data = []
        else:
            print("check sum error", hex(check_sum % 256), hex(hex_dat))
            print(hex(pack_data_len), hex(check_dev), hex(check_cmd))
            pack_data = []


def check_cfg_dev(dev):
    global error_display_str

    if int(load_cfg.dev) != int(dev):
        print("配置设备类型：" + str(int(load_cfg.dev)) + " 上传的设备类型：" + str(int(dev)))
        error_display_str = "设备类型不匹配"


def test_cmd_handle(dev, cmd, dat):
    if len(dat) < 1:
        print("设备数据异常")
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具数据异常",
                     color=wx.RED)
        return
    # #[RV30-PROTO] device_type=050 时治具常发设备字节 0x50(十进制80)，与 YAML 中 50 对齐
    _dev_match = int(load_cfg.dev) == int(dev)
    if int(load_cfg.dev) == 50 and int(dev) == 0x50:
        _dev_match = True
    if not _dev_match:
        print("配置设备类型：" + str(int(load_cfg.dev)) + " 上传的设备类型：" + str(int(dev)))
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具类型不匹配", color=wx.RED)
    else:
        if int(dev) == 1 or int(dev) == 6:  # 集尘桶设备
            dust_collector_mode(dev, cmd, dat)
        elif int(dev) == 3 or int(dev) == 4:  # 前撞设备
            lt_bump_mode(dev, cmd, dat)
        elif int(dev) == 5:  # 地检组件
            cliff_tool_mode(dev, cmd, dat)
        elif int(dev) == 7:  # 静态电流治具
            robot_static_current_mode(dev, cmd, dat)
        elif int(dev) == 10 or int(dev) == 11:  # 左右轮治具
            left_right_wheel_mode(dev, cmd, dat)
        elif int(dev) == 12:  # 边刷摆臂治具
            side_brush_mode(dev, cmd, dat)
        elif int(dev) == 13:  # 中扫治具
            main_brush_mode(dev, cmd, dat)
        elif int(dev) == 16:
            over_water_mode(dev, cmd, dat)
        elif int(dev) == 15:
            over_air_mode(dev, cmd, dat)
        elif int(dev) == 17:
           hw1_bastation_finished_product_mode(dev, cmd, dat)
        #[FX_TODO]
        elif int(dev) == 50 or (int(load_cfg.dev) == 50 and int(dev) == 0x50):  # #[RV30-PROTO] 帧设备字节 50/0x50 均进 FX
           RV30_finished_product_mode(dev, cmd, dat)


def ser_send_cmd(dev, cmd):
    ck_sum = (0x02 + dev + cmd) % 256
    ser_dat = bytes([0xA5, 0x5A, 0x02, dev, cmd, ck_sum])
    test_serial.test_serial_send(ser_dat)


# 数据 data 是一个字节序列表
def ser_send_data(dev, cmd, data):
    data_len = len(data)
    ck_sum = tool.check_sum([0x02 + data_len, dev, cmd] + data)
    sum_list = [ck_sum]
    ser_dat = bytes([0xA5, 0x5A, 0x02 + data_len, dev, cmd] + data + sum_list)
    print("发送d: ")
    for d in ser_dat:
        print(hex(d), end=' ')
    print(" ")
    test_serial.test_serial_send(ser_dat)


# #[RV30-PROTO] 以下为 RV30 基站(device_type=50) 专用辅助函数（调优入口：hw1_bastation_finished_product_mode_FX）
def rv30_proto_reset_to_idle():
    # #[RV30-PROTO] 一轮测试完全结束后恢复空闲，便于下一轮 0x66
    global rv30_session_state, rv30_last_step, rv30_max_step, rv30_89_mes_done
    global rv30_realtime_ng, rv30_last_p, rv30_last_dust_notify
    rv30_session_state = RV30_SESS_IDLE
    rv30_last_step = -1
    rv30_max_step = 0
    rv30_89_mes_done = False
    rv30_realtime_ng = False
    rv30_last_p = None  # [up_test_ui_WBH]
    rv30_last_dust_notify = -1  # [RV30-尘袋步骤3-WBH]


def rv30_proto_tx_dev_byte():
    # #[RV30-PROTO] 发往治具的「设备」字节：与治具上行帧一致；配置 050 时默认 0x50（十进制80），联调可改
    if int(load_cfg.dev) == 50:
        return 0x50
    return int(load_cfg.dev)


def rv30_proto_mes_ng_once(notify_second="MES已报NG"):
    # #[RV30-PROTO] 发完 0x89 或门闸失败后立即上报 NG，防抖不重复 send_report
    global test_end_time, rv30_89_mes_done, rv30_session_state
    if rv30_89_mes_done:
        return
    rv30_89_mes_done = True
    test_end_time = datetime.now()
    rv30_session_state = RV30_SESS_ABORTED
    mes_run.send_report(test_start_time, test_end_time, check_sn_str, "NG")
    wx.CallAfter(MainFrame.main_frame.up_notification_ui, second=notify_second, color=wx.RED)


def rv30_proto_abort_mes_after_gate_fail():
    # #[RV30-PROTO] 门闸阶段已发 0x58+0x89，此处只做 MES NG 与状态收尾
    rv30_proto_mes_ng_once(notify_second="门闸失败，MES已报NG")


def rv30_proto_realtime_fail(dev, reason):
    # #[RV30-PROTO] 实时阶段仅发 0x89 0x03，不等 0x88 即 MES NG
    global rv30_realtime_ng
    if rv30_89_mes_done:
        return
    rv30_realtime_ng = True
    ser_send_data(dev, 0x89, data=[0x03])
    mes_run.add_report(name="RV30实时判据", result="NG", value=str(reason))
    rv30_proto_mes_ng_once(notify_second="实时判据失败：" + str(reason))


def rv30_proto_parse_68_dat(dat):
    # #[RV30-PROTO-68-MOD] 解析治具 0x68「阈值上传」→ 写入 load_cfg.rv30_*（供 0x77 与 rv30_proto_yaml_realtime_ok 比对）
    # 布局 doc/MES协议.csv「阈值上传」： [0-3]回充 [4-7]版本 [8]频率 [9]尘袋 [10-11]充电min [12-13]充电max [14]LED [15-18]集尘min/max
    global load_cfg

    if len(dat) < RV30_68_DATA_LEN:
        print("[RV30-PROTO-68-MOD] 0x68 数据区长度不足: got", len(dat), "need", RV30_68_DATA_LEN)
        return False

    ir_l, ir_lc, ir_rc, ir_r = (int(dat[i]) for i in range(4))
    ver_raw = ".".join(format(int(dat[i]), "03d") for i in range(4, 8))
    freq = int(dat[8])
    dust_bag = int(dat[9])
    chg_min = _rv30_u16_be(dat[10], dat[11])
    chg_max = _rv30_u16_be(dat[12], dat[13])
    led = int(dat[14])
    suction_min = _rv30_u16_be(dat[15], dat[16])
    suction_max = _rv30_u16_be(dat[17], dat[18])

    # #[RV30-PROTO-68-MOD] 与 rv30_proto_yaml_realtime_ok 四字节 H/L 编码一致（覆盖运行时阈值，yaml 启动值可被治具刷新）
    load_cfg.rv30_ir_l = ir_l
    load_cfg.rv30_ir_lc = ir_lc
    load_cfg.rv30_ir_rc = ir_rc
    load_cfg.rv30_ir_r = ir_r
    load_cfg.rv30_charge_Hmin = (chg_min >> 8) & 0xFF
    load_cfg.rv30_charge_Lmin = chg_min & 0xFF
    load_cfg.rv30_charge_Hmax = (chg_max >> 8) & 0xFF
    load_cfg.rv30_charge_Lmax = chg_max & 0xFF
    load_cfg.rv30_suction_10pa_Hmin = (suction_min >> 8) & 0xFF
    load_cfg.rv30_suction_10pa_Lmin = suction_min & 0xFF
    load_cfg.rv30_suction_10pa_Hmax = (suction_max >> 8) & 0xFF
    load_cfg.rv30_suction_10pa_Lmax = suction_max & 0xFF
    load_cfg.rv30_freq_min = freq
    load_cfg.rv30_freq_max = freq
    load_cfg.rv30_dust_bag_expected = dust_bag
    load_cfg.rv30_led_expected = led

    # #[RV30-PROTO-68-MOD] 兼容旧 dust_th 字段（频率→ac_lv，集尘→barometer/out_barometer，勿再误用气压语义）
    dust_th.cc_min = chg_min
    dust_th.cc_max = chg_max
    dust_th.ac_lv_min = freq
    dust_th.ac_lv_max = freq
    dust_th.barometer_min = suction_min
    dust_th.barometer_max = suction_max
    dust_th.out_barometer_min = suction_min
    dust_th.out_barometer_max = suction_max

    print(
        "[RV30-PROTO-68-MOD] 阈值已加载 ir=%s,%s,%s,%s ver=%s freq=%s dust=%s "
        "chg=[%02X,%02X]-[%02X,%02X] led=%s suction=[%02X,%02X]-[%02X,%02X]"
        % (ir_l, ir_lc, ir_rc, ir_r, ver_raw, freq, dust_bag,
           dat[10], dat[11], dat[12], dat[13], led,
           dat[15], dat[16], dat[17], dat[18])
    )
    return True


def rv30_proto_parse_77_apply_globals(dat):
    # #[RV30-PROTO-77-MOD] 0x77 数据区固定 15 字节（帧长字段=17=设备+命令+数据区）：
    # [0步骤,1左红外,2左中,3右中,4右红外,5~7版本3B,8频率,9尘袋,10~11充电ADC,12LED灯,13~14集尘吸力]；集尘×10Pa
    global charge_value, dev_ver, ver_res
    global ir_code_left, ir_code_lc, ir_code_right, ir_code_rc
    global dust_bug_install, dust_collection_suction
    if len(dat) < 15:
        print("[RV30-PROTO-77-MOD] 0x77 数据区长度不足:", len(dat))
        return None
    step = int(dat[0])
    ir_code_left = int(dat[1])
    ir_code_lc = int(dat[2])
    ir_code_rc = int(dat[3])   # 右中红外（变量名保留，兼容 UI/MES 键）
    ir_code_right = int(dat[4])
    dev_ver = ".".join(format(int(dat[i]), "03d") for i in range(5, 8))
    freq = int(dat[8])
    dust_bug_install = int(dat[9])
    charge_value = int(dat[10]) << 8 | int(dat[11])
    led = int(dat[12])
    dust_collection_suction = (int(dat[13]) << 8 | int(dat[14]))
    if dev_ver == load_cfg.mcu_ver:
        ver_res = "OK"
    else:
        ver_res = "NG"
    return {
        "step": step,
        "ir_l": ir_code_left,
        "ir_lc": ir_code_lc,
        "ir_rc": ir_code_rc,
        "ir_r": ir_code_right,
        "dev_ver": dev_ver,
        "freq": freq,
        "dust": dust_bug_install,
        "charge": charge_value,
        "led": led,
        "suction_pa": dust_collection_suction,
    }


def rv30_field_active(step, field):
    # [RV30-测试项分步报错-WBH] 步骤1回充码；2+版本/频率；3+充电/尘袋/LED(不含集尘)；4+集尘吸力
    st = int(step) if step is not None else 0
    if st < 1:
        return False
    if field in ("ir_l", "ir_lc", "ir_rc", "ir_r"):
        return st >= 1
    if field in ("dev_ver", "freq"):
        return st >= 2
    if field in ("charge", "dust", "led"):
        return st >= 3
    if field == "suction_pa":
        return st >= 4
    return False


# [RV30-步骤3监视-WBH] 步骤3仅监视/尘袋提示，不参与 yaml 实时 NG
RV30_STEP3_MONITOR_FIELDS = ("charge", "dust", "led")


def rv30_step3_monitor_phase(p):
    # [RV30-步骤3监视-WBH]
    return p is not None and int(p.get("step", 0)) == 3


def rv30_dust_step3_ui(p):
    # [RV30-尘袋步骤3-WBH] 0/1/2/3 → 未测试/红+文案/绿；步骤3不打断流程
    d = int(p.get("dust", 0))
    if d == 0:
        return "untested", ""
    if d == 1:
        return "fail", "取出尘袋"
    if d == 2:
        return "fail", "放入尘袋"
    if d == 3:
        return "pass", str(d)
    return "fail", str(d)


def rv30_dust_step3_notify(p):
    # [RV30-尘袋步骤3-WBH] 顶部提示：1 取出 / 2 放入 / 3 通过；0 不改动
    global rv30_last_dust_notify
    if p is None or int(p.get("step", 0)) != 3:
        return
    d = int(p.get("dust", 0))
    if d == rv30_last_dust_notify:
        return
    rv30_last_dust_notify = d
    mf = MainFrame.main_frame
    if mf is None:
        return
    if d == 1:
        mf.up_notification_ui(second="取出尘袋", color=wx.RED)
    elif d == 2:
        mf.up_notification_ui(second="放入尘袋", color=wx.RED)
    elif d == 3:
        mf.up_notification_ui(second="请工人观察LED灯显示，正常按开始键，异常按结束键", color=wx.RED)


def rv30_dust_field_status(p):
    # [RV30-尘袋步骤3-WBH] 步骤3用状态机；步骤>3 仍用 yaml 期望(通常为3)
    if p is None:
        return "untested"
    step = int(p.get("step", 0))
    if step < 3:
        return "untested"
    if step == 3:
        d = int(p.get("dust", 0))
        if d == 0:
            return "untested"
        if d in (1, 2):
            return False
        if d == 3:
            return True
        return False
    return rv30_field_ok(p, "dust")


def rv30_dust_flow_complete(p):
    # [RV30-尘袋步骤3-WBH] 曾到步骤3则结束帧要求 dust==3
    if p is None:
        return True
    if int(p.get("step", 0)) < 3:
        return True
    return int(p.get("dust", 0)) == 3


def rv30_field_status(p, field):
    # [RV30-测试项分步报错-WBH] 未到步骤→"untested"；到步骤后同 rv30_field_ok(True/False/None)
    # [RV30-步骤3监视-WBH] 步骤3：charge/led 仅 monitor；dust 走状态机
    if p is None:
        return "untested"
    step = int(p.get("step", 0))
    if field == "dust":
        return rv30_dust_field_status(p)
    if step == 3 and field in ("charge", "led"):
        return None
    if not rv30_field_active(step, field):
        return "untested"
    return rv30_field_ok(p, field)


def rv30_field_status_finalize(p, field):
    # [RV30-步骤3监视-WBH] 0x88 终态：step>=4 按 yaml 全量判；step==3 仍用尘袋状态机
    if p is None:
        return "untested"
    step = int(p.get("step", 0))
    if step == 3:
        if field == "dust":
            return rv30_dust_field_status(p)
        if field in ("charge", "led"):
            return None
        if not rv30_field_active(step, field):
            return "untested"
        return rv30_field_ok(p, field)
    if step < 4:
        return rv30_field_status(p, field)
    if field == "dust":
        d = int(p.get("dust", 0))
        return True if d == 3 else False
    if not rv30_field_active(step, field):
        return "untested"
    return rv30_field_ok(p, field)


def rv30_proto_yaml_all_items_ok(p):
    # [RV30-步骤4终判-WBH] 步骤4：对已开放项做全量 yaml 比对（False=NG；None=未配置跳过）
    if p is None:
        return False
    step = int(p.get("step", 0))
    if step < 4:
        return False
    for field in (
        "dev_ver", "charge", "suction_pa", "freq",
        "ir_l", "ir_lc", "ir_rc", "ir_r", "dust", "led",
    ):
        if not rv30_field_active(step, field):
            continue
        if field == "dust":
            if int(p.get("dust", 0)) != 3:
                return False
            continue
        ok = rv30_field_ok(p, field)
        if ok is False:
            return False
    return True


def rv30_proto_yaml_finalize_ok(p):
    # [RV30-步骤4终判-WBH] 0x88 综合 PASS：本轮须到过步骤4，且最后一帧在步骤4+且全项达标
    global rv30_max_step
    if rv30_max_step < 4:
        return False
    if p is None:
        return False
    if int(p.get("step", 0)) < 4:
        return False
    return rv30_proto_yaml_all_items_ok(p)


def rv30_field_ok(p, field):
    # [up_test_ui_WBH] 单项判据：True/False=参与比较；None=yaml 未配置该项
    if p is None:
        return None
    if field == "dev_ver":
        expect_ver = (load_cfg.mcu_ver or "").strip()
        if not expect_ver:
            return None
        return p.get("dev_ver") == expect_ver
    if field == "charge":
        ch = (
            load_cfg.rv30_charge_Hmin, load_cfg.rv30_charge_Lmin,
            load_cfg.rv30_charge_Hmax, load_cfg.rv30_charge_Lmax,
        )
        if ch == (0, 0, 0, 0):
            return None
        lo = (ch[0] << 8) | (ch[1] & 0xFF)
        hi = (ch[2] << 8) | (ch[3] & 0xFF)
        if lo > hi:
            lo, hi = hi, lo
        return lo <= p["charge"] <= hi
    if field == "suction_pa":
        su = (
            load_cfg.rv30_suction_10pa_Hmin, load_cfg.rv30_suction_10pa_Lmin,
            load_cfg.rv30_suction_10pa_Hmax, load_cfg.rv30_suction_10pa_Lmax,
        )
        if su == (0, 0, 0, 0):
            return None
        slo = (su[0] << 8) | (su[1] & 0xFF)
        shi = (su[2] << 8) | (su[3] & 0xFF)
        if slo > shi:
            slo, shi = shi, slo
        return slo <= p["suction_pa"] <= shi
    if field == "freq":
        fmin, fmax = load_cfg.rv30_freq_min, load_cfg.rv30_freq_max
        if fmin == 0 and fmax == 0:
            return None
        flo, fhi = (fmin, fmax) if fmin <= fmax else (fmax, fmin)
        return flo <= p["freq"] <= fhi
    if field == "ir_l":
        if not load_cfg.rv30_ir_l:
            return None
        return p["ir_l"] == load_cfg.rv30_ir_l
    if field == "ir_lc":
        if not load_cfg.rv30_ir_lc:
            return None
        return p["ir_lc"] == load_cfg.rv30_ir_lc
    if field == "ir_rc":
        if not load_cfg.rv30_ir_rc:
            return None
        return p["ir_rc"] == load_cfg.rv30_ir_rc
    if field == "ir_r":
        if not load_cfg.rv30_ir_r:
            return None
        return p["ir_r"] == load_cfg.rv30_ir_r
    if field == "dust":
        if not load_cfg.rv30_dust_bag_expected:
            return None
        return p["dust"] == load_cfg.rv30_dust_bag_expected
    if field == "led":
        if not load_cfg.rv30_led_expected:
            return None
        return p["led"] == load_cfg.rv30_led_expected
    return None


def rv30_proto_yaml_realtime_ok(p):
    # #[RV30-PROTO] 以 config.yaml 为主与 0x77 解析结果比对；返回 False 表示应走实时异常
    # [up_test_ui_WBH] 汇总单项 rv30_field_ok
    # [RV30-测试项分步报错-WBH] 仅当前治具步骤已开放的项参与实时 NG
    # [RV30-步骤3监视-WBH] 步骤3整帧不实时 NG（尘袋提示+充电/LED 监视），步骤4再判
    if p is None:
        return True
    step = int(p.get("step", 0))
    if step == 3:
        return True
    for field in (
        "dev_ver", "charge", "suction_pa", "freq",
        "ir_l", "ir_lc", "ir_rc", "ir_r", "dust", "led",
    ):
        if not rv30_field_active(step, field):
            continue
        ok = rv30_field_ok(p, field)
        if ok is False:
            return False
    return True


def rv30_proto_ui_result_str(ok):
    # [up_test_ui_WBH] 单项判据 → up_test_ui 的 result 参数
    # [RV30-测试项分步报错-WBH]
    if ok == "untested":
        return "untested"
    if ok is True:
        return "pass"
    if ok is False:
        return "fail"
    return "monitor"


def rv30_proto_apply_test_ui_row(p, ui_name, field, val, finalize=False):
    # [RV30-步骤3监视-WBH] 统一刷新单行；finalize 用终态判据
    if finalize:
        st = rv30_field_status_finalize(p, field)
    else:
        if field == "dust" and rv30_step3_monitor_phase(p):
            res, show_val = rv30_dust_step3_ui(p)
            MainFrame.main_frame.up_test_ui(name=ui_name, result=res, value=show_val)
            return
        if rv30_step3_monitor_phase(p) and field in ("charge", "led"):
            MainFrame.main_frame.up_test_ui(name=ui_name, result="monitor", value=val)
            return
        st = rv30_field_status(p, field)
    if st == "untested":
        res, show_val = "untested", ""
    elif st is False:
        res, show_val = "fail", val
    elif st is True:
        res, show_val = "pass", val
    else:
        res, show_val = "monitor", val
    MainFrame.main_frame.up_test_ui(name=ui_name, result=res, value=show_val)


def rv30_proto_refresh_test_ui(p, finalize=False):
    # [up_test_ui_WBH] 0x77 实时刷新 test_static_box（须在 UI 线程 CallAfter 调用）
    # [RV30-测试项分步报错-WBH] 未到步骤显示未测试，到步骤后再判 pass/fail/monitor
    # [RV30-步骤3监视-WBH] 步骤3 charge/led 仅 monitor；0x88 且 step>=4 时 finalize=True 全量判
    if p is None or MainFrame.main_frame is None:
        return
    rows = [
        ("mcu_ver", "dev_ver", p["dev_ver"]),
        ("ir_code_left", "ir_l", str(p["ir_l"])),
        ("ir_code_lc", "ir_lc", str(p["ir_lc"])),
        ("ir_code_rc", "ir_rc", str(p["ir_rc"])),
        ("ir_code_right", "ir_r", str(p["ir_r"])),
        ("charge_value", "charge", str(p["charge"])),
        ("rv30_freq", "freq", str(p["freq"])),
        ("dust_bug_install", "dust", str(p["dust"])),
        ("rv30_led", "led", str(p["led"])),
        ("dust_collection_suction", "suction_pa", str(p["suction_pa"])),
    ]
    for ui_name, field, val in rows:
        rv30_proto_apply_test_ui_row(p, ui_name, field, val, finalize=finalize)
    if not finalize and rv30_step3_monitor_phase(p):
        rv30_dust_step3_notify(p)


def rv30_proto_refresh_test_ui_callafter(p):
    # [up_test_ui_WBH] 从串口线程安全投递到 UI 线程
    wx.CallAfter(rv30_proto_refresh_test_ui, p)


def rv30_proto_add_fx_reports():
    # #[RV30-PROTO] 上报 MES 明细项（与旧 hw1 FX 列表对齐，便于调优对比历史）
    mes_run.add_report(name="mcu软件版本", result=ver_res, value=dev_ver, val_max=load_cfg.mcu_ver, val_min=load_cfg.mcu_ver)
    mes_run.add_report(name="充电电流", result="", value=str(charge_value))
    mes_run.add_report(name="左回充码", result="", value=str(ir_code_left))
    # #[RV30-PROTO-77-MOD] 四路红外与 0x77 下标 1~4 对齐
    mes_run.add_report(name="左中回充码", result="", value=str(ir_code_lc))
    mes_run.add_report(name="右中回充码", result="", value=str(ir_code_rc))
    mes_run.add_report(name="右回充码", result="", value=str(ir_code_right))
    mes_run.add_report(name="尘袋在位", result="", value=str(dust_bug_install))
    mes_run.add_report(name="集尘吸力Pa", result="", value=str(dust_collection_suction))


def rv30_proto_finalize_88(dev, dat):
    # #[RV30-PROTO] 收到 0x88：与首字节 01/02/03 无严格 MES 映射；综合 ver_res、rv30_realtime_ng、约定正常结束=0x03
    global test_end_time, rv30_session_state
    test_end_time = datetime.now()
    res_byte = dat[0] if len(dat) else 0xFF
    if rv30_89_mes_done:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试失败", color=wx.RED)
        rv30_session_state = RV30_SESS_FINISHED
        clear_sn_save_list()
        rv30_proto_reset_to_idle()
        return
    normal_end = res_byte == 0x03
    global rv30_last_p
    # [RV30-步骤4终判-WBH] 须到过步骤4且最后一帧全项达标；步骤3不 fail，步骤1/2 仍走实时 NG
    mes_ok = (normal_end and (not rv30_realtime_ng) and (ver_res == "OK")
              and rv30_proto_yaml_finalize_ok(rv30_last_p))
    # [RV30-步骤3监视-WBH] MES 明细仅在 0x88 统一写入（步骤3不上传）
    rv30_proto_add_fx_reports()
    if mes_ok:
        mes_run.add_report(name="led", result="OK")
        res_display_str = "测试完成(综合判定 PASS)"
        text_color = wx.GREEN
        mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "OK")
    else:
        mes_run.add_report(name="led", result="NG")
        res_display_str = "测试结束(综合判定 NG)"
        text_color = wx.RED
        mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "NG")
    # [up_test_ui_WBH] 结束帧用最后一帧 0x77 刷新测试格；综合 NG 时未配置阈值的项也标 fail
    # [RV30-测试项分步报错-WBH] 结束刷新同样按最后一帧 step 分步；未到步骤保持未测试
    if rv30_last_p is not None:
        use_finalize_ui = int(rv30_last_p.get("step", 0)) >= 4
        if mes_ok:
            wx.CallAfter(
                rv30_proto_refresh_test_ui, rv30_last_p, use_finalize_ui)
        else:
            def _finalize_ui_refresh():
                p = rv30_last_p
                if p is None:
                    return
                rows = [
                    ("mcu_ver", "dev_ver", p["dev_ver"]),
                    ("ir_code_left", "ir_l", str(p["ir_l"])),
                    ("ir_code_lc", "ir_lc", str(p["ir_lc"])),
                    ("ir_code_rc", "ir_rc", str(p["ir_rc"])),
                    ("ir_code_right", "ir_r", str(p["ir_r"])),
                    ("charge_value", "charge", str(p["charge"])),
                    ("rv30_freq", "freq", str(p["freq"])),
                    ("dust_bug_install", "dust", str(p["dust"])),
                    ("rv30_led", "led", str(p["led"])),
                    ("dust_collection_suction", "suction_pa", str(p["suction_pa"])),
                ]
                fin = int(p.get("step", 0)) >= 4
                for ui_name, field, val in rows:
                    if not fin and field == "dust" and int(p.get("step", 0)) == 3:
                        res, show_val = rv30_dust_step3_ui(p)
                        MainFrame.main_frame.up_test_ui(
                            name=ui_name, result=res, value=show_val)
                        continue
                    if fin:
                        rv30_proto_apply_test_ui_row(
                            p, ui_name, field, val, finalize=True)
                        continue
                    st = rv30_field_status(p, field)
                    if st == "untested":
                        res, show_val = "untested", ""
                    elif st is False or (rv30_realtime_ng and st is not True):
                        res, show_val = "fail", val
                    elif st is True:
                        res, show_val = "pass", val
                    else:
                        res, show_val = "monitor", val
                    MainFrame.main_frame.up_test_ui(
                        name=ui_name, result=res, value=show_val)

            wx.CallAfter(_finalize_ui_refresh)
    if mes_ret:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second=res_display_str, color=text_color)
    rv30_session_state = RV30_SESS_FINISHED
    clear_sn_save_list()
    rv30_proto_reset_to_idle()


# 静态电流测试
def robot_static_current_mode(dev, cmd, dat):
    global check_sn_enable
    global test_start_time
    global test_end_time

    if len(dat) <= 0:
        print("len=0 无有效数据")
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具数据异常",
                     color=wx.RED)
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x02:  # 开始测试
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
    elif cmd == 0x02:  # 测试记录
        ser_send_cmd(dev, cmd)  # # 回复夹具开始测试
        if dat[0] == 0x01:
            static_cur_res = 'OK'
        elif dat[0] == 0x02:
            static_cur_res = 'NG'
        else:
            static_cur_res = 'un_test'
        if len(dat) >= 13:
            cur_res = (int(dat[1]) * 256 + int(dat[2]))
            cur_res = cur_res * 256 + int(dat[3])
            cur_res = cur_res * 256 + int(dat[4])
            vol_res = (int(dat[5]) * 256 + int(dat[6]))
            p_res = (int(dat[7]) * 256 + int(dat[8]))
            cur_max = (int(dat[9]) * 256 + int(dat[10]))
            cur_min = (int(dat[11]) * 256 + int(dat[12]))
            print("静态电流 vol：" + str(vol_res) + " p: " + "p_res")

            mes_run.add_report(name="静态电流测试", result=static_cur_res,
                               value=str(cur_res),
                               val_max=str(cur_max),
                               val_min=str(cur_min))
    elif cmd == 0x88:  # 测试结束
        test_end_time = datetime.now()
        static_cur_res = "NG"
        if dat[0] == 0x01:    # 测试成功
            static_cur_res = "OK"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试  PASS",
                         color=wx.GREEN)
        elif dat[0] == 0x02:  # 测试失败
            static_cur_res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试  NG",
                         color=wx.RED)
        elif dat[0] == 0x0A:  # 停止测试
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试停止",
                         color=wx.RED)
        elif dat[0] == 0x0E:  # 扫码异常，check sn 出错
            pass
        if dat[0] == 0x01 or dat[0] == 0x02:
            mes_run.send_report(test_start_time, test_end_time, check_sn_str, static_cur_res)


def left_right_wheel_mode(dev, cmd, dat):
    global check_sn_enable
    global test_start_time
    global test_end_time

    if len(dat) <= 0:
        print("len=0 无有效数据")
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具数据异常",
                     color=wx.RED)
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x02 or dat[0] == 0x01:  # 开始测试
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
    elif cmd == 0x02:  # 测试记录
        ser_send_cmd(dev, cmd)  # # 回复夹具开始测试
        if len(dat) >= 24:
            forward_current = (int(dat[1]) * 256 + int(dat[2]))  # 正转电流
            byte_data = bytes([dat[3], dat[4]])
            forward_speed = int.from_bytes(byte_data, byteorder="big", signed=True)  # 正转速度
            reverse_current = (int(dat[5]) * 256 + int(dat[6]))  # 反转电流
            byte_data = bytes([dat[7], dat[8]])
            reverse_speed = int.from_bytes(byte_data, byteorder="big", signed=True)  # 反转速度
            locked_current = (int(dat[9]) * 256 + int(dat[10]))  # 堵转电流
            current_unit = int(dat[11])  # 电流单位 01 A, 02 mA, 03 uA
            current_min = (int(dat[12]) * 256 + int(dat[13]))  # 空载电流下限
            current_max = (int(dat[14]) * 256 + int(dat[15]))  # 空载电流上限
            speed_min = (int(dat[16]) * 256 + int(dat[17]))  # 空载速度下限
            speed_max = (int(dat[18]) * 256 + int(dat[19]))  # 空载速度上限
            locked_min = (int(dat[20]) * 256 + int(dat[21]))  # 堵转电流下限
            locked_max = (int(dat[22]) * 256 + int(dat[23]))  # 堵转电流上限
            if current_unit == 0x01:
                unit = "A"
            elif current_unit == 0x02:
                unit = "mA"
            elif current_unit == 0x03:
                unit = "uA"
            else:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具数据异常",
                             color=wx.RED)
                return
            print("空载电流，速度阀值，堵转阀值", current_min, current_max, speed_min, speed_max, locked_min, locked_max)
            print("空载，正反转电流，速度：", forward_current, reverse_current, forward_speed, reverse_speed)
            print("堵转电流：", str(locked_current)+unit)
            mes_run.add_report(name="正转电流", result=get_res(forward_current, current_min, current_max),
                               value=str(forward_current) + unit,
                               val_max=str(current_max) + unit,
                               val_min=str(current_min) + unit)
            mes_run.add_report(name="反转电流", result=get_res(reverse_current, current_min, current_max),
                               value=str(reverse_current) + unit,
                               val_max=str(current_max) + unit,
                               val_min=str(current_min) + unit)
            mes_run.add_report(name="堵转电流", result=get_res(locked_current, locked_min, locked_max),
                               value=str(locked_current) + unit,
                               val_max=str(locked_max) + unit,
                               val_min=str(locked_min) + unit)
            unit = "RPM"
            mes_run.add_report(name="正转速度", result=get_res(forward_speed, speed_min, speed_max),
                               value=str(forward_speed) + unit,
                               val_max=str(speed_max) + unit,
                               val_min=str(speed_min) + unit)
            mes_run.add_report(name="反转速度", result=get_res(reverse_speed, -speed_max, -speed_min),
                               value=str(reverse_speed) + unit,
                               val_max='-' + str(speed_min) + unit,
                               val_min='-' + str(speed_max) + unit)
    elif cmd == 0x88:  # 测试结束
        test_end_time = datetime.now()
        res = "NG"
        if dat[0] == 0x01:    # 测试成功
            res = "OK"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试  PASS",
                         color=wx.GREEN)
        elif dat[0] == 0x02:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="空载电流异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x03:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="堵转电流异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x04:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="堵转测试异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x05:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="速度测试异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x09:  # 测试失败，边刷治具，编码器异常
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具编码器异常，请检测  NG",
                         color=wx.RED)
        elif dat[0] == 0x0A:  # 停止测试
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试停止",
                         color=wx.RED)
        elif dat[0] == 0x0E:  # 扫码枪错误
            pass
        mes_res = True
        if 0x05 >= dat[0] >= 0x01:
            mes_res = mes_run.send_report(test_start_time, test_end_time, check_sn_str, res)
        if mes_res:
            data_list = [0x01]
        else:
            data_list = [0x02]
        ser_send_data(dev, 0x89, data_list)  # # 回复夹具开始测试


# 边刷摆臂测试治具
def side_brush_mode(dev, cmd, dat):
    global check_sn_enable
    global test_start_time
    global test_end_time
    print(dat)
    if len(dat) <= 0:
        print("len=0 无有效数据")
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具数据异常",
                     color=wx.RED)
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x02 or dat[0] == 0x01:  # 开始测试
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
    elif cmd == 0x02:  # 测试记录
        ser_send_cmd(dev, cmd)  # # 回复夹具开始测试
        if len(dat) >= 30:
            byte_data = bytes([dat[1], dat[2]])
            forward_current = int.from_bytes(byte_data, byteorder="big", signed=True)
            byte_data = bytes([dat[3], dat[4]])
            reverse_current = int.from_bytes(byte_data, byteorder="big", signed=True)
            locked_current = (int(dat[5]) * 256 + int(dat[6]))  # 边刷，堵转电流
            motor_out_current = (int(dat[7]) * 256 + int(dat[8]))  # 摆出电流
            motor_in_current = (int(dat[9]) * 256 + int(dat[10]))  # 摆入电流
            limit_switch = int(dat[11])  # 微动开关检测
            motor_travel = int(dat[12])  # 摆臂行程
            current_unit = int(dat[13])  # 电流单位 01 A, 02 mA, 03 uA
            current_min = (int(dat[14]) * 256 + int(dat[15]))  # 空载电流下限
            current_max = (int(dat[16]) * 256 + int(dat[17]))  # 空载电流上限
            locked_min = (int(dat[18]) * 256 + int(dat[19]))  # 堵转电流下限，边刷堵转
            locked_max = (int(dat[20]) * 256 + int(dat[21]))  # 堵转电流上限，边刷堵转
            out_in_current_min = (int(dat[22]) * 256 + int(dat[23]))  # 堵转电流上限
            out_in_current_max = (int(dat[24]) * 256 + int(dat[25]))  # 堵转电流上限
            out_in_locked_min = (int(dat[26]) * 256 + int(dat[27]))  # 摆臂堵转电流上限，不测试
            out_in_locked_max = (int(dat[28]) * 256 + int(dat[29]))  # 摆臂堵转电流上限，不测试

            if current_unit == 0x01:
                unit = "A"
            elif current_unit == 0x02:
                unit = "mA"
            elif current_unit == 0x03:
                unit = "uA"
            else:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具数据异常",
                             color=wx.RED)
                return
            mes_run.add_report(name="边刷正转电流", result=get_res(forward_current, current_min, current_max),
                               value=str(forward_current) + unit,
                               val_max=str(current_max) + unit,
                               val_min=str(current_min) + unit)
            mes_run.add_report(name="边刷反转电流", result=get_res(reverse_current, -current_max, -current_min),
                               value=str(reverse_current) + unit,
                               val_max='-' + str(current_min) + unit,
                               val_min='-' + str(current_max) + unit)
            mes_run.add_report(name="边刷堵转电流", result=get_res(locked_current, locked_min, locked_max),
                               value=str(locked_current) + unit,
                               val_max=str(locked_max) + unit,
                               val_min=str(locked_min) + unit)
            mes_run.add_report(name="摆臂伸出电流", result=get_res(motor_out_current, out_in_current_min, out_in_current_max),
                               value=str(motor_out_current) + unit,
                               val_max=str(out_in_current_max) + unit,
                               val_min=str(out_in_current_min) + unit)
            mes_run.add_report(name="摆臂收回电流", result=get_res(motor_in_current, out_in_current_min, out_in_current_max),
                               value=str(motor_in_current) + unit,
                               val_max=str(out_in_current_max) + unit,
                               val_min=str(out_in_current_min) + unit)
            if motor_travel == 0xff:
                make_res = "un_test"
            elif motor_travel == 0x01:
                make_res = "OK"
            else:
                make_res = "NG"
            mes_run.add_report(name="摆臂行程", result=make_res, value=make_res)
            if limit_switch == 0xff:
                make_res = "un_test"
            elif limit_switch == 0x01:
                make_res = "OK"
            else:
                make_res = "NG"
            mes_run.add_report(name="摆臂微动开关", result=make_res, value=make_res)
    elif cmd == 0x88:  # 测试结束
        test_end_time = datetime.now()
        res = "NG"
        if dat[0] == 0x01:    # 测试成功
            res = "OK"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试  PASS",
                         color=wx.GREEN)
        elif dat[0] == 0x02:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="边刷空载电流异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x03:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="边刷堵转电流异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x04:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="边刷堵转测试异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x05:  # 测试失败，边刷速度异常，不使用
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="边刷速度测试异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x06:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="摆臂电流测试异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x07:  # 测试失败，边刷速度异常，不使用
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="摆臂手动开关测试异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x08:  # 测试失败，边刷速度异常，不使用
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="摆臂行程测试异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x09:  # 测试失败，边刷治具，编码器异常
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具编码器异常，请检测  NG",
                         color=wx.RED)
        elif dat[0] == 0x0A:  # 停止测试
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试停止",
                         color=wx.RED)
        elif dat[0] == 0x0E:  # 扫码枪错误
            pass
        mes_res = True
        if 0x08 >= dat[0] >= 0x01:
            mes_res = mes_run.send_report(test_start_time, test_end_time, check_sn_str, res)
        if mes_res:  # 上次数据私发通过
            data_list = [0x01]
        else:
            data_list = [0x02]
        ser_send_data(dev, 0x89, data_list)  # # 回复夹具开始测试


def main_brush_mode(dev, cmd, dat):
    global check_sn_enable
    global test_start_time
    global test_end_time

    if len(dat) <= 0:
        print("len=0 无有效数据")
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具数据异常",
                     color=wx.RED)
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x02 or dat[0] == 0x01:  # 开始测试
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
    elif cmd == 0x02:  # 测试记录
        ser_send_cmd(dev, cmd)  # # 回复夹具开始测试
        if len(dat) >= 16:

            byte_data = bytes([dat[1], dat[2]])
            forward_current = int.from_bytes(byte_data, byteorder="big", signed=True)  # 正转电流
            byte_data = bytes([dat[3], dat[4]])
            reverse_current = int.from_bytes(byte_data, byteorder="big", signed=True)  # 反转电流
            locked_current = (int(dat[5]) * 256 + int(dat[6]))  # 堵转电流
            current_unit = int(dat[7])  # 电流单位 01 A, 02 mA, 03 uA
            current_min = (int(dat[8]) * 256 + int(dat[9]))  # 空载电流下限
            current_max = (int(dat[10]) * 256 + int(dat[11]))  # 空载电流上限
            locked_min = (int(dat[12]) * 256 + int(dat[13]))  # 空载速度下限
            locked_max = (int(dat[14]) * 256 + int(dat[15]))  # 空载速度上限

            if current_unit == 0x01:
                unit = "A"
            elif current_unit == 0x02:
                unit = "mA"
            elif current_unit == 0x03:
                unit = "uA"
            else:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具数据异常",
                             color=wx.RED)
                return
            mes_run.add_report(name="正转电流", result=get_res(forward_current, current_min, current_max),
                               value=str(forward_current) + unit,
                               val_max=str(current_max) + unit,
                               val_min=str(current_min) + unit)
            mes_run.add_report(name="反转电流", result=get_res(reverse_current, -current_max, -current_min),
                               value=str(reverse_current) + unit,
                               val_max='-' + str(current_min) + unit,
                               val_min='-' + str(current_max) + unit),
            mes_run.add_report(name="堵转电流", result=get_res(locked_current, locked_min, locked_max),
                               value=str(locked_current) + unit,
                               val_max=str(locked_max) + unit,
                               val_min=str(locked_min) + unit)

    elif cmd == 0x88:  # 测试结束
        test_end_time = datetime.now()
        res = "NG"
        if dat[0] == 0x01:    # 测试成功
            res = "OK"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试  PASS",
                         color=wx.GREEN)
        elif dat[0] == 0x02:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="空载电流异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x03:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="堵转电流异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x04:  # 测试失败
            res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="堵转测试异常  NG",
                         color=wx.RED)
        elif dat[0] == 0x0A:  # 停止测试
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试停止",
                         color=wx.RED)
        elif dat[0] == 0x0E:  # 扫码枪错误
            pass
        mes_res = True
        if 0x04 >= dat[0] >= 0x01:
            mes_res = mes_run.send_report(test_start_time, test_end_time, check_sn_str, res)
        if mes_res:
            data_list = [0x01]
        else:
            data_list = [0x02]
        ser_send_data(dev, 0x89, data_list)  # # 回复夹具开始测试


sn_left = ""
sn_right = ""


# 地检组件测试
def cliff_tool_mode(dev, cmd, dat):
    global check_sn_enable
    global test_start_time
    global test_end_time
    global cliff_sn_dict
    global sn_left
    global sn_right
    global check_sn_str

    if len(dat) <= 0:
        print("len=0 无有效数据")
        return

    if type(cmd) is str:
        if cmd == "sn":  # 收到SN信息
            sn_num = len(dat)
            str_list = [0x00, 0x00, 0x00, 0x00]
            if sn_num == 0 or sn_num > 2:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                             first="输入的SN数量异常: " + str(sn_num),
                             color=wx.RED)
                ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
                return
            sn_left = ""
            sn_right = ""
            match_res = False
            if sn_num == 1:
                sn_left = str(dat[0])
                match_res = encode_rules.match_sn_encoding_rules(dev=load_cfg.dev, sn=str(sn_left))
                if match_res is False:
                    wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=1,
                                 text="左地检SN:" + str(sn_left) + " " + "编码异常",
                                 color=wx.RED)
            elif sn_num == 2:
                sn_left = str(dat[0])
                match_res = encode_rules.match_sn_encoding_rules(dev=load_cfg.dev, sn=str(sn_left))
                if match_res is False:
                    wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=1,
                                 text="左地检SN:" + str(sn_left) + " " + "编码异常",
                                 color=wx.RED)
                sn_right = str(dat[1])
                match_res_temp = encode_rules.match_sn_encoding_rules(dev=load_cfg.dev, sn=str(sn_right))
                if match_res_temp is False:
                    wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=2,
                                 text="右地检：" + str(sn_right) + " " + "编码异常",
                                 color=wx.RED)
                if match_res is False or match_res_temp is False:
                    match_res = False

            if sn_num == 2 and sn_left == sn_right:  # 左右SN相同
                wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=3,
                             text="输入的左右地检条码不能相同",
                             color=wx.RED)
                # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具扫码失败
                sn_string = sn_left + '&' + sn_right
                str_list = [int(byte) for byte in sn_string.encode('utf-8')]
                ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
                return
            elif match_res is False:  # 编码异常
                # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具扫码失败
                ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
                return

            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=1,
                         text="左地检SN:" + str(sn_left) + " " + "过站检测",
                         color=wx.RED)
            # mes 过站
            res = True
            res = mes_run.check_sn_is_ok(sn_left)
            # print(str_list)
            if res:
                ser_send_data(dev=int(load_cfg.dev), cmd=0x57, data=str_list)
                # ser_send_cmd(int(load_cfg.dev), 0x57)  # 回复夹具开始测试
            else:
                # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具扫码失败
                ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
            check_sn_enable = False
    elif cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            if TWO_CLIFF_SENSOR_MODE_EN is True:
                start_sn_collect(first="左地检SN：", second="右地检SN：")
            else:
                start_sn_collect(first="请输入地检SN:")
            # start_sn_collect(first="请输入左地检SN：", third="请输入右地检SN：")

        elif dat[0] == 0x02:  # 开始测试
            print('开始测试')
            # wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
    elif cmd == 0x02:  # 测试记录
        if dat[0] == 0x01:
            cliff_led1_res = 'OK'
        elif dat[0] == 0x02:
            cliff_led1_res = 'NG'
        else:
            cliff_led1_res = 'un_test'
        if dat[1] == 0x01:
            cliff_led2_res = 'OK'
        elif dat[1] == 0x02:
            cliff_led2_res = 'NG'
        else:
            cliff_led2_res = 'un_test'

        led_white_min = (int(dat[2]) * 256 + int(dat[3]))
        led_white_max = (int(dat[4]) * 256 + int(dat[5]))

        led_black_min = (int(dat[6]) * 256 + int(dat[7]))
        led_black_max = (int(dat[8]) * 256 + int(dat[9]))

        led1_white = (int(dat[10]) * 256 + int(dat[11]))
        led1_black = (int(dat[14]) * 256 + int(dat[15]))

        led2_white = (int(dat[12]) * 256 + int(dat[13]))
        led2_black = (int(dat[16]) * 256 + int(dat[17]))

        ser_send_cmd(dev, cmd)  # # 回复夹具开始测试

        test_end_time = datetime.now()
        check_sn_str = sn_left
        mes_run.clear_report()  # 清除mes待上传记录
        mes_run.add_report(name="地检白板-黑板-测试LED1", result=cliff_led1_res,
                           value='白板：' + str(led1_white) + ',黑板：' + str(led1_black),
                           val_max='白板：' + str(led_white_max) + ',黑板：' + str(led_black_max),
                           val_min='白板：' + str(led_white_min) + ',黑板：' + str(led_black_min))
        if TWO_CLIFF_SENSOR_MODE_EN is False:
            return
        mes_res = mes_run.send_report(test_start_time, test_end_time, check_sn_str, cliff_led1_res)
        if mes_res is not True:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=1,
                         text="左地检SN:" + str(sn_left) + " " + "NG",
                         color=wx.RED)
            str_list = [0x00, 0x00, 0x00, 0x00]
            # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具扫码失败
            ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
            return
        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=1,
                     text="左地检SN:" + str(sn_left) + " " + cliff_led1_res,
                     color=wx.RED)
        check_sn_str = sn_right
        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=2,
                     text="右地检SN:" + str(sn_right) + " " + cliff_led1_res,
                     color=wx.RED)
        mes_run.clear_report()  # 清除mes待上传记录
        sn_res = mes_run.check_sn_is_ok(check_sn_str)
        cliff_res = cliff_led2_res
        if sn_res:
            mes_run.add_report(name="地检白板-黑板-测试LED2", result=cliff_led2_res,
                               value='白板：' + str(led2_white) + ',黑板：' + str(led2_black),
                               val_max='白板：' + str(led_white_max) + ',黑板：' + str(led_black_max),
                               val_min='白板：' + str(led_white_min) + ',黑板：' + str(led_black_min))
            mes_res = mes_run.send_report(test_start_time, test_end_time, sn_right, cliff_led2_res)
        else:
            str_list = [0x00, 0x00, 0x00, 0x00]
            # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具扫码失败
            ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=2,
                         text="右地检SN:" + str(sn_right) + " " + "NG",
                         color=wx.RED)
            return
        if mes_res is not True:
            str_list = [0x00, 0x00, 0x00, 0x00]
            # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具扫码失败
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=2,
                         text="右地检SN:" + str(sn_right) + " " + "NG",
                         color=wx.RED)
            ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
            return
        else:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=2,
                         text="右地检SN:" + str(sn_right) + " " + cliff_led2_res,
                         color=wx.RED)

    elif cmd == 0x88:  # 测试结束
        test_end_time = datetime.now()

        check_sn_enable = False
        cliff_res = "NG"
        if dat[0] == 0x01:    # 测试成功
            cliff_res = "OK"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=3,
                         text="测试  PASS",
                         color=wx.GREEN)
        elif dat[0] == 0x02:  # 测试失败
            cliff_res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=3,
                         text="测试  NG",
                         color=wx.RED)
        elif dat[0] == 0x0A:  # 停止测试
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=3,
                         text="测试停止",
                         color=wx.RED)
        elif dat[0] == 0x0E:  # 扫码异常，check sn 出错
            print("扫码枪异常")
        mes_res = True
        if dat[0] != 0x0E and dat[0] != 0x0A:
            pass
            # mes_res = mes_run.send_report(test_start_time, test_end_time, check_sn_str, cliff_res)
        if mes_res:
            data_list = [0x01]
        else:
            data_list = [0x02]
        ser_send_data(dev, 0x89, data_list)  # # 回复夹具开始测试


# 前撞设备，组件或PCB
def lt_bump_mode(dev, cmd, dat):
    global check_sn_enable
    global test_start_time
    global test_end_time

    if len(dat) <= 0:
        print("len=0 无有效数据")
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x02:  # 开始测试
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
    elif cmd == 0x02:  # 测试记录
        ser_send_cmd(dev, cmd)  # # 回复夹具开始测试
        lt_ir_res = "un_test"
        if dat[0] == 0x01:
            lt_ir_res = "OK"
        elif dat[0] == 0x02:
            lt_ir_res = "NG"
        wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", get_display_res(lt_ir_res))

        if len(dat) >= 109:  # 1 + 12 * 9
            for i in range(9):
                far_val = (int(dat[1 + i * 12]) * 256 + int(dat[2 + i * 12]))
                close_val = (int(dat[3 + i * 12]) * 256 + int(dat[4 + i * 12]))
                close_min = (int(dat[5 + i * 12]) * 256 + int(dat[6 + i * 12]))
                close_max = (int(dat[7 + i * 12]) * 256 + int(dat[8 + i * 12]))
                far_min = (int(dat[9 + i * 12]) * 256 + int(dat[10 + i * 12]))
                far_max = (int(dat[11 + i * 12]) * 256 + int(dat[12 + i * 12]))

                if far_min <= far_val <= far_max:
                    far_res = "OK"
                else:
                    far_res = "NG"

                if close_min <= close_val <= close_max:
                    close_res = "OK"
                else:
                    close_res = "NG"
                if i == 0:
                    name_str = "沿墙灯"
                else:
                    name_str = f"LED{i}"
                mes_run.add_report(name=name_str+"近值", result=close_res,
                                   value=str(close_val),
                                   val_max=str(close_max),
                                   val_min=str(close_min))
                mes_run.add_report(name=name_str+"远值", result=far_res,
                                   value=str(far_val),
                                   val_max=str(far_max),
                                   val_min=str(far_min))
    elif cmd == 0x88:  # 测试结束
        test_end_time = datetime.now()
        lt_bump_res = "NG"
        if dat[0] == 0x01:    # 测试成功
            lt_bump_res = "OK"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试  PASS",
                         color=wx.GREEN)
        elif dat[0] == 0x02:  # 测试失败
            lt_bump_res = "NG"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试  NG",
                         color=wx.RED)
        elif dat[0] == 0x0A:  # 停止测试
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试停止",
                         color=wx.RED)
        elif dat[0] == 0x0E:  # 扫码异常，check sn 出错
            pass
        if dat[0] == 0x01 or dat[0] == 0x02:
            mes_run.send_report(test_start_time, test_end_time, check_sn_str, lt_bump_res)


# 回充座测试
def docking_station_mode(dev, cmd, dat):
    global check_sn_enable
    global test_start_time
    global test_end_time
    global cliff_sn_dict
    global left_res
    global right_res
    global check_sn_str

    if len(dat) <= 0:
        print("len=0 无有效数据")
        return
    if type(cmd) is str:
        if cmd == "sn":  # 收到SN信息
            check_sn_str = dat[0]
            match_res = encode_rules.match_sn_encoding_rules(dev=load_cfg.dev, sn=str(check_sn_str))
            # str_list_hex = [hex(byte) for byte in check_sn_str.encode('utf-8')]
            str_list = [int(byte) for byte in check_sn_str.encode('utf-8')]
            # print(check_sn_str, str(str_list), str_list_hex)
            # print(str_list)
            if match_res:  # 条码规则匹配成功
                # mes 过站
                res = True
                res = mes_run.check_sn_is_ok(check_sn_str)
                # print(str_list)
                if res:
                    ser_send_data(dev=int(load_cfg.dev), cmd=0x57, data=str_list)
                    # ser_send_cmd(int(load_cfg.dev), 0x57)  # 回复夹具开始测试
                else:
                    # ser_send_cmd(int(load_cfg.dev), 0x58)  # 回复夹具扫码失败
                    ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)
            else:
                ser_send_data(dev=int(load_cfg.dev), cmd=0x58, data=str_list)  # 回复夹具扫码失败
                wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                             first="请输入条码:" + str(check_sn_str),
                             third="编码规则不通过，请查")
            check_sn_enable = False
    elif cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            start_sn_collect(first="请输入SN:")

        elif dat[0] == 0x02:  # 开始测试
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item,
                         num=2, text="开始测试", color=wx.RED)
    elif cmd == 0x02:  # 测试记录
        ser_send_cmd(dev, cmd)  # # 回复夹具开始测试
        if len(dat) < 4:
            print("回充座收到测试结果长度不对")
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试记录数据长度异常")
            return
        res = "OK"


# 积尘桶或集尘桶PCB测试
def dust_collector_mode(dev, cmd, dat):
    global test_start_time
    global test_end_time
    global check_sn_enable
    if len(dat) <= 0:
        print("len=0 无有效数据")
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x01:
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
        elif dat[0] == 0x02:
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
        elif dat[0] == 0x52:
            print('请拔出尘袋')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请拔出尘袋")
        elif dat[0] == 0x51:
            print('请插入尘袋')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请插入尘袋")
        elif dat[0] == 0x05:
            print('请观察灯效是否正常')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请观察灯效是否正常")
        else:
            print('其他开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="继续测试")
    elif cmd == 0x68:
        print('所有阀值：' + str(dat))
        # 阈值 充电电流
        dust_th.cc_max = (int(dat[0]) * 256 + int(dat[1]))
        dust_th.cc_min = (int(dat[2]) * 256 + int(dat[3]))
        # 阈值 ac 过载频率
        dust_th.ac_lv_max = int(dat[4])
        dust_th.ac_lv_min = int(dat[5])
        # 阈值 外接气压计 上线下线；吸力值
        dust_th.out_barometer_max = (int(dat[6]) * 256 + int(dat[7]))
        dust_th.out_barometer_min = (int(dat[8]) * 256 + int(dat[9]))
        # 阈值 气压值小板 上线下线；检测尘满
        dust_th.barometer_max = (int(dat[10]) * 256 + int(dat[11]))
        dust_th.barometer_min = (int(dat[12]) * 256 + int(dat[13]))
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码", color=wx.RED)
    elif cmd == 0x01:  # 命令帧：红外收发和集尘宝版本号
        print("红外收发码:" + str(dat))
        infrared_code = int(dat[0])

        dev_ver = format(int(dat[1]), '03d') + '.'
        dev_ver += (format(int(dat[2]), '03d') + '.' + format(int(dat[3]), '03d'))
        wx.CallAfter(MainFrame.main_frame.up_ver_ui, dev_ver)
        if dev_ver == load_cfg.mcu_ver:
            ver_res = "OK"
        else:
            ver_res = "NG"
        mes_run.add_report(name="mcu软件版本", result=ver_res,
                           value=dev_ver,
                           val_max=load_cfg.mcu_ver,
                           val_min=load_cfg.mcu_ver)
        res = ""
        display_str = "pass"
        if infrared_code == 1:
            res = "OK"
            display_str = "pass"
        elif infrared_code == 2:
            res = "NG"
            display_str = "fail"

        mes_run.add_report(name="红外通讯，收发码", result=res)
        wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)

        # 版本号异常，不进行后续测试
        if res == "OK" and dev_ver != load_cfg.mcu_ver:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试失败：软件版本号不匹配", color=wx.RED)
            return
        ser_send_cmd(dev, cmd)  # 回复夹具开始测试
    elif cmd == 0x02:  # 命令帧：回充红外灯，x 右 左 近卫
        print('四路红外灯发送测试' + str(dat))
        ser_send_cmd(dev, cmd)  # 回复夹具开始测试
        ir1 = int(dat[0])
        ir2 = int(dat[1])
        ir3 = int(dat[2])
        ir4 = int(dat[3])

        res_str_value = ""
        if ir2 == 1 and ir3 == 1 and ir4 == 1:
            res = "OK"
        else:
            res = "NG"
        if ir2 == 1:
            ir2_res = "OK"
            res_str_value += "右红外-OK "
        else:
            ir2_res = "NG"
            res_str_value += "右红外-NG "
        if ir3 == 1:
            ir3_res = "OK"
            res_str_value += "左红外-OK "
        else:
            ir3_res = "NG"
            res_str_value += "左红外-NG "
        if ir4 == 1:
            ir4_res = "OK"
            res_str_value += "近卫红外-OK "
        else:
            ir4_res = "NG"
            res_str_value += "近卫红外-NG "
        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "right_ir", get_display_res(ir1))
        wx.CallAfter(MainFrame.main_frame.up_test_ui, "right_ir", get_display_res(ir2_res))
        wx.CallAfter(MainFrame.main_frame.up_test_ui, "left_ir", get_display_res(ir3_res))
        wx.CallAfter(MainFrame.main_frame.up_test_ui, "guard_light", get_display_res(ir4_res))

        mes_run.add_report(name="回充红外发码测试", result=res, value=res_str_value)

    elif cmd == 0x03:  # 尘袋在位测试
        print('尘袋在位测试' + str(dat))
        res_str = "NG"
        ser_send_cmd(dev, cmd)  # 回复夹具开始测试
        if dat[0] == 0x01:  # 尘袋在位，用于显示
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="尘袋在位")
        elif dat[0] == 0x02:  # 尘袋不在位，用于显示
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="尘袋不在位")
        elif dat[0] == 0x81:  # 尘袋测试通过
            res_str = "OK"
        elif dat[0] == 0x82:  # 尘袋测试不通过
            res_str = "NG"
        if dat[0] == 0x81 or dat[0] == 0x82:
            wx.CallAfter(MainFrame.main_frame.up_test_ui, name="bag_install",
                         result=get_display_res(res_str))
            mes_run.add_report(name="回充红外发码测试", result=res_str)

    elif cmd == 0x04:
        print('负载测试' + str(dat))
        ser_send_cmd(dev, cmd)  # 回复夹具开始测试
        cur_pass = int(dat[0])
        res_cur_pass = "NG"
        if cur_pass == 1:
            res_cur_pass = "OK"
        elif cur_pass == 2:
            res_cur_pass = "NG"
        wx.CallAfter(MainFrame.main_frame.up_test_ui, name="load_current",
                     result=get_display_res(res_cur_pass))
        mes_run.add_report(name="负载电流是否通过", result=res_cur_pass)
    elif cmd == 0x05:
        print('灯显测试')
        ser_send_cmd(dev, cmd)  # 回复夹具开始测试
        if dat[0] == 0x51:
            led_pass = "OK"
            led_display = "pass"
        elif dat[0] == 0x52:
            led_pass = "NG"
            led_display = "fail"
        else:
            led_pass = "untested"
            led_display = "untested"
        if dev == 0x06:  # PCB
            led_value = f"LED1 通过次数{int(dat[1])}，LED2 通过次数{int(dat[2])}"
            min_value = str(int(dat[4]))
            max_value = "不限"
        else:
            led_value = f"LED白 通过次数{int(dat[1])}，LED红 通过次数{int(dat[2])}, LED黑 通过次数{int(dat[3])}"
            min_value = str(int(dat[4]))
            max_value = "不限"
        wx.CallAfter(MainFrame.main_frame.up_test_ui, name="led_display",
                     result=led_display)
        mes_run.add_report(name="LED灯显测试", result=led_pass,
                           value=led_value,
                           val_min=min_value,
                           val_max=max_value)

    elif cmd == 0x61:
        print('AC交流板的过零信号频率' + str(dat))
        ser_send_cmd(dev, 0x06)  # 回复夹具开始测试
        ac_pass = int(dat[0])
        ac_value = int(dat[1])
        ac_res = 'un_test'
        if ac_pass == 1:
            ac_res = 'OK'
        elif ac_pass == 2:
            ac_res = 'NG'
        
        wx.CallAfter(MainFrame.main_frame.up_test_ui, name="ac_check",
                     result=get_display_res(ac_res))
        mes_run.add_report(name="AC交流板的过零信号频率",
                           result=ac_res,
                           value=str(ac_value),
                           val_max=str(dust_th.ac_lv_max),
                           val_min=str(dust_th.ac_lv_min))
    elif cmd == 0x62:
        ser_send_cmd(dev, 0x06)  # 回复夹具
        print('外接吸力值计' + str(dat))
        res_str = 'un_test'
        out_suction = int(dat[0])
        if out_suction == 1:
            res_str = 'OK'
        elif out_suction == 2:
            res_str = 'NG'
        if dev == 0x01:
            out_suction_value = (int(dat[1]) * 256 + int(dat[2]))
        else:
            out_suction_value = "PCB人工判断 " + res_str
            dust_th.out_barometer_max = ""
            dust_th.out_barometer_min = ""
        print('外接吸力值测试值：' + str(out_suction_value))
        wx.CallAfter(MainFrame.main_frame.up_test_ui, name="suction",
                     result=get_display_res(res_str))
        mes_run.add_report(name="外接吸力计",
                           result=res_str,
                           value=str(out_suction_value),
                           val_max=str(dust_th.out_barometer_max),
                           val_min=str(dust_th.out_barometer_min))
    elif cmd == 0x63:
        ser_send_cmd(dev, 0x06)  # 回复夹具
        print('气压计小板' + str(dat))
        res_str = 'un_test'
        barometer_pass = int(dat[0])
        if barometer_pass == 1:
            res_str = 'OK'
        elif barometer_pass == 2:
            res_str = 'NG'

        barometer_value = (int(dat[1]) * 256 + int(dat[2]))
        print('气压计小板：' + str(barometer_value))
        wx.CallAfter(MainFrame.main_frame.up_test_ui, name="barometer",
                     result=get_display_res(res_str))
        mes_run.add_report(name="气压计小板",
                           result=res_str,
                           value=str(barometer_value),
                           val_max=str(dust_th.barometer_max),
                           val_min=str(dust_th.barometer_min))
    # 测试完成
    elif cmd == 0x88:
        ser_send_cmd(dev, 0x89)  # 回复夹具
        res_value = dat[0]
        res_display_str = ''
        test_end_time = datetime.now()
        print("jichentongceswanc")
        if res_value == 0x01:
            res_display_str = "测试完成  PASS"
            wx.CallAfter(MainFrame.main_frame.up_test_ui, name="led_display",
                         result="pass")
            mes_run.add_report(name="led", result="OK",)
        elif res_value == 0x00:
            res_display_str = "条码没通过  NG"
        elif res_value == 0x02:  # 需要处理，没有测试项
            res_display_str = "回充发码异常  NG"
            mes_run.add_report(name="回充发码",
                               result="NG",
                               value="NG",
                               val_max="",
                               val_min="")
        elif res_value == 0x03:
            res_display_str = "红外收发异常  NG"
        elif res_value == 0x04:
            res_display_str = "尘袋在位检测异常  NG"
        elif res_value == 0x05:
            res_display_str = "充电电流异常  NG"
        elif res_value == 0x06:
            res_display_str = "内置气压计异常  NG"
        elif res_value == 0x07:
            res_display_str = "LED灯显异常  NG"
        elif res_value == 0x08:
            res_display_str = "AC交流板的过零信号频率异常  NG"
        elif res_value == 0x09:
            res_display_str = "外部气压计异常  NG"
        elif res_value == 0x0A:
            res_display_str = "测试停止  NG"
        elif res_value == 0x0B:
            res_display_str = "没有扫码  NG"
        elif res_value == 0x0E:  # 扫码异常，check sn 出错
            pass
        else:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                         second="测试结果异常，请检测",
                         color=wx.RED)
            return
        mes_run.add_report(name="污水通路过水",
                           result="NG",
                           value="NG",
                           )
        mes_run.add_report(name="左拖布过水",
                           result="NG",
                           value="NG",
                           )
        mes_run.add_report(name="右拖布过水",
                           result="NG",
                           value="NG",
                           )
        mes_run.add_report(name="左拖布温度adc",
                           result="NG",
                           value="NG",
                           )
        mes_run.add_report(name="右拖布温度adc",
                           result="NG",
                           value="NG",
                           )
        text_color = wx.RED
        print("测试结果：" + res_display_str)
        mes_ret = False
        if res_value == 0x01:
            text_color = wx.GREEN
            mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "OK")
        elif res_value != 0x00 and res_value != 0x0A:
            mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "NG")
        if mes_ret:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                         second=res_display_str,
                         color=text_color)


def get_display_res(value):
    ret = ""
    if value == "OK":
        ret = "pass"
    elif value == "NG":
        ret = "fail"
    else:
        ret = "untested"
    return ret


def is_sn_up_enable():
    return sn_up_enable


def clear_sn_up_enable():
    global sn_up_enable
    sn_up_enable = False
    print("clean sn up enable")


def set_sn_up_enable():
    global sn_up_enable
    sn_up_enable = True
    print("set sn up enable")


def start_sn_collect(first="", second="", third="", start_sn=""):
    global sn_up_enable
    global sn_save_list

    sn_save_list = []
    dirt = {"head": first, "sn": ""}
    sn_save_list.append(dirt)
    dirt = {"head": second, "sn": ""}
    sn_save_list.append(dirt)
    dirt = {"head": third, "sn": ""}
    sn_save_list.append(dirt)
    full = False
    if start_sn != "":
        full = save_sn_to_list(sn=start_sn)

    wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                 first=sn_save_list[0]["head"] + sn_save_list[0]["sn"],
                 second=sn_save_list[1]["head"] + sn_save_list[1]["sn"],
                 third=sn_save_list[2]["head"] + sn_save_list[2]["sn"],
                 color=wx.RED)
    if full is False:
        set_sn_up_enable()


# 模拟治具，发测试命令
def send_sn_cmd():
    full = save_sn_to_list(sn="")
    sn_list = get_sn_collect_res()
    if len(sn_list) < 1 or int(load_cfg.dev) != 5:  # 暂时只处理地检治具
        return
    if full:
        sn_cmd = {
            "cmd": "sn",
            "msg": sn_list,
        }
        tool.clear_queue(rx_sn_cmd_q)
        rx_sn_cmd_q.put(sn_cmd)


# 获取收集到的SN
def get_sn_collect_res():
    global sn_save_list

    sn_list = []

    for item in sn_save_list:
        if item["head"] != "" and item["sn"] != "":
            sn = item["sn"]
            sn_list.append(sn)

    return sn_list


def clear_sn_save_list():
    """
    清除全局变量 sn_save_list 的内容。
    将 sn_save_list 重置为空列表。
    """
    global sn_save_list
    sn_save_list = []


def save_sn_to_list(sn=""):
    global sn_save_list
    is_list_full = True
    if sn != "":
        for item in sn_save_list:
            if item["head"] != "" and item["sn"] == "":
                item["sn"] = sn
                break
    for item in sn_save_list:
        if item["head"] != "" and item["sn"] == "":
            is_list_full = False
    # print(sn_save_list)
    return is_list_full


def check_sn_num():
    global sn_save_list
    global sn_up_enable

    # SN未采集完
    if sn_up_enable:
        return -1

    sn_num = 0
    for item in sn_save_list:
        if item["head"] != "" and item["sn"] != "":
            sn_num += 1

    return sn_num


def check_barcodes_match_process():
    global test_work_state
    global barcode_msg_update
    global test_error_str

    if is_sn_up_enable() is not True:
        one_sn = ""
        tow_sn = ""
        for item in sn_save_list:
            if item["head"] == "请输入条码一：":
                one_sn = item["sn"]
            elif item["head"] == "请输入条码二：":
                tow_sn = item["sn"]
        print("字符比较", one_sn, tow_sn, str(one_sn == tow_sn))
        if one_sn == tow_sn and len(one_sn) >= 4 and len(tow_sn) >= 4:
            is_in_db = sqlite_db.is_sn_in_database(one_sn, sqlite_db.conn)
            if is_in_db is False:
                sns = [one_sn]
                sqlite_db.add_sn_record(connect=sqlite_db.conn, sns=sns, name="大货SN")
                print("测试通过，SN：" + one_sn)
                text = "比较通过    PASS"
                color = wx.GREEN
                res = "PASS"
                voice.play_voice("pass")
            elif is_in_db is True:
                text = "条码已经使用:"
                color = wx.RED
                results = sqlite_db.find_record_time_by_sn(sqlite_db.conn, one_sn)
                res = "条码已经使用:" + results[1]
                if results[0] is True:
                    text += '\n' + results[1]
                voice.play_voice("sn_is_used")
                test_error_str = "SN已使用，请检查后复位测试"

            else:
                text = "数据库操作异常"
                color = wx.RED
                res = "NG 数据库异常"
                voice.play_voice("db_error")
        else:
            print("测试失败", one_sn, tow_sn)
            text = "比较失败, 请检查后复位测试"
            color = wx.RED
            res = "NG"
            voice.play_voice("NG")
            test_error_str = "SN比较失败，请检查后复位测试"
        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=3, text=text, color=color)
        file_path = MainFrame.heading_line_dict["102"] + "记录" + ".xlsx"
        title = ["日期", "测试结果", "SN1", "SN2"]
        now = datetime.now()
        # 格式化为字符串（默认格式）
        date_str = now.strftime("%Y-%m-%d %H:%M:%S")  # 输出示例: "2023-11-15"
        data = [date_str, res, one_sn, tow_sn]
        ret = excel.add_record_to_excel(file_path, title, data)
        print(ret[0], ret[1])
        if ret[0] is False:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=3, text="记录文件写入异常，"+ret[1], color=wx.RED)
        test_work_state = "idle"
        barcode_msg_update = False
        tool.clear_queue(barcode_q)


def get_res(val=0xffff, val_min=0, val_max=0):
    if val == 0xffff:
        return "un_test"
    elif val_max >= val >= val_min:
        return "OK"
    else:
        return "NG"
    
clear_water_volume = 0
duty_water_volume = 0
left_mop_water_volume = 0
right_mop_water_volume = 0
left_mop_temperature = 0
right_mop_temperature = 0

def over_water_mode(dev, cmd, dat):
    global test_start_time
    global test_end_time
    global check_sn_enable
    global clear_water_volume 
    global duty_water_volume 
    global left_mop_water_volume 
    global right_mop_water_volume 
    global left_mop_temperature 
    global right_mop_temperature 
    if len(dat) <= 0:
        print("len=0 无有效数据")
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x01:
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
        elif dat[0] == 0x02:
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
        elif dat[0] == 0x52:
            print('请拔出尘袋')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请拔出尘袋")
        elif dat[0] == 0x51:
            print('请插入尘袋')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请插入尘袋")
        elif dat[0] == 0x05:
            print('请观察灯效是否正常')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请观察灯效是否正常")
        else:
            print('其他开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="继续测试")
    elif cmd == 0x68:
        print('所有阀值：' + str(dat))
        # 阈值 充电电流
        dust_th.cc_max = (int(dat[0]) * 256 + int(dat[1]))
        dust_th.cc_min = (int(dat[2]) * 256 + int(dat[3]))
        # 阈值 ac 过载频率
        dust_th.ac_lv_max = int(dat[4])
        dust_th.ac_lv_min = int(dat[5])
        # 阈值 外接气压计 上线下线；吸力值
        dust_th.out_barometer_max = (int(dat[6]) * 256 + int(dat[7]))
        dust_th.out_barometer_min = (int(dat[8]) * 256 + int(dat[9]))
        # 阈值 气压值小板 上线下线；检测尘满
        dust_th.barometer_max = (int(dat[10]) * 256 + int(dat[11]))
        dust_th.barometer_min = (int(dat[12]) * 256 + int(dat[13]))
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码", color=wx.RED)
    elif cmd == 0x77:  # 命令帧：红外收发和集尘宝版本号
        print("过水测试过程数据:" + str(dat))
        infrared_code = int(dat[0])
        clear_water_volume = int(dat[1])<<8|int(dat[2])
        duty_water_volume = int(dat[3])<<8|int(dat[4])
        left_mop_water_volume = int(dat[5])<<8|int(dat[6])
        right_mop_water_volume = int(dat[7])<<8|int(dat[8])
        left_mop_temperature = int(dat[9])<<8|int(dat[10])
        right_mop_temperature = int(dat[11])<<8|int(dat[12])
        if clear_water_volume > clear_water_volume_max:
           clear_water_volume_max = clear_water_volume
        if clear_water_volume < clear_water_volume_min:
           clear_water_volume_min = clear_water_volume

        if duty_water_volume > duty_water_volume_max:
           duty_water_volume_max = duty_water_volume
        if duty_water_volume < duty_water_volume_min:
           duty_water_volume_min = duty_water_volume

        if left_mop_water_volume > left_mop_water_volume_max:
           left_mop_water_volume_max = left_mop_water_volume
        if left_mop_water_volume < left_mop_water_volume_min:
           left_mop_water_volume_min = left_mop_water_volume

        if right_mop_water_volume > right_mop_water_volume_max:
           right_mop_water_volume_max = right_mop_water_volume
        if right_mop_water_volume < right_mop_water_volume_min:
           right_mop_water_volume_min = right_mop_water_volume

        if left_mop_temperature > left_mop_temperature_max:
           left_mop_temperature_max = left_mop_temperature
        if left_mop_temperature < left_mop_temperature_min:
           left_mop_temperature_min = left_mop_temperature

        if right_mop_temperature > right_mop_temperature_max:
           right_mop_temperature_max = right_mop_temperature
        if right_mop_temperature < right_mop_temperature_min:
           right_mop_temperature_min = right_mop_temperature

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"

        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"
        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"
        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)
        ser_send_cmd(dev, cmd)  # 回复夹具开始测试
    # 测试完成
    elif cmd == 0x88:
        ser_send_cmd(dev, 0x89)  # 回复夹具
        res_value = dat[0]
        res_display_str = ''
        test_end_time = datetime.now()
        print("jichentongceswanc")
        if res_value == 0x01:
            res_display_str = "测试完成  PASS"
            wx.CallAfter(MainFrame.main_frame.up_test_ui, name="led_display",
                         result="pass")
            mes_run.add_report(name="led", result="OK",)
        elif res_value == 0x00:
            res_display_str = "条码没通过  NG"
        elif res_value == 0x02:  # 需要处理，没有测试项
            res_display_str = "测试结果异常，请检测"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                         second="测试结果异常，请检测",
                         color=wx.RED)
        mes_run.add_report(name="清水通路过水",
                    result="",
                    value= str(clear_water_volume),
                    )
        mes_run.add_report(name="污水通路过水",
                           result="NG",
                           value= str(duty_water_volume),
                           )
        mes_run.add_report(name="左拖布过水",
                           result="NG",
                           value= str(left_mop_water_volume),
                           )
        mes_run.add_report(name="右拖布过水",
                           result="NG",
                           value= str(right_mop_water_volume),
                           )
        mes_run.add_report(name="左拖布温度adc",
                           result="NG",
                           value= str(left_mop_temperature),
                           )
        mes_run.add_report(name="右拖布温度adc",
                           result="NG",
                           value= str(right_mop_temperature),
                           )
        text_color = wx.RED
        print("测试结果：" + res_display_str)
        mes_ret = False
        if res_value == 0x01:
            text_color = wx.GREEN
            mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "OK")
        elif res_value != 0x00 and res_value != 0x0A:
            mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "NG")
        if mes_ret:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                         second=res_display_str,
                         color=text_color)
            



def over_air_mode(dev, cmd, dat):
    global test_start_time
    global test_end_time
    global check_sn_enable
    clear_water_pressure = 0
    duty_water_pressure = 0
    mop_water_pressure = 0
    if len(dat) <= 0:
        print("len=0 无有效数据")
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x01:
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
        elif dat[0] == 0x02:
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
        elif dat[0] == 0x52:
            print('请拔出尘袋')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请拔出尘袋")
        elif dat[0] == 0x51:
            print('请插入尘袋')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请插入尘袋")
        elif dat[0] == 0x05:
            print('请观察灯效是否正常')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请观察灯效是否正常")
        else:
            print('其他开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="继续测试")
    elif cmd == 0x68:
        print('所有阀值：' + str(dat))
        # 阈值 充电电流
        dust_th.cc_max = (int(dat[0]) * 256 + int(dat[1]))
        dust_th.cc_min = (int(dat[2]) * 256 + int(dat[3]))
        # 阈值 ac 过载频率
        dust_th.ac_lv_max = int(dat[4])
        dust_th.ac_lv_min = int(dat[5])
        # 阈值 外接气压计 上线下线；吸力值
        dust_th.out_barometer_max = (int(dat[6]) * 256 + int(dat[7]))
        dust_th.out_barometer_min = (int(dat[8]) * 256 + int(dat[9]))
        # 阈值 气压值小板 上线下线；检测尘满
        dust_th.barometer_max = (int(dat[10]) * 256 + int(dat[11]))
        dust_th.barometer_min = (int(dat[12]) * 256 + int(dat[13]))
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码", color=wx.RED)
    elif cmd == 0x77:  # 命令帧：红外收发和集尘宝版本号
        print("过水测试过程数据:" + str(dat))
        infrared_code = int(dat[0])
        clear_water_pressure = int(dat[1])<<8|int(dat[2])
        duty_water_volume = int(dat[3])<<8|int(dat[4])
        mop_water_volume = int(dat[5])<<8|int(dat[6])
        if clear_water_pressure > clear_water_pressure_max:
           clear_water_pressure_max = clear_water_pressure
        if clear_water_pressure < clear_water_pressure_min:
           clear_water_pressure_min = clear_water_pressure

        if duty_water_pressure > duty_water_pressure_max:
           duty_water_pressure_max = duty_water_pressure
        if duty_water_pressure < duty_water_pressure_min:
           duty_water_pressure_min = duty_water_pressure

        if mop_water_pressure > mop_water_pressure_max:
           mop_water_pressure_max = mop_water_pressure
        if mop_water_pressure < mop_water_pressure_min:
           mop_water_pressure_min = mop_water_pressure

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"

        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"
        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"
        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)
        ser_send_cmd(dev, cmd)  # 回复夹具开始测试
    # 测试完成
    elif cmd == 0x88:
        ser_send_cmd(dev, 0x89)  # 回复夹具
        res_value = dat[0]
        res_display_str = ''
        test_end_time = datetime.now()
        print("jichentongceswanc")
        if res_value == 0x01:
            res_display_str = "测试完成  PASS"
            wx.CallAfter(MainFrame.main_frame.up_test_ui, name="led_display",
                         result="pass")
            mes_run.add_report(name="led", result="OK",)
        elif res_value == 0x00:
            res_display_str = "条码没通过  NG"
        elif res_value == 0x02:  # 需要处理，没有测试项
            res_display_str = "测试结果异常，请检测"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                         second="测试结果异常，请检测",
                         color=wx.RED)
        mes_run.add_report(name="清水通路气压",
                    result="",
                    value= str(clear_water_pressure),
                    )
        mes_run.add_report(name="污水通路气压",
                           result="NG",
                           value= str(duty_water_pressure),
                           )
        mes_run.add_report(name="拖布通路气压",
                           result="NG",
                           value= str(mop_water_pressure),
                           )
        text_color = wx.RED
        print("测试结果：" + res_display_str)
        mes_ret = False
        if res_value == 0x01:
            text_color = wx.GREEN
            mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "OK")
        elif res_value != 0x00 and res_value != 0x0A:
            mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "NG")
        if mes_ret:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                         second=res_display_str,
                         color=text_color)
        mes_run.clear_report()  # 清除mes待上传记录
        tool.clear_queue(barcode_q)  # 清空扫码枪数据
            





charge_value = 0
hot_air = 0
ir_code_left = 0
ir_code_lc = 0  # #[RV30-PROTO-77-MOD] 左中红外码
ir_code_right = 0
ir_code_rc = 0  # #[RV30-PROTO-77-MOD] 右中红外码（变量名保留）
clear_tank_install = 0
duty_tank_install = 0
dust_bug_install = 0
clean_base_install = 0
dust_collection_suction = 0
clean_water_pump_current = 0
duty_water_pump_current = 0
cleaner_pump_current = 0
electromagnetic_three_way_current = 0
clean_base_liquid_level = 0
turbidity_data = 0
dev_ver = 0
ver_res = "OK"
def hw1_bastation_finished_product_mode(dev, cmd, dat):
    global test_start_time
    global test_end_time
    global check_sn_enable
    global ver_res
    global dev_ver
    global charge_value 
    global hot_air 
    global ir_code_left 
    global ir_code_right 
    global ir_code_rc 
    global clear_tank_install 
    global duty_tank_install 
    global dust_bug_install 
    global clean_base_install 
    global dust_collection_suction 
    global clean_water_pump_current 
    global duty_water_pump_current 
    global cleaner_pump_current 
    global electromagnetic_three_way_current 
    global clean_base_liquid_level 
    global turbidity_data 
    if len(dat) <= 0:
        print("len=0 无有效数据")
        return

    if cmd == 0x66:  # 命令帧：夹具上传开始测试
        ser_send_cmd(dev, 0x67)  # # 回复夹具开始测试
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()  # 清除mes待上传记录
            tool.clear_queue(barcode_q)  # 清空扫码枪数据
            check_sn_enable = True  # 使能SN号过站检测
            print('扫描枪扫描二维码')
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
        elif dat[0] == 0x01:
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
        elif dat[0] == 0x02:
            print('开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
        elif dat[0] == 0x52:
            print('请拔出尘袋')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请拔出尘袋")
        elif dat[0] == 0x51:
            print('请插入尘袋')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请插入尘袋")
        elif dat[0] == 0x05:
            print('请观察灯效是否正常')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请观察灯效是否正常")
        else:
            print('其他开始测试')
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="继续测试")
    elif cmd == 0x68:
        print('所有阀值：' + str(dat))
        # 阈值 充电电流
        dust_th.cc_max = (int(dat[0]) * 256 + int(dat[1]))
        dust_th.cc_min = (int(dat[2]) * 256 + int(dat[3]))
        # 阈值 ac 过载频率
        dust_th.ac_lv_max = int(dat[4])
        dust_th.ac_lv_min = int(dat[5])
        # 阈值 外接气压计 上线下线；吸力值
        dust_th.out_barometer_max = (int(dat[6]) * 256 + int(dat[7]))
        dust_th.out_barometer_min = (int(dat[8]) * 256 + int(dat[9]))
        # 阈值 气压值小板 上线下线；检测尘满
        dust_th.barometer_max = (int(dat[10]) * 256 + int(dat[11]))
        dust_th.barometer_min = (int(dat[12]) * 256 + int(dat[13]))
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码", color=wx.RED)
    elif cmd == 0x77:  # 命令帧：红外收发和集尘宝版本号
        print("基站成品测试过程数据:" + str(dat))
        infrared_code = int(dat[0])
        charge_value = int(dat[1])<<8|int(dat[2])
        hot_air = int(dat[3])<<8|int(dat[4])
        ir_code_left = int(dat[5])
        ir_code_right = int(dat[6])
        ir_code_rc = int(dat[7])
        clear_tank_install = int(dat[8])
        duty_tank_install = int(dat[9])
        dust_bug_install = int(dat[10])
        clean_base_install = int(dat[11])
        dust_collection_suction = int(dat[18])<<8|int(dat[19])
        clean_water_pump_current = int(dat[21])<<8|int(dat[21])
        duty_water_pump_current =int(dat[23])<<8|int(dat[24])
        cleaner_pump_current = int(dat[31])<<8|int(dat[32])
        electromagnetic_three_way_current = int(dat[27])<<8|int(dat[28])
        clean_base_liquid_level = int(dat[25])<<8|int(dat[26])
        turbidity_data = int(dat[33])<<8|int(dat[34])

        dev_ver = format(int(dat[1]), '03d') + '.'
        dev_ver += (format(int(dat[2]), '03d') + '.' + format(int(dat[3]), '03d'))
        wx.CallAfter(MainFrame.main_frame.up_ver_ui, dev_ver)
        if dev_ver == load_cfg.mcu_ver:
            ver_res = "OK"
        else:
            ver_res = "NG"
        res = ""
        display_str = "pass"
        if infrared_code == 1:
            res = "OK"
            display_str = "pass"
        elif infrared_code == 2:
            res = "NG"
            display_str = "fail"
        # 版本号异常，不进行后续测试
        if res == "OK" and dev_ver != load_cfg.mcu_ver:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="测试失败：软件版本号不匹配", color=wx.RED)
        # if clear_water_pressure > clear_water_pressure_max:
        #    clear_water_pressure_max = clear_water_pressure
        # if clear_water_pressure < clear_water_pressure_min:
        #    clear_water_pressure_min = clear_water_pressure

        # if duty_water_pressure > duty_water_pressure_max:
        #    duty_water_pressure_max = duty_water_pressure
        # if duty_water_pressure < duty_water_pressure_min:
        #    duty_water_pressure_min = duty_water_pressure

        # if mop_water_pressure > mop_water_pressure_max:
        #    mop_water_pressure_max = mop_water_pressure
        # if mop_water_pressure < mop_water_pressure_min:
        #    mop_water_pressure_min = mop_water_pressure

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"

        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"
        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)

        # display_str = "pass"
        # if infrared_code == 1:
        #     res = "OK"
        #     display_str = "pass"
        # elif infrared_code == 2:
        #     res = "NG"
        #     display_str = "fail"
        # wx.CallAfter(MainFrame.main_frame.up_test_ui, "ir_rx", display_str)
        ser_send_cmd(dev, cmd)  # 回复夹具开始测试
    # 测试完成
    elif cmd == 0x88:
        ser_send_cmd(dev, 0x89)  # 回复夹具
        res_value = dat[0]
        res_display_str = ''
        test_end_time = datetime.now()
        print("jichentongceswanc")
        if res_value == 0x01:
            res_display_str = "测试完成  PASS"
            wx.CallAfter(MainFrame.main_frame.up_test_ui, name="led_display",
                         result="pass")
            mes_run.add_report(name="led", result="OK",)
        elif res_value == 0x00:
            res_display_str = "条码没通过  NG"
        elif res_value == 0x02:  # 需要处理，没有测试项
            res_display_str = "测试结果异常，请检测"
            wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                         second="测试结果异常，请检测",
                         color=wx.RED)
        mes_run.add_report(name="mcu软件版本", result=ver_res,
                value=dev_ver,
                val_max=load_cfg.mcu_ver,
                val_min=load_cfg.mcu_ver)
        mes_run.add_report(name="充电电流",
                    result="",
                    value= str(charge_value),
                    )
        mes_run.add_report(name="热风",
                           result="NG",
                           value= str(hot_air),
                           )
        mes_run.add_report(name="左回充码",
                           result="NG",
                           value= str(ir_code_left),
                           )
        mes_run.add_report(name="右回充码",
                    result="",
                    value= str(ir_code_right),
                    )
        mes_run.add_report(name="近卫回充码",
                           result="NG",
                           value= str(ir_code_rc),
                           )
        mes_run.add_report(name="清水箱在位",
                           result="NG",
                           value= str(clear_tank_install),
                           )
        mes_run.add_report(name="污水箱在位",
                    result="",
                    value= str(duty_tank_install),
                    )
        mes_run.add_report(name="尘袋在位",
                           result="NG",
                           value= str(dust_bug_install),
                           )
        mes_run.add_report(name="清洁底座在位",
                           result="NG",
                           value= str(clean_base_install),
                           )
        mes_run.add_report(name="集尘吸力",
                           result="NG",
                           value= str(dust_collection_suction),
                           )
        mes_run.add_report(name="清水泵电流",
                           result="NG",
                           value= str(clean_water_pump_current),
                           )
        mes_run.add_report(name="污水泵电流",
                    result="",
                    value= str(duty_water_pump_current),
                    )
        mes_run.add_report(name="清洁泵电流",
                           result="NG",
                           value= str(cleaner_pump_current),
                           )
        mes_run.add_report(name="电磁三通电流",
                           result="NG",
                           value= str(electromagnetic_three_way_current),
                           )
        mes_run.add_report(name="清洁底座液位",
                    result="",
                    value= str(clean_base_liquid_level),
                    )
        mes_run.add_report(name="浊度数据",
                           result="NG",
                           value= str(turbidity_data),
                           )
        text_color = wx.RED
        print("测试结果：" + res_display_str)
        mes_ret = False
        if res_value == 0x01:
            text_color = wx.GREEN
            mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "OK")
        elif res_value != 0x00 and res_value != 0x0A:
            mes_ret = mes_run.send_report(test_start_time, test_end_time, check_sn_str, "NG")
        if mes_ret:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                         second=res_display_str,
                         color=text_color)
        clear_sn_save_list()


# #[RV30-PROTO] RV30 基站成品(device_type=50)：0x66 不发 0x67；门闸 0x57/0x58；0x77 无应答；异常 0x89 0x03；0x88 综合判定 MES
def RV30_finished_product_mode(dev, cmd, dat):
    # #[RV30-PROTO] 调优入口：本函数 + rv30_proto_* + config.yaml rv30_* 键
    global test_start_time
    global test_end_time
    global check_sn_enable
    global ver_res
    global dev_ver
    global charge_value
    global ir_code_left
    global ir_code_lc
    global ir_code_right
    global ir_code_rc
    global dust_bug_install
    global dust_collection_suction
    global rv30_session_state
    global rv30_last_step
    global rv30_max_step
    global rv30_89_mes_done
    global rv30_realtime_ng
    global rv30_last_p  # [up_test_ui_WBH]
    global rv30_last_dust_notify  # [RV30-尘袋步骤3-WBH]
    if len(dat) <= 0:
        print("len=0 无有效数据")
        return

    if cmd == 0x66:
        # #[RV30-PROTO] 开始测试：禁止 ser_send_cmd(0x67)，仅等扫码后 0x57/0x58
        if dat[0] == 0x00:
            test_start_time = datetime.now()
            mes_run.clear_report()
            tool.clear_queue(barcode_q)
            check_sn_enable = True
            rv30_last_step = -1
            rv30_max_step = 0
            rv30_89_mes_done = False
            rv30_realtime_ng = False
            rv30_last_dust_notify = -1  # [RV30-尘袋步骤3-WBH]
            rv30_session_state = RV30_SESS_WAIT_SN
            print("RV30 扫描枪扫描二维码")
            wx.CallAfter(MainFrame.main_frame.reset_ui)
            wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请扫码")
    #     elif dat[0] == 0x01:
    #         wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
    #     elif dat[0] == 0x02:
    #         wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="开始测试")
    #     elif dat[0] == 0x52:
    #         wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请拔出尘袋")
    #     elif dat[0] == 0x51:
    #         wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请插入尘袋")
    #     elif dat[0] == 0x05:
    #         wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="请观察灯效是否正常")
    #     else:
    #         wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="继续测试")
    # elif cmd == 0x68:
    #     # #[RV30-PROTO-68-MOD] 阈值上传：解析后刷新 load_cfg.rv30_*，供后续 0x77 判据使用
    #     print("RV30 阈值上传 len=" + str(len(dat)) + " dat=" + str(dat))
    #     if rv30_proto_parse_68_dat(dat):
    #         wx.CallAfter(MainFrame.main_frame.up_notification_ui,
    #                      second="已加载治具阈值(0x68)", color=wx.BLUE)
    #     else:
    #         wx.CallAfter(MainFrame.main_frame.up_notification_ui,
    #                      second="0x68 阈值帧长度异常", color=wx.RED)
    elif cmd == 0x77:
        # #[RV30-PROTO-77-MOD] 实时数据：数据区 15 字节；不向治具回帧；与 config.yaml rv30_* 比对
        print("RV30 实时数据 len=" + str(len(dat)) + " dat=" + str(dat))
        if len(dat) != 15:
            print("[RV30-PROTO-77-MOD] 期望数据区 15 字节，实际:", len(dat))
        if rv30_session_state != RV30_SESS_RUNNING or rv30_89_mes_done:
            return
        p = rv30_proto_parse_77_apply_globals(dat)
        wx.CallAfter(MainFrame.main_frame.up_ver_ui, dev_ver)
        if p is not None:
            rv30_last_p = p  # [up_test_ui_WBH]
            rv30_proto_refresh_test_ui_callafter(p)  # [up_test_ui_WBH]
            st = p["step"]
            if int(st) > rv30_max_step:
                rv30_max_step = int(st)
            if st != rv30_last_step:
                # #[RV30-PROTO] 步骤变化时刷新提示（步骤表仅作参考，可改文案/条件）
                rv30_last_step = st
                wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="治具步骤：" + str(st), color=wx.BLUE)
            # [RV30-测试项分步报错-WBH] 仅当前 step 已开放项参与实时 NG
            if not rv30_proto_yaml_realtime_ok(p):
                rv30_proto_realtime_fail(dev, "yaml阈值:" + str(p))
                return
            # if ver_res != "OK":
            #     rv30_proto_realtime_fail(dev, "版本不匹配:" + str(dev_ver))
            #     return
    elif cmd == 0x88:
        # #[RV30-PROTO] 结束帧：不向治具发 0x89 应答；综合判定见 rv30_proto_finalize_88
        print("RV30 测试结束帧 dat[0]=" + str(dat[0] if dat else None))
        rv30_proto_finalize_88(dev, dat)
    else:
        print("RV30 未处理命令 cmd=" + hex(cmd))

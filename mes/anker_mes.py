import socket
import json

from test_tool import test
from ui import MainFrame
import wx
from mes import mes_run


anker_mes_ip = "127.0.0.1"
anker_mes_port = 20480
ak_robot_ret_sn = ""
ak_robot_sn = ""
ak_bat_sn = ""
ak_lt_sn = ""
station_error_flag = False  # 站点配置异常

station_check_dirt = {
    "003": "A07",  # 前撞组件
    "004": "A04",  # 前撞板（PCB）
    "005": "A05",  # 地检组件
    "006": "A14",  # 集尘桶主板（PCB）
    "010": "A10",  # 左轮组件
    "011": "A11",  # 右轮组件
    "012": "A09",  # 边刷摆臂组件
    "013": "A08",  # 中扫组件
}


# 安克码使用SN # 海能码使用MAC
# 数据发送和接收的函数
def anker_mes_send(msg_type='', sn='', mac='', res=0, start=0, end=0, report=None):
    global anker_mes_ip
    global anker_mes_port
    # 绑定SN使用
    global ak_robot_ret_sn
    global ak_robot_sn
    global ak_bat_sn
    global ak_lt_sn

    # start_time = 0  # int(parsing_data_util.anker_mes_start_time)   # int 类型，为时间戳（单位s)，
    # end_time = 0  # int(parsing_data_util.anker_mes_end_time)   # int 类型, 测试结束时间。
    result = res  # int类型 0: un test, 1: success, 2: fail, 3: error
    # message = None
    check_mac = mac  # 非安克系统码
    # CheckMac CheckSn
    # 创建一个 Python 字典
    if msg_type == "CheckSn":
        test_sn = {
            "type": "CheckSn",
            "sn": sn,
        }
        message = test_sn
    elif msg_type == "CheckMac":
        test_mac = {
            "type": "CheckMac",
            "MacAddr": mac,
        }
        message = test_mac
    elif msg_type == "CheckSnStation":
        test_sn_station = {
            "type": "CheckSnStation",  # 过站检测
            "sn": sn,                  # 安克码使用SN
            "macaddr": mac,            # 海能码使用MAC
        }
        message = test_sn_station
    elif msg_type == "TestReport":
        if mac != "":
            check_sn = ""
            check_mac = mac
        else:
            check_sn = sn
            check_mac = ""
        test_report = {
            "type": "TestReport",
            "sn_writed": 0,  # int 类型，为时间戳（单位s)，
            "start_time": start,
            "end_time": end,  # int 类型, 测试结束时间。
            "MacAddr": check_mac,
            "sn": check_sn,
            "result": result,  # int类型 0: un test, 1: success, 2: fail, 3: error
            "items": report,  # 测试记录
        }
        message = test_report
    elif msg_type == "BindExtend":
        test_bind_sn = {
            "type": "BindExtend",  # 过站检测
            "kv": {
                "Bat": ak_bat_sn,
                "Front": ak_lt_sn
            },
            "no_need_check": 0,
            "sn": ak_robot_sn
        }
        message = test_bind_sn
    else:
        print('anker mes pram error, rx cmd: ', msg_type)
        return "参数异常 anker_mes_send"

    #  test_result["items"] = [{"name": "地检测试1", "result": 2, "val": "pass", "max": "", "min": ""},
    #                        {"name": "地检测试2", "result": 2, "val": "pass", "max": "", "min": ""}]
    #  将字典转换为 JSON 字符串，确保汉字正常显示，ensure_ascii=False
    json_data = json.dumps(message, ensure_ascii=False, indent=4)  # indent 用于美化输出，缩进 4 个空格

    # 打印 JSON 数据
    print(json_data)
    # while True:

    # 创建一个TCP/IP套接字
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # 设置超时时间
        client_socket.settimeout(5)
        # 连接到服务器
        client_socket.connect((anker_mes_ip, anker_mes_port))
        print(f"Connected to {anker_mes_ip}:{anker_mes_port}")

        # 发送数据
        print(f"Sending: {json_data}")
        client_socket.sendall(json_data.encode('utf-8'))

        # 接收数据
        data = client_socket.recv(1024)
        print(data.decode('utf-8'))
        dat = json.loads(data.decode('utf-8'))
        print(type(dat))
        print(f"Received: {data.decode()}")
        print('res', dat.get("res"), type(dat.get("res")))

        if dat.get("res"):  # bool
            res_sn = dat.get("sn", "")
            if "need_ret_sn" == ak_robot_ret_sn:
                ak_robot_ret_sn = res_sn
                print("get sn :" + ak_robot_ret_sn)
                print(dat.get("sn", ""))
            if msg_type == "CheckMac":
                station_error_check(res_sn)
            return "OK"
        else:
            if "need_ret_sn" == ak_robot_ret_sn:
                ak_robot_ret_sn = ""
            return dat.get("reason")
    except socket.timeout:
        print("连接或接收数据超时！")
        return "连接或接收数据超时！"
    except ConnectionRefusedError:
        print("连接被拒绝，服务器可能未启动或端口错误！")
        return "连接被拒绝，服务器可能未启动或端口错误！"
    except socket.gaierror:
        print("地址解析错误，请检查主机名或IP地址！")
        return "地址解析错误，请检查主机名或IP地址！"
    except socket.error as e:
        print(f"Socket error: {e}")
        return f"Socket error: {e}"
    except Exception as e:  # 捕获所有异常
        print(f"Other exception: {e}")
        return f"Other exception: {e}"
    finally:
        # 关闭套接字
        print("Closing socket")
        client_socket.close()


# 组装测试结果 //result  int类型 0:no test,1:skip,2:success,3:fail
def anker_mes_get_result_item(name="", result=0, value="", val_max="", val_min=""):

    ret_dat = {
        "name": name,
        "result": result,
        "val": value,
        "max": val_max,
        "min": val_min
    }
    return ret_dat


# dev 测试设备类型，sn SN号，test_dev 治具名称或编号
def check_sn_is_ok(sn=""):
    print("anker check sn: " + sn)
    if (int(test.load_cfg.dev) == 1 or int(test.load_cfg.dev) == 101 or
            int(test.load_cfg.dev) == 104 or int(test.load_cfg.dev) == 7):  # 集尘桶测试治具，打高压
        ret = anker_mes_send(msg_type="CheckSn", sn=sn)
    else:
        ret = anker_mes_send(msg_type="CheckMac", mac=sn)
    if ret == "OK":
        return True
    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, third="安克mes，"+ret, color=wx.RED)
        return False


# dev 测试设备类型，sn SN号，test_dev 治具名称或编号
def check_station_is_ok(sn=""):
    print("anker check station: " + sn)
    ret = anker_mes_send(msg_type="CheckSnStation", mac=sn)
    if ret == "OK":
        return True
    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="安克 "+str(ret), color=wx.RED)
        return False


def anker_send_report(start_time, end_time, ck_sn="", result="un_test"):
    # result  0:un test,1:success,2:fail,3:error
    print("anker_send_report")
    dev = int(test.load_cfg.dev)
    if result == "OK":
        res = 1
    elif result == "NG":
        res = 2
    else:  # result == "un_test":
        res = 0
    if dev == 1 or dev == 7 or dev == 101 or dev == 104:
        ck_mac = ""
    else:
        ck_mac = ck_sn
        ck_sn = ""
    ret = anker_mes_send(msg_type="TestReport",
                         sn=ck_sn,
                         mac=ck_mac, res=res,
                         start=int(start_time.timestamp()), end=int(end_time.timestamp()),
                         report=mes_run.anker_report)
    if ret == "OK":
        return True
    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="安克 " + ret, color=wx.RED)
        return False


def anker_bind_robot_bat_lt_sn(robot_sn, bat_sn, lt_sn):
    global ak_robot_sn
    global ak_bat_sn
    global ak_lt_sn

    ak_robot_sn = robot_sn
    ak_bat_sn = bat_sn
    ak_lt_sn = lt_sn
    print("anker_bind_robot_bat_lt_sn")
    ret = anker_mes_send(msg_type="BindExtend")
    if ret == "OK":
        return True
    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second=str(ret) + ret, color=wx.RED)
        return False


def station_error_check(res_sn):
    global station_error_flag
    dev = test.load_cfg.dev
    check_sn = station_check_dirt.get(dev, "")
    if check_sn != "":
        if res_sn[3:6] != check_sn:
            station_error_flag = True
            print("基站配置异常", check_sn, res_sn)


def is_station_cfg_error():
    return station_error_flag


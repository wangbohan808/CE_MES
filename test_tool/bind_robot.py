#  绑定主机、电池和前撞测试
import time
import wx
from ui import MainFrame
from myserial import test_serial
from tool_box import tool
from test_tool import test
from mes import mes_run
from datetime import datetime
from mes import celink_mes
from mes import anker_mes
from test_tool import encode_rules

robot_anker_sn = ""
robot_sn = ""
bat_sn = ""
lt_bump_sn = ""
start_time_flag = False


def bind_sn_process():

    global robot_sn
    global bat_sn
    global lt_bump_sn
    global robot_anker_sn

    robot_sn = ""
    bat_sn = ""
    lt_bump_sn = ""
    print("开始测试")
    sn_list = test.get_sn_collect_res()
    # 等待SN输入
    if test.is_sn_up_enable():
        return
    if len(sn_list) != 3:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, first="获取条码数量异常：", color=wx.RED)
        test.test_work_state = "idle"
        return

    robot_sn = sn_list[0]
    bat_sn = sn_list[1]
    lt_bump_sn = sn_list[2]

    wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                 first="主机条码：" + robot_sn,
                 second="电池条码：" + bat_sn,
                 third="前撞条码：" + lt_bump_sn,
                 color=wx.RED)
    ret = check_robot_bat_lt_sn_rules_is_ok(robot_sn, bat_sn, lt_bump_sn)
    if ret is not True:
        test.test_work_state = "idle"
        return

    res = True
    if test.load_cfg.mes == "1" or test.load_cfg.mes == "2":
        res = celink_mes.celink_bind_robot_bat_lt_sn(robot_sn, bat_sn, lt_bump_sn)

    if res is not True:
        test.test_work_state = "idle"
        return
    if test.load_cfg.mes == "1" or test.load_cfg.mes == "3":
        res = anker_mes.anker_bind_robot_bat_lt_sn(robot_anker_sn, bat_sn, lt_bump_sn)
        end_time = datetime.now()
        if res:
            report_res = anker_mes.anker_send_report(test.test_start_time, end_time, ck_sn=robot_sn, result="OK")
            if report_res:
                wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                             second="测试完成    PASS",
                             color=wx.GREEN)

    test.test_work_state = "idle"


def check_state_change(cur_state="running"):
    return cur_state != test.test_work_state


def check_state_change_or_barcode_change(cur_state="running"):
    if cur_state != test.test_work_state or test.barcode_q.empty() is not True:
        return True
    else:
        return False


def check_robot_bat_lt_sn_rules_is_ok(rob_sn="", rob_bat_sn="", rob_lt_bump_sn=""):

    robot_match_res = encode_rules.match_sn_encoding_rules(dev="robot", sn=rob_sn)
    bat_match_res = encode_rules.match_sn_encoding_rules(dev="bat", sn=rob_bat_sn)
    front_match_res = encode_rules.match_sn_encoding_rules(dev="front", sn=rob_lt_bump_sn)

    if robot_match_res and bat_match_res and front_match_res:
        return True
    else:
        print(robot_match_res, bat_match_res, front_match_res)
        robot_res = " 符合规范：" if robot_match_res else " 不合规范："
        robot_color = wx.GREEN if robot_match_res else wx.RED
        bat_res = " 符合规范：" if bat_match_res else " 不合规范："
        bat_color = wx.GREEN if bat_match_res else wx.RED
        front_res = " 符合规范：" if front_match_res else " 不合规范："
        front_color = wx.GREEN if front_match_res else wx.RED

        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item,
                     num=1,
                     text="主机编码检测" + robot_res + rob_sn,
                     color=robot_color)
        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item,
                     num=2,
                     text="电池编码检测" + bat_res + rob_bat_sn,
                     color=bat_color)
        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item,
                     num=3,
                     text="前撞编码检测" + front_res + rob_lt_bump_sn,
                     color=front_color)
        return False

    # 检测主机码
    celink_robot_ret = True
    if test.load_cfg.mes == "001" or test.load_cfg.mes == "002":
        celink_robot_ret = celink_mes.check_sn_is_ok(robot_sn)
    anker_mes.ak_robot_ret_sn = "need_ret_sn"
    anker_robot_ret = True
    if test.load_cfg.mes == "001" or test.load_cfg.mes == "003":
        anker_robot_ret = anker_mes.check_sn_is_ok(robot_sn)
    robot_anker_sn = anker_mes.ak_robot_ret_sn
    anker_mes.ak_robot_ret_sn = ""

    anker_bat_ret = True
    if encode_rules.check_barcode(bat_sn, "bat"):
        if test.load_cfg.mes == "001" or test.load_cfg.mes == "003":
            anker_bat_ret = anker_mes.check_station_is_ok(bat_sn)
    else:
        anker_bat_ret = False

    anker_lt_bump_ret = True
    if encode_rules.check_barcode(lt_bump_sn, "front"):
        if test.load_cfg.mes == "001" or test.load_cfg.mes == "003":
            anker_lt_bump_ret = anker_mes.check_station_is_ok(lt_bump_sn)
    else:
        anker_lt_bump_ret = False

    mes_run.anker_report = []
    if celink_robot_ret and anker_robot_ret:
        robot_sn_check_res = "主机过站：" + robot_sn + "    PASS"
        rep = anker_mes.anker_mes_get_result_item(name="主机过站", result=2, value=str(robot_sn))
        mes_run.anker_report.append(rep)

    else:
        robot_sn_check_res = "主机过站：" + robot_sn + "    NG"
        rep = anker_mes.anker_mes_get_result_item(name="主机过站", result=3, value=str(robot_sn))
        mes_run.anker_report.append(rep)

    if anker_bat_ret:
        bat_sn_check_res = "电池过站：" + bat_sn + "    PASS"
        rep = anker_mes.anker_mes_get_result_item(name="电池过站", result=2, value=str(bat_sn))
        mes_run.anker_report.append(rep)
    else:
        bat_sn_check_res = "电池过站：" + bat_sn + "    NG"
        rep = anker_mes.anker_mes_get_result_item(name="电池过站", result=3, value=str(bat_sn))
        mes_run.anker_report.append(rep)

    if anker_lt_bump_ret:
        lt_bump_sn_check_res = "前撞过站：" + lt_bump_sn + "    PASS"
        rep = anker_mes.anker_mes_get_result_item(name="前撞过站", result=2, value=str(lt_bump_sn))
        mes_run.anker_report.append(rep)
    else:
        lt_bump_sn_check_res = "前撞过站：" + lt_bump_sn + "    NG"
        rep = anker_mes.anker_mes_get_result_item(name="前撞过站", result=3, value=str(lt_bump_sn))
        mes_run.anker_report.append(rep)

    wx.CallAfter(MainFrame.main_frame.up_notification_ui,
                 first=robot_sn_check_res,
                 second=bat_sn_check_res,
                 third=lt_bump_sn_check_res,
                 color=wx.RED)

    if celink_robot_ret and anker_robot_ret and anker_bat_ret and anker_lt_bump_ret:
        return True
    else:
        return False



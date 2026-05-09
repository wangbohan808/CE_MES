from ui import MainFrame
from test_tool import test
from database import sqlite_db
from datetime import datetime
import wx
from test_tool import excel
from tool_box import tool
from test_tool import voice

parts_continuous_counts = 0
parts_total_counts = 0


def check_barcodes_of_parts_box_process():
    global parts_total_counts
    global parts_continuous_counts
    sn_head = test.load_cfg.parts_sn_head
    if len(sn_head) != 7:
        print("head:")
        print(sn_head)
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, third="SN固定码,在配置文件中\n不是7位字符", color=wx.RED)
        return
    wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=2,
                 text="计数：" + str(parts_continuous_counts), color=wx.RED)
    if test.is_sn_up_enable() is not True:

        sn = ""
        for item in test.sn_save_list:
            if item["head"] == "请输入条码：":
                sn = item["sn"]
                break
        print("配件纸盒SN", str(sn))
        sn_len = len(sn)
        if (sn_len == 10 or sn_len == 13) and sn_head == sn[:7]:
            is_in_db = sqlite_db.is_sn_in_database(sn, sqlite_db.conn)
            if is_in_db is False:
                sns = [sn]
                if sn_len == 10:
                    parts_continuous_counts = 0
                    name = "纸箱SN"
                else:
                    parts_continuous_counts += 1
                    parts_total_counts += 1
                    wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=2,
                                 text="连续扫码计数：" + str(parts_continuous_counts), color=wx.RED)
                    wx.CallAfter(MainFrame.main_frame.up_ver_ui, ver_str=str(parts_total_counts))
                    name = "配件SN"
                sqlite_db.add_sn_record(connect=sqlite_db.conn, sns=sns, name=name)
                print("测试通过，SN：" + sn)
                text = "检测通过    PASS"
                color = wx.GREEN
                res = "PASS"
                voice.play_voice("pass")
            elif is_in_db is True:
                text = "条码已经使用:"
                color = wx.RED
                results = sqlite_db.find_record_time_by_sn(sqlite_db.conn, sn)
                res = "条码已经使用:" + results[1]
                if results[0] is True:
                    text += '\n' + results[1]
                voice.play_voice("sn_is_used")
                test.test_error_str = "SN已使用，请检查后复位测试"

            else:
                text = "数据库操作异常"
                color = wx.RED
                res = "NG 数据库异常"
                voice.play_voice("db_error")
        else:
            print("测试失败", sn)
            text = "SN检测不通过, 请检查后复位测试"
            color = wx.RED
            res = "NG"
            voice.play_voice("NG")
            test.test_error_str = "SN检测不通过，请检查后复位测试"
        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=3, text=text, color=color)
        file_path = MainFrame.heading_line_dict["103"] + "记录" + ".xlsx"
        title = ["日期", "批次", "SN", "测试结果"]
        now = datetime.now()
        # 格式化为字符串（默认格式）
        date_str = now.strftime("%Y-%m-%d %H:%M:%S")  # 输出示例: "2023-11-15"
        data = [date_str, sn_head, sn, res]
        ret = excel.add_record_to_excel(file_path, title, data)
        print(ret[0], ret[1])
        if ret[0] is False:
            wx.CallAfter(MainFrame.main_frame.up_notification_ui_item, num=3, text="记录文件写入异常\n"+ret[1], color=wx.RED)
        test.test_work_state = "idle"
        test.barcode_msg_update = False
        tool.clear_queue(test.barcode_q)



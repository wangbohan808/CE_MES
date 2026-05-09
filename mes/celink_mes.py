import json
import requests
import wx
from ui import MainFrame
from test_tool import test
from mes import mes_run

# 定义请求的URL
url = 'http://192.168.7.90/CelinkHNSDJWCFService/OrBitWebAPI.ashx'


# 海能mes系统，用户码，工站码
station_sn_code = {
    "001": "AKJCTGNCS",    # 集尘桶成品功能测试
    "003": "AKQZGNCS",     # 前撞组件
    # "005": "AKDJGNCS",   # 地检组件
    "007": "AKZJZJJTDLCS",  # 静态电流
    "100": "AKBDDCHQZZJ",  # 绑定主机、前撞、电池
    "101": "AKJCTDGY",     # 整机耐压测试（打高压）
    # --- WEIGH-106-BEGIN: 海能过站码（TODO：待 MES 正式 UserParameter 替换占位）---
    "106": "HNBZCZ",
    # --- WEIGH-106-END ---

    #[FX_TODO]
    "50":"HNXJCTQGNCS"
}

# 海能mes系统，用户码，工站码
station_report_code = {
    "001": "AKJCTGNCS",    # 集尘桶成品功能测试
    "003": "AKQZGNCS",     # 前撞组件
    "004": "AKQZBGNCS",    # 前撞PCBA
    "005": "AKDJGNCS",     # 地检组件
    "006": "AKJCTZBGNCS",  # 集尘桶PCBA
    "105": "HNJZNYCS",  # 耐压测试
    "015": "HNJZQMXCS",  # 气密性测试
    "016": "HNJZGSCS",  # 过水测试
    "017": "HNJZQGNCS",  # 全功能测试
    "018": "HNWSXQMXCS",  # 污水箱气密性测试
    "100": "AKBDDCHQZZJ",  # 绑定主机、前撞、电池
    "101": "AKJCTDGY",     # 整机耐压测试（打高压）
    # --- WEIGH-106-BEGIN: 海能上报码（TODO：待 MES 正式 UserParameter 替换占位）---
    "106": "HNBZCZ",
    # --- WEIGH-106-END ---

    #[FX_TODO]
    "50":"HNXJCTQGNCS"
}


# ce_link mes 通讯
def celink_mes_communication(mes_data):
    # 获取返回的JSON数据
    print("开始发送")
    try:
        response = requests.post(url, data=mes_data, timeout=5)
        print(f"状态码: {response.status_code}")
        print("Content-Type:", response.headers.get('Content-Type'))
        # 检查响应状态码
        if response.status_code == 200:
            try:
                response_data = response.json()
                print(response_data)
                result_code = response_data.get('ResultCode')
                result_message = response_data.get('ResultMessage')

                if result_code == "OK":
                    print("请求成功！返回信息：", result_message)
                    return True, "OK"
                else:
                    print("请求失败！返回信息：", result_message)
                    return False, result_message

            except ValueError:
                print("响应内容不是有效的JSON格式！")
                print("响应内容为：", response.text)
                return False, "发送数据非有效JSON格式"
        else:
            print(f"请求失败，状态码：{response.status_code}")
            print("响应内容为：", response.text)
            return False, response.text

    except requests.exceptions.Timeout:
        print("请求超时！")
        return False, "请求超时"
    except Exception as e:
        print("发生错误：", str(e))
        return False, "通讯错误：" + str(e)


test_item_description_dirt = {

}


# 组装测试结果
def celink_mes_get_result_item(name="", value="", description="", result=False):
    # description = test_item_description_dirt.get(name, "")
    if result:
        result_str = "OK"
    else:
        result_str = "NG"

    ret_dirt = {
        "ItemName": name,
        "ItemValue": value,
        "ItemResult": result_str,
        "Description": description
    }

    return ret_dirt


# dev 测试设备类型，sn SN号，test_dev 治具名称或编号
def check_sn_is_ok(sn=""):
    print("海能mes, check sn")
    dev = test.load_cfg.dev
    test_dev = test.load_cfg.test_tool

    user_parameter = station_sn_code.get(dev, "")
    if user_parameter == "":  # 设备不需要过海能工站
        return True
    dat_dirt = {
        'API': 'HN_CheckLotSN',
        'UserParameter': user_parameter,  # 用户码
    }
    user_data = {
        "LotSN": sn,
        "TestDevice": test_dev,
    }
    # indent 用于美化输出，缩进 4 个空格
    dat_dirt["UserData"] = json.dumps(user_data, ensure_ascii=False, indent=4)
    ret = celink_mes_communication(dat_dirt)
    if ret[0] is not True:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="海能MES，"+ret[1], color=wx.RED)
    else:
        return True


def is_json(json_string):
    if not isinstance(json_string, str):  # 检查是否为字符串
        return False
    try:
        json.loads(json_string)
        return True
    except json.JSONDecodeError:
        return False
    

def format_message_with_line_breaks(msg):
    """在每两个逗号后添加换行符（保留原逗号）"""
    result = []
    comma_count = 0
    for ch in msg:
        result.append(ch)
        if ch == ',' or ch == '，':      # 同时支持英文和中文逗号
            comma_count += 1
            if comma_count % 2 == 0:
                result.append('\n')
    return ''.join(result)


def celink_send_report(dev, start_time, end_time, ck_sn, result):
    print("海能mes发送记录")
    data = {
        "API": "HN_SubmitTestData",
        "UserParameter": station_report_code.get(dev),
    }

    user_data = {
        "LotSN": ck_sn,
        "TestDevice": test.load_cfg.test_tool,
        "UserCode": "001",
        "TestResult": result,
        "StartTime": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "EndTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "TestDataItem": mes_run.celink_report
    }
    print("1111111111")
    print(mes_run.celink_report)
    data["UserData"] = json.dumps(user_data, ensure_ascii=False, indent=4)

    ret = celink_mes_communication(data)

    if ret[0] is True:
        wx.CallAfter(MainFrame.main_frame.up_sn_ui, "")
        return True
    else:
        # 处理错误消息：每两个逗号换行
        formatted_error = format_message_with_line_breaks(ret[1])
        full_msg = "海能mes，" + formatted_error   # 使用中文逗号保持风格
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second=full_msg, color=wx.RED)
        wx.CallAfter(MainFrame.main_frame.up_notification_ui_item_size, 2, 16)   # 字体缩小为16
        wx.CallAfter(MainFrame.main_frame.up_sn_ui, "")
        return False


# def celink_send_report(dev, start_time, end_time, ck_sn, result):
#     print("海能mes发送记录")
#     data = {
#         "API": "HN_SubmitTestData",
#         "UserParameter": station_report_code.get(dev),
#     }

#     user_data = {
#         "LotSN": ck_sn,
#         "TestDevice": test.load_cfg.test_tool,
#         "UserCode": "001",
#         "TestResult": result,
#         "StartTime": start_time.strftime("%Y-%m-%d %H:%M:%S"),
#         "EndTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
#         "TestDataItem": mes_run.celink_report
#     }
#     print("1111111111")
#     print(mes_run.celink_report)
#     data["UserData"] = json.dumps(user_data, ensure_ascii=False, indent=4)

#     ret = celink_mes_communication(data)

#     if ret[0] is True:
#         return True
#     else:
#         wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="海能mes," + ret[1], color=wx.RED)
#         # wx.CallAfter(MainFrame.main_frame.up_notification_ui_item_size, 2, 12)  # 将第二行字体缩小为12
#         wx.CallAfter(MainFrame.main_frame.up_notification_ui_item_size, 2, 16)  # 将第二行字体缩小为12
#         return False

#     # if ret[0] is True:
#     #     return True
#     # else:
#     #     wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="海能mes，" + ret[1], color=wx.RED)
#     #     return False


def celink_bind_robot_bat_lt_sn(robot_sn="", bat_sn="", lt_sn=""):
    bind_dev = [
        {"AssemblyType": "Bat", "AssemblySN": bat_sn},
        {"AssemblyType": "Front", "AssemblySN": lt_sn},
    ]

    data = {
        "API": "HN_BindData",
        "UserParameter": station_report_code.get(test.load_cfg.dev),
    }
    user_data = {
        "LotSN": robot_sn,
        "BindData": bind_dev,
    }
    data["UserData"] = json.dumps(user_data, ensure_ascii=False, indent=4)

    ret = celink_mes_communication(data)

    if ret[0] is True:
        return True
    else:
        wx.CallAfter(MainFrame.main_frame.up_notification_ui, second="海能mes，" + ret[1], color=wx.RED)
        return False

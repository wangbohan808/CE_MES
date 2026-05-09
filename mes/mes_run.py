from test_tool import test
from mes import anker_mes
from mes import celink_mes
from ui import MainFrame
from datetime import datetime
from test_tool import excel

anker_report = []
celink_report = []


# 过站检测，return: TURE 检测通过， FASE 检测不通过
def check_sn_is_ok(sn=""):
    # 如果不使用mes系统，直接返回TURE
    if test.load_cfg.mes != "001" and test.load_cfg.mes != "002" and test.load_cfg.mes != "003":
        return True
    if test.load_cfg.mes == "001" or test.load_cfg.mes == "002":  # mes == 2 仅使用海能 mes
        if celink_mes.check_sn_is_ok(sn) is not True:
            return False
    if test.load_cfg.mes == "001" or test.load_cfg.mes == "003":  # mes == 2 仅使用海能 mes
        if anker_mes.check_sn_is_ok(sn) is not True:
            return False

    return True


# 过站检测，return: TURE 检测通过， FASE 检测不通过
def check_station_is_ok(sn):
    print("check sn: " + sn)
    # 如果不使用mes系统，直接返回TURE
    if test.load_cfg.mes != "001" and test.load_cfg.mes != "002" and test.load_cfg.mes != "003":
        return True
    if test.load_cfg.mes == "001" or test.load_cfg.mes == "002":  # mes == 2 仅使用海能 mes
        if celink_mes.check_sn_is_ok(sn) is not True:
            return False
    if test.load_cfg.mes == "001" or test.load_cfg.mes == "003":  # mes == 2 仅使用海能 mes
        if anker_mes.check_station_is_ok(sn) is not True:
            return False

    return True


def clear_report():
    global celink_report
    global anker_report

    celink_report = []
    anker_report = []


# result ,"OK", "NG", "un_test"
def add_report(name="", result="", value="", val_max="", val_min=""):

    global celink_report
    global anker_report

    celink_res = "un_test"
    anker_res = 0  # res  int类型 0:no test,1:skip,2:success,3:fail
    if result == "OK":
        celink_res = result
        anker_res = 2
    elif result == "NG":
        celink_res = result
        anker_res = 3
    elif result == "un_test":
        anker_res = 0
        value = "未测试"

    des = ""
    if val_max != "" and val_max != "":
        des = "max:" + val_max + " min:" + val_min

    celink_rep = celink_mes.celink_mes_get_result_item(name=name, value=value,
                                                       description=des,
                                                       result=celink_res)
    anker_rep = anker_mes.anker_mes_get_result_item(name=name,
                                                    result=anker_res,
                                                    value=value,
                                                    val_max=val_max,
                                                    val_min=val_min)
    celink_report.append(celink_rep)
    anker_report.append(anker_rep)


# result ,"OK", "NG", "un_test"
def add_report_cliff(name="", result="", value="", val_max="", val_min=""):
    add_report(name="", result="", value="", val_max="", val_min="")


def send_report(start_time, end_time, sn, result):
    ret = True
    # 如果不使用mes系统，直接返回TURE
    print("%s",test.load_cfg.mes)
    if test.load_cfg.mes != "001" and test.load_cfg.mes != "002" and test.load_cfg.mes != "003":
        ret = True
    elif test.load_cfg.mes == "001" or test.load_cfg.mes == "002":  # mes == 2 仅使用海能 mes
        print("celink_mes")
        if celink_mes.celink_send_report(test.load_cfg.dev, start_time, end_time, sn, result) is not True:
            ret = False
        else:
            ret = True
    elif test.load_cfg.mes == "001" or test.load_cfg.mes == "003":  # mes == 3 仅使用海能 mes
        print("anker_mes")
        if anker_mes.anker_send_report(start_time, end_time, sn, result) is not True:
            ret = False
        else:
            ret = True
    if ret is False:
        result = "mes NG"
    save_report(end_time, sn=sn, result=result)

    return ret


def get_test_item_value(res):
    if res == 0:
        res_str = "未测试"
    elif res == 1:
        res_str = "测试跳过"
    elif res == 2:
        res_str = "PASS"
    elif res == 3:
        res_str = "NG"
    else:
        res_str = "未知结果"
    return res_str


def save_report(time, sn="", result=""):
    dev = test.load_cfg.dev
    formatted_date = datetime.now().strftime("%Y-%m")  # 格式：YYYY-MM
    test_end_time = time.strftime("%Y-%m-%d %H:%M:%S")
    file_path = "测试记录\\" + MainFrame.heading_line_dict[dev] + "记录" + formatted_date + ".csv"
    record = {
        "日期": test_end_time,
        "SN": sn,
        "测试结果": result
    }
    print(str(anker_report))
    # 组装测试结果 //result  int类型 0:no test,1:skip,2:success,3:fail
    for index, value in enumerate(anker_report):
        name = value["name"]+"测试" + str(index+1)
        record[name] = get_test_item_value(value["result"])
        name = value["name"] + "值" + str(index+1)
        record[name] = value["val"]
        name = value["name"] + "阀值" + str(index+1)
        record[name] = value["min"] + "-" + value["max"]

    excel.add_record_to_csv(file_path, record)




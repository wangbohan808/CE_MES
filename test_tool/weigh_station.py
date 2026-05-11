# [WEIGH-106] 称重工位（device_type=106）专用模块 — 调优请全文搜索：WEIGH-106、[WEIGH-106]、weigh_station
import re
import time
import wx
from datetime import datetime

from myserial import test_serial
from tool_box import tool
from test_tool import test
from test_tool import encode_rules
from test_tool import weigh_limits
from mes import mes_run
from ui import MainFrame

# --- WEIGH-106-BEGIN: 协议常量 ---
WEIGH_CMD_READ = b"R\r\n"
# 应答示例 ASCII: "+ 2.17 kg \r\n"
WEIGHT_LINE_PATTERN = re.compile(r"[+-]\s*([\d.]+)\s*kg", re.IGNORECASE)
# --- WEIGH-106-END ---


# [WEIGH-106]
def parse_weight_kg_from_text(text):
    """从仪表应答文本中解析质量（kg）。失败返回 None。"""
    if not text:
        return None
    m = WEIGHT_LINE_PATTERN.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


# [WEIGH-106]
def read_scale_response_text(timeout_sec):
    """在超时内从 test_rx_q 拼出应答字符串（可含多段 chunk）。"""
    deadline = time.time() + float(timeout_sec)
    buf = ""
    while time.time() < deadline:
        drained = False
        while not test_serial.test_rx_q.empty():
            chunk = test_serial.test_rx_q.get()
            buf += chunk.decode("utf-8", errors="ignore")
            drained = True
        if "\n" in buf or "\r\n" in buf:
            return buf
        if drained is False:
            time.sleep(0.02)
    return buf


# [WEIGH-106]
def process():
    """称重工位主流程：单次扫码 -> 编码规则 -> 海能过站 -> 延时 -> R\\r\\n -> 解析 -> 上下限 -> MES 上报。"""
    sn_list = test.get_sn_collect_res()
    if test.is_sn_up_enable():
        return
    if len(sn_list) != 1:
        wx.CallAfter(
            MainFrame.main_frame.up_notification_ui,
            first="获取条码数量异常：",
            color=wx.RED,
        )
        test.test_work_state = "idle"
        return
    sn = sn_list[0]


    encode_res = encode_rules.match_sn_encoding_rules(dev=test.load_cfg.dev, sn=sn)
    if encode_res is not True:
        wx.CallAfter(
            MainFrame.main_frame.up_notification_ui,
            second="SN编码异常 NG：" + sn,
            color=wx.RED,
        )
        test.test_work_state = "idle"
        return


    if mes_run.check_sn_is_ok(sn) is False:
        test.test_work_state = "idle"
        return

    wx.CallAfter(
        MainFrame.main_frame.up_notification_ui,
        second="过站通过，即将读取重量…",
        third="（约 {:.1f}s）".format(test.load_cfg.weight_read_delay_sec),
        color=wx.RED,
    )
    time.sleep(float(test.load_cfg.weight_read_delay_sec))


    # [WEIGH-106]清空队列，解析数据
    tool.clear_queue(test_serial.test_rx_q)
    test_serial.test_serial_send(WEIGH_CMD_READ)

    rx_text = read_scale_response_text(test.load_cfg.weight_read_timeout_sec)
    weight_kg = parse_weight_kg_from_text(rx_text)
    end_time = datetime.now()
    w_min = float(test.load_cfg.weight_min_kg)
    w_max = float(test.load_cfg.weight_max_kg)
    scheme_2 = str(getattr(test.load_cfg, "weigh_scheme", "1")).strip() == "2"

    # [WEIGH-106]清空mes报告，添加报告
    mes_run.clear_report()

    if weight_kg is None:
        wx.CallAfter(
            MainFrame.main_frame.up_notification_ui,
            second="读数失败或超时",
            third="原始应答：" + repr(rx_text[:120]),
            color=wx.RED,
        )
        mes_run.add_report(
            name="重量(kg)",
            result="NG",
            value="READ_FAIL",
            val_max=str(w_max),
            val_min=str(w_min),
        )
        mes_run.send_report(test.test_start_time, end_time, sn, "NG")
        test.test_work_state = "idle"
        test.clear_sn_save_list()
        return

    rep_lo = w_min
    rep_hi = w_max
    third_detail = "合格区间 {:.1f} ~ {:.1f} kg".format(w_min, w_max)

    if not scheme_2:
        in_range = w_min <= weight_kg <= w_max
    else:
        hist = weigh_limits.load_history_weights()
        t = len(hist) + 1
        p = int(getattr(test.load_cfg, "weigh_pass_first_n", 5))
        if p < 0:
            p = 0
        if t <= p:
            in_range = True
            rep_lo, rep_hi = w_min, w_max
            third_detail = "第 {} 台，前 {} 台直通（MES 参考 {:.1f}~{:.1f} kg）".format(
                t, p, w_min, w_max
            )
        else:
            dyn = weigh_limits.scheme2_dynamic_limits(t, hist)
            if dyn is None:
                in_range = w_min <= weight_kg <= w_max
                rep_lo, rep_hi = w_min, w_max
                third_detail = "动态窗口无样本，暂用固定限 {:.1f}~{:.1f} kg".format(
                    w_min, w_max
                )
            else:
                lo, hi, mu, sig = dyn
                rep_lo, rep_hi = lo, hi
                in_range = lo <= weight_kg <= hi
                third_detail = "μ±σ 合格 {:.3f}~{:.3f} kg（μ={:.3f} σ={:.3f}）".format(
                    lo, hi, mu, sig
                )
        new_hist = list(hist)
        new_hist.append(weight_kg)
        weigh_limits.save_history_weights(new_hist)

    overall = "OK" if in_range else "NG"
    mes_run.add_report(
        name="重量(kg)",
        result=overall,
        value="{:.3f}".format(weight_kg),
        val_max="{:.3f}".format(rep_hi),
        val_min="{:.3f}".format(rep_lo),
    )
    send_ok = mes_run.send_report(test.test_start_time, end_time, sn, overall)
    if send_ok:
        if in_range:
            wx.CallAfter(
                MainFrame.main_frame.up_notification_ui,
                second="称重 PASS  {:.3f} kg".format(weight_kg),
                third=third_detail,
                color=wx.GREEN,
            )
        else:
            wx.CallAfter(
                MainFrame.main_frame.up_notification_ui,
                second="称重 NG  {:.3f} kg".format(weight_kg),
                third=third_detail,
                color=wx.RED,
            )
    else:
        wx.CallAfter(
            MainFrame.main_frame.up_notification_ui,
            second="称重结果已判 {}，但 MES 上报失败".format(overall),
            third="实测 {:.3f} kg".format(weight_kg),
            color=wx.RED,
        )

    test.test_work_state = "idle"
    test.clear_sn_save_list()

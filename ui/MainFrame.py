import time

import wx
import wx.xrc
import mythread
import test_tool.test
from myserial import test_serial
from test_tool import test
from tool_box import tool
from test_tool import sn_check
import applog

# 主界面
main_frame = None
# 标题和版本号
name_ver = "海能测试治具 v1.0.3"

# 位图列表
bitmap_list = [
    {"ture": "picture/ture.png"},
    {"false": "picture/false.png"},
    {"warning": "picture/warning.png"},
    {"white": "picture/white.png"},
    {"red": "picture/red.png"},
    {"green": "picture/green.png"},
]


item_result = [
    {"ir_rx": ["红外收发：", "", "white"]},
    {"ac_check": ["AC交流过零：", "", "white"]},
    {"right_ir": ["右红外灯：", "", "white"]},
    {"load_current": ["负载电流：", "", "white"]},
    {"barometer": ["气压计小板：", "", "white"]},
    {"left_ir": ["左红外灯：", "", "white"]},
    {"bag_install": ["尘袋在位：", "", "white"]},
    {"led_display": ["LED灯效：", "", "white"]},
    {"guard_light": ["近 卫 灯：", "", "white"]},
    {"suction": ["吸   力：", "", "white"]},
]

# [up_test_ui_WBH] RV30(device_type=50) 测试格键名与 test.py 0x77 字段一致
rv30_item_result = [
    {"mcu_ver": ["MCU版本：", "", "white"]},
    {"ir_code_left": ["左回充码：", "", "white"]},
    {"ir_code_lc": ["左中回充：", "", "white"]},
    {"ir_code_rc": ["右中回充：", "", "white"]},
    {"ir_code_right": ["右回充码：", "", "white"]},
    {"charge_value": ["充电电流：", "", "white"]},
    {"rv30_freq": ["过零频率：", "", "white"]},
    {"dust_bug_install": ["尘袋在位：", "", "white"]},
    {"rv30_led": ["LED灯效：", "", "white"]},
    {"dust_collection_suction": ["集尘吸力：", "", "white"]},
]


#TODO使用时打开
hw1_over_water_item_result = [
    {"clear_water_volume": ["清水通路水量：", "", "white"]},
    {"duty_water_volume": ["污水通路水量：", "", "white"]},
    {"left_mop_water_volume": ["左拖布水量：", "", "white"]},
    {"right_mop_water_volume": ["右拖布水量：", "", "white"]},
    {"left_mop_temperature": ["左拖布温度：", "", "white"]},
    {"right_mop_temperature": ["右拖布温度：", "", "white"]},
]

#TODO使用时打开
hw1_over_air_item_result = [
    {"clear_water_pressure": ["清水通路气压：", "", "white"]},
    {"duty_water_pressure": ["污水通路气压：", "", "white"]},
    {"left_mop_water_pressure": ["拖布通路气压：", "", "white"]},
]

#TODO使用时打开
hw1_basestation_produst_item_result = [
    {"charge_value": ["充电电流：", "", "white"]},
    {"hot_air": ["热风：", "", "white"]},
    {"ir_code_left": ["左回充码：", "", "white"]},
    {"ir_code_right": ["右回充码：", "", "white"]},
    {"ir_code_rc": ["右中回充码：", "", "white"]},  # #[RV30-PROTO-77-MOD]
    {"ir_code_lc": ["左中回充码：", "", "white"]},  # #[RV30-PROTO-77-MOD]
    {"clear_tank_install": ["清水箱在位：", "", "white"]},
    {"duty_tank_install": ["污水箱在位：", "", "white"]},
    {"dust_bug_install": ["尘袋在位：", "", "white"]},
    {"clean_base_install": ["清洁底座在位：", "", "white"]},
    {"dust_collection_suction": ["集尘吸力：", "", "white"]},
    {"clean_water_pump_current": ["清水泵电流：", "", "white"]},
    {"duty_water_pump_current": ["污水泵电流：", "", "white"]},
    {"cleaner_pump_current": ["清洁泵电流：", "", "white"]},
    {"electromagnetic_three_way_current": ["电磁三通电流：", "", "white"]},
    {"clean_base_liquid_level": ["清洁底座液位：", "", "white"]},
    {"turbidity_data": ["浊度数据", "", "white"]},

]

# device_type： 0001   集尘桶产品；0002 充电座产品；
#               0003   前撞组件； 0004 前撞PCB；
#               0005   地检组件； 0006 集尘宝PCBA；
#                     大于 999 非海能测试主板治具
#               1000  绑定主机、前撞组件、电池组件
#               1001  打高压测试治具
# 标题栏文字
heading_line_text = "海能测试治具"
# 设备类型和标题栏列表
# heading_line_dict = {
#     "001": "集尘桶测试治具",
#     "002": "充电座测试治具",
#     "003": "前撞组件测试治具",
#     "004": "前撞PCB测试治具",
#     "005": "地检组件测试治具",
#     "006": "集尘桶PCB测试治具",
#     "007": "静态电流测试治具",
#     "010": "左轮测试治具",
#     "011": "右轮测试治具",
#     "012": "边刷摆臂治具",
#     "013": "中扫测试治具",
#     "100": "绑定主机、前撞、电池",
#     "101": "打高压测试治具",
#     "102": "条码比对工具",
#     "103": "配件纸箱条码检测工具",
#     "104": "打高压治具ZC7122D",
# }

heading_line_dict = {
    "001": "过水测试治具",
    "002": "充电座测试治具",
    "003": "前撞组件测试治具",
    "004": "前撞PCB测试治具",
    "005": "地检组件测试治具",
    "006": "集尘桶PCB测试治具",
    "007": "静态电流测试治具",
    "010": "左轮测试治具",
    "011": "右轮测试治具",
    "012": "边刷摆臂治具",
    "013": "中扫测试治具",
    "105": "耐高压测试治具",
    "015": "过气测试治具",
    "016": "过水测试治具",
    "017": "基站成品测试治具",
    "100": "绑定主机、前撞、电池",
    "101": "打高压测试治具",
    "102": "条码比对工具",
    "103": "配件纸箱条码检测工具",
    "104": "打高压治具ZC7122D",
    "106": "称重工位",  # [WEIGH-106] device_type=106，与 WEIGH_STATION_106_SPEC / weigh_station 对照

    #[FX_TODO]
    "050":"双红外成品检测"
}


# green1 = wx.Colour("ForestGreen")  # 森林绿 (RGB:34,139,34)
# green2 = wx.Colour("LimeGreen")   # 柠檬绿 (RGB:50,205,50)

class MainFrame(wx.Frame):
    def __init__(self, parent):
        global main_frame
        main_frame = self

        # 加载配置信息
        test.load_config()
        # 按键信息
        self.buttons_msg = [
            {"name": "open_serial", "display": "打开串口", "function": self.open_serial},
            # {"name": "close_serial", "display": "关闭串口", "function": self.close_serial}
        ]
        self.buttons = []

        # 连接状态信息
        self.connect_msg = [
            {"name": "com_connect", "display": "夹具：", "display_bitmap": get_bitmap("false")},
            # {"name": "scanner_connect", "display": "扫码枪：", "display_bitmap": get_bitmap("false")},
        ]

        self.connect_text = []
        self.connect_bitmap = []
        # 用来存储测试结果控件
        self.test_widget = []
        # 集尘桶版本和配件SN号
        self.dev_ver = None  # 集尘桶或其他软件版本号
        self.dev_sn = None            # 集尘桶或其他配件SN号
        # 用于存储扫码枪(键盘输入)输入的数据
        self.barcode_data = ""
        # 输出提示信息
        self.notification_static_text = []
        # 用来存储输入数据控件列表
        self.input_sn_text_ctrl = []
        # 日志
        self.logger = None

        # 初始化 wx.Frame 窗口对象,是顶级窗口
        # parent: 父窗口。如果是顶级窗口，可以设置为 None
        # wx.ID_ANY 自动分配ID
        # pos: 窗口的初始位置。默认值为 wx.DefaultPosition，表示由系统决定位置
        # size: 窗口的初始大小。默认值为 wx.DefaultSize，表示由系统决定大小 (width, height)
        # style: 窗口样式 wx.RESIZE_BORDER、wx.MINIMIZE_BOX,wx.TAB_TRAVERSAL 允许tab键切换焦点
        wx.Frame.__init__(self, parent, id=wx.ID_ANY,
                          title=name_ver, pos=wx.DefaultPosition,
                          size=wx.Size(900, 600),
                          style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)
        self.SetFocus()  # 延时调用确保窗口就绪，获取键盘输入焦点
        # 默认显示字体
        ui_def_font = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL,
                              faceName="微软雅黑")
        # 创建主布局，垂直分布
        main_box = wx.BoxSizer(wx.VERTICAL)

        # 使用 sizer 布局管理器将控件居中

        # 第一行，水平布局，创建若干按键
        item_one_box = wx.BoxSizer(wx.HORIZONTAL)

        for item in self.buttons_msg:
            button = wx.Button(self, wx.ID_ANY, item["display"], wx.DefaultPosition, wx.DefaultSize)
            item_one_box.Add(button, 0, wx.ALL, 5)
            button.Bind(wx.EVT_BUTTON, item["function"])
            self.buttons.append(button)
        # 标题行，显示所要测试的设备
        title_text = test.load_cfg.project_name + heading_line_dict.get(test.load_cfg.dev, "未知设备，请修改配置")
        heading_line_static_text = wx.StaticText(self, wx.ID_ANY, title_text,
                                                 wx.DefaultPosition, wx.DefaultSize, style=wx.ALIGN_CENTER)
        # 标题栏字体
        heading_line_font = wx.Font(30, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        heading_line_static_text.SetFont(heading_line_font)
        item_one_box.Add(heading_line_static_text, 1, wx.ALL | wx.ALIGN_CENTER, 5)

        # 第二行，水平显示，各个连接状态
        connect_static_box = wx.StaticBox(self, wx.ID_ANY, "连接状态")  # 添加方框标题
        item_tow_box = wx.StaticBoxSizer(connect_static_box, wx.HORIZONTAL)
        connect_static_box.SetFont(ui_def_font)
        # GetStaticBox() 用于获取与 wx.StaticBoxSizer 关联的 wx.StaticBox 控件

        # 创建具体内容
        for item in self.connect_msg:
            static_text = wx.StaticText(connect_static_box, wx.ID_ANY, item["display"]+"未连接",
                                        wx.DefaultPosition, wx.DefaultSize, 0)
            static_text.SetMinSize(wx.Size(80, -1))
            static_bitmap = wx.StaticBitmap(connect_static_box, wx.ID_ANY, get_bitmap("false"),
                                            wx.DefaultPosition, wx.Size(20, 20), 0)
            static_bitmap.SetMinSize(wx.Size(80, -1))
            # 添加到容器
            item_tow_box.Add(static_text, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
            item_tow_box.Add(static_bitmap, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
            # 保存创建的 StaticText 和 StaticBitmap 到列表
            self.connect_text.append(static_text)
            self.connect_bitmap.append(static_bitmap)

        # 第三行，用于测试过程中的提示信息
        notif_static_box = wx.StaticBox(self, wx.ID_ANY, "提示信息")  # 添加方框标题
        notif_static_box_sizer = wx.StaticBoxSizer(notif_static_box, wx.HORIZONTAL)
        # 设置字体和高度
        notification_font = wx.Font(26, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        notif_ver_box = wx.BoxSizer(wx.VERTICAL)  # 垂直分布
        for i in range(3):
            text = wx.StaticText(notif_static_box, wx.ID_ANY, "",
                                wx.DefaultPosition, wx.DefaultSize, 0)
            text.SetFont(notification_font)
            notif_ver_box.Add(text, 0, wx.ALL | wx.EXPAND, 5)
            self.notification_static_text.append(text)
        # for i in range(3):
        #     text = wx.StaticText(notif_static_box, wx.ID_ANY, "",
        #                         wx.DefaultPosition, wx.DefaultSize, 0)
        #     text.SetFont(notification_font)
        #     notif_ver_box.Add(text, 0, wx.ALL | wx.EXPAND, 5)
        #     self.notification_static_text.append(text)
        notif_static_box_sizer.Add(notif_ver_box, 1, wx.ALL | wx.EXPAND)

        # 第四行，显示版本号和SN
        item_sn_ver_box = wx.BoxSizer(wx.HORIZONTAL)
        # 版本号复用
        ver_str_change = "版本号："
        if int(test.load_cfg.dev) == 103:
            ver_str_change = "配件总数："
        ver_name_static_text = wx.StaticText(self, wx.ID_ANY, ver_str_change,
                                             wx.DefaultPosition, wx.DefaultSize, 0)
        ver_name_static_text.SetFont(ui_def_font)
        ver_static_text = wx.StaticText(self, wx.ID_ANY, "",
                                        wx.DefaultPosition, wx.DefaultSize, 0)
        ver_static_text.SetMinSize(wx.Size(100, -1))
        ver_static_text.SetFont(ui_def_font)
        sn_name_static_text = wx.StaticText(self, wx.ID_ANY, "SN: ",
                                            wx.DefaultPosition, wx.DefaultSize, 0)
        sn_name_static_text.SetFont(ui_def_font)
        sn_static_text = wx.StaticText(self, wx.ID_ANY, "",
                                       wx.DefaultPosition, wx.DefaultSize, 0)
        sn_static_text.SetFont(ui_def_font)
        # 保存版本号和 SN号内容控件，方便更新
        self.dev_ver = ver_static_text
        self.dev_sn = sn_static_text

        item_sn_ver_box.Add(ver_name_static_text, 0, wx.ALL, 5)
        item_sn_ver_box.Add(ver_static_text, 0, wx.ALL, 5)
        item_sn_ver_box.Add(sn_name_static_text, 0, wx.ALL, 5)
        item_sn_ver_box.Add(sn_static_text, 0, wx.ALL, 5)

        # 第四行，网格显示，添加方框，测试项
        # test_static_box = wx.StaticBox(self, wx.ID_ANY, "测试数据")  # 添加方框标题
        test_static_box = wx.StaticBox(self, wx.ID_ANY, "")  # 添加方框标题
        test_static_box_sizer = wx.StaticBoxSizer(test_static_box, wx.HORIZONTAL)
        item_temp = item_result
        # [up_test_ui_WBH] RV30 基站成品使用专用测试项列表
        if int(test.load_cfg.dev) == 50:
            item_temp = rv30_item_result
        elif str(test.load_cfg.project_name) is not None and str(test.load_cfg.project_name) == "HW1" or str(test.load_cfg.project_name) == "RV50":
            if int(test.load_cfg.dev) == 16:
                item_temp = hw1_over_water_item_result
            if int(test.load_cfg.dev) == 15:
                item_temp = hw1_over_air_item_result
            if int(test.load_cfg.dev) == 17:
                item_temp = hw1_basestation_produst_item_result

        if len(item_temp) % 3 == 0:
            row = len(item_temp) // 3
        else:
            row = len(item_temp) // 3 + 1
        flex_grid = wx.FlexGridSizer(rows=row, cols=9, vgap=5, hgap=5)
        print("row is ", row)
        # 添加控件到 FlexGridSizer
        for msg in item_temp:
            key = next(iter(msg))
            widget_list = []
            for index, value in enumerate(msg[key]):
                if index == 0:
                    static_tex1 = wx.StaticText(test_static_box, wx.ID_ANY,
                                                value, wx.DefaultPosition, wx.DefaultSize, 0)
                    # static_tex1.SetBackgroundColour(wx.Colour(0, 169, 169))  # 文本框背景灰色的RGB值
                    static_tex1.SetMinSize(wx.Size(120, -1))
                    static_tex1.SetFont(ui_def_font)
                    flex_grid.Add(static_tex1, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
                    widget_list.append(static_tex1)
                elif index == 1:
                    static_tex2 = wx.StaticText(test_static_box, wx.ID_ANY,
                                                value, wx.DefaultPosition, wx.DefaultSize, 0)
                    static_tex2.SetBackgroundColour(wx.Colour(255, 255, 255))  # 白色的RGB值
                    static_tex2.SetMinSize(wx.Size(100, -1))
                    static_tex2.SetFont(ui_def_font)
                    flex_grid.Add(static_tex2, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
                    widget_list.append(static_tex2)
                elif index == 2:
                    static_bitmap = wx.StaticBitmap(test_static_box, wx.ID_ANY, get_bitmap(value),
                                                    wx.DefaultPosition, wx.Size(20, 20), 0)
                    flex_grid.Add(static_bitmap, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
                    widget_list.append(static_bitmap)
            self.test_widget.append({key: widget_list})

        test_static_box_sizer.Add(flex_grid, 1, wx.EXPAND)
        # 设置行和列可以扩展, 设置 3、6、9项可扩展，并设置相同比例
        flex_grid.AddGrowableCol(2, proportion=1)
        flex_grid.AddGrowableCol(5, proportion=1)
        flex_grid.AddGrowableCol(8, proportion=1)
        # AddGrowableRow()

        main_box.Add(item_one_box, 0, wx.EXPAND | wx.ALL, 5)
        main_box.Add(item_tow_box, 0, wx.EXPAND | wx.ALL, 5)
        main_box.Add(notif_static_box_sizer, 0, wx.EXPAND | wx.ALL, 5)
        main_box.Add(item_sn_ver_box, 0, wx.EXPAND | wx.ALL, 5)
        main_box.Add(test_static_box_sizer, 0, wx.EXPAND | wx.ALL, 5)
        dev = int(test.load_cfg.dev)


        # [FX_TODO]
        # if int(dev) > 100:
        #     test_static_box.Hide()
        if int(dev) != 50:
            test_static_box.Hide()


        if int(dev) == 100 or int(dev) == 102 or int(dev) == 103:
            connect_static_box.Hide()
        self.Layout()

        self.SetSizer(main_box)
        # self.Layout()  # 强制刷新当前窗口或面板的布局,通常情况下，SetSizer 会自动调用 Layout()
        self.Centre(wx.BOTH)  # 将窗口居中显示，如果只想在水平或垂直方向上居中，可以使用 wx.HORIZONTAL 或 wx.VERTICAL
        self.Layout()
        # 绑定事件
        # 绑定键盘事件
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_event)
        # 绑定窗口最大化事件
        self.Bind(wx.EVT_MAXIMIZE, self.on_maximize)
        # 主窗口关闭，关闭其他线程
        self.Bind(wx.EVT_CLOSE, self.on_window_close)
        # 绑定窗口就绪事件
        self.Bind(wx.EVT_SHOW, self.on_window_ready)
        #绑定窗口大小事件，确保用户调整窗口宽度时文本重新换行
        self.Bind(wx.EVT_SIZE, self.on_size)
        # 创建测试线程
        mythread.start_work_thread()
        mythread.start_serial_thread()

    def open_serial(self, event):

        self.reset_ui()
        self.SetFocus()  # 延时调用确保窗口就绪，获取键盘输入焦点

        dev = int(test.load_cfg.dev)
        # 测试不需要串口，
        if dev == 100:
            self.up_notification_ui(second="请扫主机条码，启动测试", color=wx.RED)
        elif dev == 102 or dev == 103:
            test.test_error_str = ""
            test.sn_save_list = []
            test.barcode_msg_update = False
            tool.clear_queue(test.barcode_q)
            self.up_notification_ui(second="请扫码", color=wx.RED)
            if dev == 103:
                self.up_ver_ui(ver_str=str(sn_check.parts_total_counts))
            print("请扫码")
        # 串口打开状态，关闭串口，清空屏幕
        elif test_serial.get_test_com_open_state():
            self.up_notification_ui(second="串口已关闭，请打开串口", color=wx.RED)
            self.up_open_ser_button_text("打开串口")
            test_serial.close_test_com()
        # 串口没有打开状态，打开串口，清空屏幕
        elif test_serial.get_test_com_open_state() is False:
            test_serial.open_test_com()
            if test_serial.get_test_com_open_state():
                self.up_open_ser_button_text("关闭串口")
                self.up_notification_ui(second="请扫码，启动测试", color=wx.RED)
            else:
                self.up_open_ser_button_text("打开串口")
                self.up_notification_ui(second="串口打开失败", color=wx.RED)

        test.test_work_state = "idle"
        event.Skip()  # 告诉MainLoop继续处理这个消息，而不是在当前handler处理完了就中断了

    def close_serial(self, event):
        print("关闭串口")
        test_serial.close_test_com()
        self.up_connect_ui("com_connect", False)
        event.Skip()  # 告诉MainLoop继续处理这个消息，而不是在当前handler处理完了就中断了

    def on_maximize(self, event):
        self.SetFocus()  # 获取键盘输入焦点
        event.Skip()  # 确保事件继续传递

    def on_window_close(self, event):
        if mythread.work_thread and mythread.work_thread.is_alive():
            mythread.work_stop_event.set()
            mythread.work_thread.join()
        if mythread.serial_thread and mythread.serial_thread.is_alive():
            mythread.serial_stop_event.set()
            mythread.serial_thread.join()
        # 确保程序退出
        event.Skip()

    def on_window_ready(self, event):
        self.logger = applog.AppLog()
        # 记录启动完成
        log = self.logger.get_logger()
        log.info("UI运行OK，启动日志功能")
        # 解绑事件避免重复初始化
        self.Unbind(wx.EVT_SHOW)
        # 确保程序退出
        event.Skip()

    def on_size(self, event):
        event.Skip()
        for text in self.notification_static_text:
            text.Wrap(-1)
        self.Layout()

    # 键盘事件
    def on_key_event(self, event):
        """
        处理键盘事件，捕获扫码枪输入的数据
        """
        key_code = event.GetUnicodeKey()
        focus = wx.Window.FindFocus()
        if focus:
            if focus != self:
                self.SetFocus()  # 获取键盘输入焦点

        # 如果按下的是回车键，表示扫码完成
        if key_code == wx.WXK_NONE:  # 读取到无效的Unicode 字符
            pass
        elif key_code == wx.WXK_RETURN or key_code == wx.WXK_TAB:
            self.up_sn_ui(self.barcode_data)
            print(self.barcode_data)
            test.barcode_msg = self.barcode_data
            if test.barcode_q.full() is not True:
                test.barcode_q.put(self.barcode_data)
            if test.is_sn_up_enable():
                ret = test.save_sn_to_list(self.barcode_data)
                if ret:
                    test.clear_sn_up_enable()
                    if int(test.load_cfg.dev) < 100:
                        test.send_sn_cmd()
                self.up_notification_ui(first=test.sn_save_list[0]["head"] + test.sn_save_list[0]["sn"],
                             second=test.sn_save_list[1]["head"] + test.sn_save_list[1]["sn"],
                             third=test.sn_save_list[2]["head"] + test.sn_save_list[2]["sn"],
                             color=wx.RED)
            test.barcode_msg_update = True
            self.barcode_data = ""  # 清空数据，准备下一次扫码
        else:
            # 将按键字符添加到扫码数据中
            self.barcode_data += chr(key_code)
            print(hex(key_code))

        event.Skip()  # 继续传递事件

    def up_open_ser_button_text(self, dis_str=""):
        self.buttons[0].SetLabel(dis_str)

    # 更新连接状态, name 见 self.connect_msg 键 "name" 的值
    # state bool型
    def up_connect_ui(self, name, state):
        if state:
            cun_port = test_serial.test_ser.port
        for index, value in enumerate(self.connect_msg):
            if value.get("name") == name:
                if state is True:
                    dis_str = value.get("display") + cun_port
                    bitmap = get_bitmap("ture")
                else:
                    dis_str = value.get("display") + "未连接"
                    bitmap = get_bitmap("false")
                print("set map")
                self.connect_text[index].SetLabel(dis_str)
                self.connect_bitmap[index].SetBitmap(bitmap)

    # 更新版本号
    def up_ver_ui(self, ver_str=''):
        self.dev_ver.SetLabel(ver_str)

    # 更新SN号
    def up_sn_ui(self, sn_str=''):
        self.dev_sn.SetLabel(sn_str)


    # wx.Colour(255, 0, 0) 或 wx.RED
    # 绿色: wx.Colour(0, 255, 0) 或 wx.GREEN
    # 蓝色: wx.Colour(0, 0, 255) 或 wx.BLUE
    # 黑色: wx.Colour(0, 0, 0) 或 wx.BLACK
    # 白色: wx.Colour(255, 255, 255) 或 wx.WHITE
    # 更新提示文本,分三行显示，默认显示黑色
    def up_notification_ui(self, first="", second="", third="", color=wx.BLACK):
        self.notification_static_text[0].SetLabel(first)
        self.notification_static_text[0].SetForegroundColour(color)
        self.notification_static_text[1].SetLabel(second)
        self.notification_static_text[1].SetForegroundColour(color)
        self.notification_static_text[2].SetLabel(third)
        self.notification_static_text[2].SetForegroundColour(color)
        self.Layout()                     # 先布局使控件获得正确宽度
        for text in self.notification_static_text:
            text.Wrap(-1)                 # -1 表示使用当前宽度自动换行
        self.Layout()                     # 再次布局适应新高度

    # def up_notification_ui(self, first="", second="", third="", color=wx.BLACK):

    #     self.notification_static_text[0].SetLabel(first)
    #     self.notification_static_text[0].SetForegroundColour(color)
    #     self.notification_static_text[1].SetLabel(second)
    #     self.notification_static_text[1].SetForegroundColour(color)
    #     self.notification_static_text[2].SetLabel(third)
    #     self.notification_static_text[2].SetForegroundColour(color)
    #     self.Layout()  # 刷新布局


    # 更新提示单项
    def up_notification_ui_item(self, num=1, text="", color=wx.BLACK):
        if num > 3 or num < 1:
            return
        index = num - 1
        self.notification_static_text[index].SetLabel(text)
        self.notification_static_text[index].SetForegroundColour(color)
        # self.notification_static_text[index].Refresh()
        self.Layout()  # 刷新布局

    # 设置字体，并加粗 wx.FONTWEIGHT_BOLD
    def up_notification_ui_item_size(self, num=1, size=26):
        if num > 3 or num < 1:
            return
        not_font = wx.Font(size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        index = num - 1
        self.notification_static_text[index].SetFont(not_font)
        self.Layout() # 刷新布局

    def up_layout(self):
        self.Layout()  # 刷新布局

    # 更新测试结果，name :item_result列表中字典的键值如，'led1'
    # result 测试结果，"pass","fail","untested","reset","monitor"
    # [up_test_ui_WBH] value 非空时中间列显示实测值（RV30 实时 0x77）
    def up_test_ui(self, name='', result='', value=''):

        for item in self.test_widget:
            if name == '':
                key = next(iter(item))
                widget_list = item[key]
                widget_list[1].SetLabel("")
                widget_list[1].SetBackgroundColour(wx.Colour("white"))  # 绿色的RGB值
                widget_list[1].Refresh()
                widget_list[2].SetBitmap(get_bitmap("white"))
            elif item.get(name):
                widget_list = item[name]
                if result == "pass":
                    widget_list[1].SetLabel(str(value) if value else "通过")
                    widget_list[1].SetBackgroundColour(wx.Colour("green"))  # 绿色的RGB值
                    widget_list[1].Refresh()
                    widget_list[2].SetBitmap(get_bitmap("green"))
                elif result == "fail":
                    widget_list[1].SetLabel(str(value) if value else "不通过")
                    widget_list[1].SetBackgroundColour(wx.Colour("red"))  # 绿色的RGB值
                    widget_list[1].Refresh()
                    widget_list[2].SetBitmap(get_bitmap("red"))
                elif result == "untested":
                    widget_list[1].SetLabel("未测试")
                    widget_list[1].SetBackgroundColour(wx.Colour("white"))  # 绿色的RGB值
                    widget_list[1].Refresh()
                    widget_list[2].SetBitmap(get_bitmap("white"))
                elif result == "monitor":
                    # [up_test_ui_WBH] yaml 未配置阈值的监视项：只显示数值
                    widget_list[1].SetLabel(str(value) if value else "")
                    widget_list[1].SetBackgroundColour(wx.Colour("white"))
                    widget_list[1].Refresh()
                    widget_list[2].SetBitmap(get_bitmap("white"))
                elif result == "reset":
                    widget_list[1].SetLabel("")
                    widget_list[1].SetBackgroundColour(wx.Colour("white"))  # 绿色的RGB值
                    widget_list[1].Refresh()
                    widget_list[2].SetBitmap(get_bitmap("white"))
                break

    def reset_ui(self):
        self.up_ver_ui()
        self.up_sn_ui()
        self.up_notification_ui()
        self.up_test_ui()

    # test线程消息,字典形式
    def test_thread_msg(self, msg):
        print("rx msg :" + str(msg))


# 获取图标，如果输入参数错误，输出感叹号图标
def get_bitmap(name):
    for item in bitmap_list:
        if item.get(name):
            image = wx.Image(item.get(name), wx.BITMAP_TYPE_ANY).Scale(20, 20)
            return wx.Bitmap(image)
    image = wx.Image("picture/warning.png", wx.BITMAP_TYPE_ANY).Scale(20, 20)
    return wx.Bitmap(image)


# 第四行，网格显示，添加方框，测试项不需要，怎么修改
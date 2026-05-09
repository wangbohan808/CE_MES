import time
from queue import Queue, Empty
import struct


# 休眠时触发条件退出
def conditional_sleep(timeout, condition_check, interval=0.3):
    """自定义条件中断的休眠函数"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition_check():  # 检查条件是否满足
            return True        # 条件满足，提前退出
        time.sleep(interval)  # 短暂休眠（如0.1秒）
    return False              # 超时未满足条件


# 清空队列
def clear_queue(q):
    """清空队列的线程安全方法"""
    while True:
        try:
            q.get_nowait()  # 非阻塞获取元素
            # q.task_done()   # 若之前调用过 join()，需标记任务完成
        except Empty:
            break


# 取 start - end 字段，最低两位，从0开始
def extract_bits(data, start, end):
    mask = (1 << (end - start + 1)) - 1  # 创建掩码
    return (data >> start) & mask


# 检测特定位是否为1
def check_bit(data, n):
    return (data >> n) & 1


# 字节序高位先发，转浮点数

def bytes_to_float(bytes_data):

    # 将字节数组转换为字节串
    byte_string = bytes(bytes_data)

    # 使用 struct 模块解析字节串
    # '>f' 表示高位先发的 4 字节浮点数
    float_value = struct.unpack('>f', byte_string)[0]

    # print(float_value)  # 输出 12.375
    return float_value


# 分隔SN码成 头部和数字部分
def split_sn_barcode(barcode):
    #  从右往左找到第一个非数字字符的位置
    split_index = 0
    for i in range(len(barcode) - 1, -1, -1):
        if not barcode[i].isdigit():
            split_index = i + 1
            break
    # 分割条码
    non_digit_part = barcode[:split_index]
    digit_part = barcode[split_index:]
    return non_digit_part, digit_part


#  求校验和
def check_sum(data):
    ck_sum = 0
    for dat in data:
        ck_sum += dat
    return ck_sum % 256




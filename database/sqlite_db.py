import sqlite3
from datetime import datetime
import os
import csv
from tool_box import tool

db_error_state = ""    # 数据库异常标志
conn = None      # 数据库连接，一次仅支持访问一个数据库
# cursor = None  # 数据库游标，一次仅支持访问一个数据库

# 关于显示提交  conn.commit()
# 1、DDL 操作（如 CREATE TABLE）会隐式提交事务
# 在执行 DDL 语句（例如建表、删表、修改表结构）时，
# 会自动提交当前事务。因此，即使没有显式调用 conn.commit()，表的创建也会立即生效
# 2、DML 操作（如 INSERT, UPDATE, DELETE）需要显式提交
# 如果是数据操作（增删改查），则需要显式调用 conn.commit() 提交事务，否则修改不会持久化到数据库

robot_db_path = 'C:\\CelinkDB\\robot_sn.db'
parts_db_path = 'C:\\CelinkDB\\parts_sn.db'


def open_sn_database(db_type=""):
    global conn

    if db_type == "robot_sn":
        db_path = robot_db_path
    elif db_type == "parts_sn":
        db_path = parts_db_path
    else:
        print("创建数据库异常，未知数据库类型：" + str(db_type))
        return False, "创建数据库异常，未知数据库类型"

    if not os.path.exists(db_path):
        print("数据库文件不存在")
        return False, "指定目录未找到数据库"

    # 连接到SQLite数据库（如果不存在会自动创建）
    conn = sqlite3.connect(db_path)

    # 创建游标对象
    cursor = conn.cursor()
    try:
        # 定义建表 SQL（使用 IF NOT EXISTS 避免重复创建）
        create_table_sql = '''
            CREATE TABLE IF NOT EXISTS sn_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sn TEXT UNIQUE NOT NULL,           -- SN字符串，设置唯一约束
                times TEXT NOT NULL,               -- 时间字符串
                name TEXT,                         -- 名称，描述信息，可以是中文
                box_sn TEXT,                       -- 绑定纸盒SN，多个配件可绑定一个纸盒
                reserved TEXT                      -- 保留字段，方便后面扩展
            )
        '''
        # 执行 SQL 语句
        cursor.execute(create_table_sql)
        print("表格创建成功！")

        # create_db_init(conn)
        return True, "数据库打开成功"
    except sqlite3.Error as e:
        print(f"数据库操作失败: {e}")
        return False, f"数据库操作失败: {e}"
    finally:
        cursor.close()


def is_sn_in_database(sn: str, connect: sqlite3.Connection) -> bool | None:
    global db_error_state
    print("检测sn是否在数据库")
    if is_connection_valid(connect) is False:
        db_error_state = "数据库连接异常"
        print("数据库连接异常")
        return None

    ck_cursor = connect.cursor()
    try:
        ck_cursor.execute("SELECT 1 FROM sn_records WHERE sn = ?", (sn,))
        if ck_cursor.fetchone():
            print(f"SN找到: '{sn}' ")
            return True
        else:
            print(f"SN不存在: SN '{sn}' ")
            return False
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        return None
    finally:
        ck_cursor.close()


def find_record_time_by_sn(connect: sqlite3.Connection, sn: str):
    if is_connection_valid(connect) is False:
        return False, "数据库连接异常"

    cursor = connect.cursor()
    try:
        cursor.execute("SELECT times FROM sn_records WHERE sn = ?", (sn,))
        # 获取结果
        result = cursor.fetchone()  # 返回一个元组（如 (25,)）或 None
        print("找到记录：", end="")
        print(result)
        if result:
            return True, result[0]
        else:
            return False, "未找到记录"
    except sqlite3.Error as e:
        return False, "访问数据库异常"


def add_sn_record(connect: sqlite3.Connection, sns, name="", box_sn=""):

    if is_connection_valid(connect) is False:
        return False

    # 获取当前时间
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(current_time)
    cursor = connect.cursor()
    try:
        # 插入新记录
        for sn in sns:
            cursor.execute('''
            INSERT INTO sn_records (sn, times, name, box_sn)
            VALUES (?, ?, ?, ?)
            ''', (sn, current_time, name, box_sn))
        connect.commit()
        return True
    except sqlite3.Error as e:
        print(f"数据库错误：{e} ")
        connect.rollback()
        return False


def is_connection_valid(connect: sqlite3.Connection) -> bool:
    """验证数据库连接是否有效"""
    if connect is None:
        print("未打开数据库")
        return False
    cursor = connect.cursor()
    try:
        cursor.execute("SELECT 1")
        print("数据库连接成功")
        return True
    except sqlite3.ProgrammingError:
        # 连接已关闭
        print("异常：数据库关闭")
        return False
    except sqlite3.Error as e:
        # 其他数据库错误（如文件被删除、权限问题等）
        print(f"异常：数据库错误 {e}")
        return False
    finally:
        cursor.close()


def fetch_all_records(connect: sqlite3.Connection):
    if is_connection_valid(connect) is True:
        cursor = connect.cursor()
        try:
            # 查询多个列（例如：id, name, email）
            cursor.execute("SELECT id, name, sn, times, box_sn FROM sn_records")
            for row in cursor:
                records_id, name, sn, times, box_sn = row
                print("id:"+str(records_id), "name:"+name, "sn:"+sn, "times: "+times, "box_sn"+box_sn)
        except sqlite3.Error as e:
            print(f"数据库查询异常：{e}")
    else:
        print("查询记录，遍历数据库连接异常")


def create_db_init(connect: sqlite3.Connection):
    cursor = connect.cursor()
    # 读取 CSV 文件
    sn_list = []
    with open('大货订单(1).csv', 'r') as file:
        csv_reader = csv.reader(file)  # 返回一个迭代器
        for row in csv_reader:
            sn_list.append(row[2:])
        start_list = sn_list[1:]
    sn_list_save = []
    for item in start_list:
        # print(item)
        res_start = tool.split_sn_barcode(item[0])
        res_end = tool.split_sn_barcode(item[1])
        res_num = item[2]
        start_part_one = res_start[0]
        start_part_two = res_start[1]
        end_part_one = res_end[0]
        end_part_two = res_end[1]
        # print("one", start_part_one, end_part_one)
        # print("two", start_part_two, end_part_two)
        if start_part_one == end_part_one:
            # print(start_part_one, end_part_one)
            if int(end_part_two) + 1 - int(start_part_two) == int(res_num):
                for i in range(int(res_num)):
                    sn = start_part_one + str(int(start_part_two) + i).zfill(len(start_part_two))
                    # print(sn)
                    sn_list_save.append(sn)
                    # add_sn_record(connect=connect, sn=sn, name="大货SN")
            else:
                print("error num", res_start, res_end, res_num)
        else:
            print("error head", res_start, res_end, res_num)

    # 准备批量数据
    add_sn_record(connect=connect, sns=sn_list_save, name="大货SN", box_sn="")
    fetch_all_records(connect)



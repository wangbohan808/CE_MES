import threading
import time
from myserial import test_serial
from test_tool import test

work_thread = None
serial_thread = None
# 创建一个事件对象，用于通知线程停止
work_stop_event = threading.Event()
serial_stop_event = threading.Event()


def thread_test_running():
    while not work_stop_event.is_set():
        test.test_run_process()
    print("Worker thread stopped.")


def start_work_thread():
    global work_thread
    if work_thread is None or not work_thread.is_alive():
        work_stop_event.clear()
        work_thread = threading.Thread(target=thread_test_running)
        work_thread.start()


def stop_work_thread():
    work_stop_event.set()
    if work_thread is not None:
        work_thread.join()


def thread_serial_running():
    while not work_stop_event.is_set():
        test_serial.test_serial_process()
    print("serial thread stopped.")


def start_serial_thread():
    global serial_thread
    if serial_thread is None or not serial_thread.is_alive():
        serial_stop_event.clear()
        serial_thread = threading.Thread(target=thread_serial_running)
        serial_thread.start()


def stop_serial_thread():
    serial_stop_event.set()
    if serial_thread is not None:
        serial_thread.join()


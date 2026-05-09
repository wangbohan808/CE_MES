import wx
from ui import MainFrame
import mythread


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')
    app = wx.App()

    window = MainFrame.MainFrame(parent=None)
    window.Show()

    app.MainLoop()


# Press the green button in the gutter to run the script.
# 打包指令 pyinstaller --onefile main.py

if __name__ == '__main__':
    print_hi('海能机器人')


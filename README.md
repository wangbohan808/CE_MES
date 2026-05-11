# test_fixture_software

## Python 环境

本项目当前使用的虚拟环境（`.venv`）基于以下 Python 版本创建：

| 项目 | 值 |
|------|-----|
| Python 版本 | **3.11.7** |
| 创建命令参考 | `python -m venv .venv`（建议使用与本环境一致的 **Python 3.11.x**） |

若尚未创建虚拟环境，可在项目根目录执行：

```powershell
python -m venv .venv
```

激活虚拟环境（PowerShell）：

```powershell
.\.venv\Scripts\Activate.ps1
```

## pip 全局使用清华源（可选）

将 pip 默认索引设为清华大学 PyPI 镜像，**只需配置一次**，之后在本机任意虚拟环境中使用 `pip install` 都会优先走该源：

```powershell
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

若遇到 HTTPS 证书校验相关报错，可额外设置信任主机（按需）：

```powershell
pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn
```

查看当前 pip 配置是否生效：

```powershell
pip config list
```

## 一键安装依赖

在项目根目录下，**激活 `.venv` 后**执行：

```powershell
pip install -r requirements.txt
```

若不想先手动激活，可用虚拟环境内的解释器一条命令安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

（首次使用前请确保已创建 `.venv`，且该目录下的 Python 与依赖兼容；推荐使用 Python **3.11.x**。）

## 运行入口

```powershell
python main.py
```

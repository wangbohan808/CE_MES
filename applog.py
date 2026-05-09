import os
import logging
import logging.handlers
from datetime import datetime


log_file = 'logs/app.log'    # 日志文件路径
backup_count = 1             # 备份文件数量
max_size_mb = 10             # 单个日志文件最大大小(MB)

# 设置默认日志格式
# asc time 时间戳；name 日志记录器名称；level name 日志级别；message 消息
# 其他配置 %(filename)s：生成日志的文件名
# %(funcName)s：生成日志的函数名， %(lineno)d：生成日志的代码行号 等等
log_format = '%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s'


class AppLog:
    """高级日志记录器，支持多级别日志、文件轮转和控制台输出"""

    def __init__(self, name="AppLog", level=logging.INFO):
        """
        初始化日志记录器
        :param name: 日志记录器名称
        :param level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        # 创建日志记录器
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.log_file = log_file

        # 确保目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        formatter = logging.Formatter(log_format)

        # 创建文件处理器（带轮转功能）
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_size_mb * 1024 * 1024,  # 转换为字节
            backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def get_logger(self):
        """获取日志记录器实例"""
        return self.logger

    def set_level(self, level):
        """设置日志记录级别"""
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)



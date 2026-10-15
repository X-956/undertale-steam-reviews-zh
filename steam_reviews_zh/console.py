"""让中文日志兼容 Windows 管道、旧终端和重定向输出。"""

import sys


def configure_console():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")


def print_message(message):
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    text = str(message).encode(encoding, errors="backslashreplace").decode(encoding)
    print(text, file=stream, flush=True)

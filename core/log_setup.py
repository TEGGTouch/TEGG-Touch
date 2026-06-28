"""
TEGG Touch (PyQt6) - core/log_setup.py
日志初始化 + 异常钩子 + 诊断辅助。

每次启动写新的会话日志: logs/teggtouch-YYYYMMDD-HHMMSS.log (UTF-8)
保留最近 N 次会话, 超出自动删除。
全局异常 (Python + Qt) 自动写入当前会话日志。
"""

import logging
import os
import sys
import traceback
import platform
import datetime
import glob

# ── 配置 ──
KEEP_SESSIONS = 10                            # 保留最近 N 次会话日志
LOGS_DIR_NAME = 'logs'
LOG_FILENAME_FMT = 'teggtouch-{ts}.log'       # ts = YYYYMMDD-HHMMSS
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

_session_log_path: str | None = None
_logs_dir: str | None = None


def _app_dir() -> str:
    """exe 所在目录 (frozen) / 项目根 (dev)。与 constants.APP_DIR 同口径，
    但在此就地计算，避免底层日志模块反向依赖 constants (它会拉起 i18n)。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _logs_root() -> str:
    """日志根目录: exe 所在目录下 logs/ (绝对路径, 不依赖 CWD)"""
    global _logs_dir
    if _logs_dir is None:
        _logs_dir = os.path.join(_app_dir(), LOGS_DIR_NAME)
        os.makedirs(_logs_dir, exist_ok=True)
    return _logs_dir


def get_session_log_path() -> str | None:
    """返回当前会话的日志文件路径 (setup_logging 调用后才有值)"""
    return _session_log_path


def list_recent_log_paths(n: int = KEEP_SESSIONS) -> list[str]:
    """返回最近 n 个会话日志路径 (按 mtime 倒序, 当前会话排第一)"""
    root = _logs_root()
    paths = glob.glob(os.path.join(root, 'teggtouch-*.log'))
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths[:n]


def cleanup_old_logs(keep: int = KEEP_SESSIONS):
    """删除超出保留数的旧日志文件"""
    paths = list_recent_log_paths(n=10000)   # 取全部
    for old in paths[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass


def _format_env_report() -> str:
    """生成环境快照字符串 (写入日志头, 也用于诊断报告)"""
    lines = ['===== TEGG Touch Session =====']
    try:
        from core.constants import APP_VERSION
        lines.append(f'App version : {APP_VERSION}')
    except Exception:
        pass
    lines.append(f'Time        : {datetime.datetime.now().isoformat(timespec="seconds")}')
    lines.append(f'OS          : {platform.system()} {platform.release()} '
                 f'({platform.version()})')
    lines.append(f'Arch        : {platform.machine()}')
    lines.append(f'Python      : {sys.version.split()[0]} ({sys.executable})')
    lines.append(f'CWD         : {os.getcwd()}')
    lines.append(f'Frozen      : {bool(getattr(sys, "frozen", False))}')
    try:
        import ctypes
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        is_admin = '?'
    lines.append(f'Admin       : {is_admin}')

    # 屏幕 (尝试用 Qt 取; 没初始化时跳过)
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            screens = []
            for s in app.screens():
                g = s.geometry()
                screens.append(f'{g.width()}x{g.height()}@{s.logicalDotsPerInch():.0f}dpi')
            lines.append(f'Screens     : {", ".join(screens) or "(none)"}')
    except Exception:
        pass

    # 依赖版本 (失败安静跳过)
    for mod_name in ('PyQt6.QtCore', 'sounddevice', 'vosk', 'keyboard', 'PIL'):
        try:
            mod = __import__(mod_name, fromlist=['*'])
            ver = getattr(mod, '__version__',
                          getattr(mod, 'PYQT_VERSION_STR', None)) or '?'
            lines.append(f'{mod_name:12s}: {ver}')
        except Exception:
            pass

    lines.append('=' * 32)
    return '\n'.join(lines)


def _new_session_log_path() -> str:
    """生成新的会话日志文件路径 (含当前时间戳)"""
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    return os.path.join(_logs_root(), LOG_FILENAME_FMT.format(ts=ts))


def setup_logging(debug: bool = False) -> str:
    """初始化日志系统。返回当前会话日志路径。

    - 创建 logs/ 目录
    - 新建会话文件 (UTF-8, 不覆盖已有)
    - 清理超出 KEEP_SESSIONS 的旧日志
    - 把环境报告写入日志头
    - 替换 root logger 的 handler (移除 basicConfig 之前的)
    """
    global _session_log_path
    _session_log_path = _new_session_log_path()

    level = logging.DEBUG if debug else logging.INFO

    root = logging.getLogger()
    # 移除之前的 handlers (避免重复输出)
    for h in list(root.handlers):
        root.removeHandler(h)

    fh = logging.FileHandler(_session_log_path, mode='w', encoding='utf-8')
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(fh)
    root.setLevel(level)

    # 控制台同步 (开发环境可见)
    try:
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(level)
        sh.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(sh)
    except Exception:
        pass

    # 环境报告写入日志头
    try:
        with open(_session_log_path, 'a', encoding='utf-8') as f:
            f.write(_format_env_report() + '\n')
    except Exception:
        pass

    cleanup_old_logs(KEEP_SESSIONS)
    return _session_log_path


def install_excepthook():
    """安装全局异常钩子: Python 未捕获异常 + Qt 警告/错误 → 日志。"""
    logger = logging.getLogger('uncaught')

    # Python 端
    def _py_excepthook(exc_type, exc_value, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, tb)
            return
        msg = ''.join(traceback.format_exception(exc_type, exc_value, tb))
        logger.critical('UNCAUGHT EXCEPTION:\n%s', msg)
        sys.__excepthook__(exc_type, exc_value, tb)

    sys.excepthook = _py_excepthook

    # Qt 端
    try:
        from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
        qt_logger = logging.getLogger('Qt')

        def _qt_handler(mode, ctx, message):
            level_map = {
                QtMsgType.QtDebugMsg: logging.DEBUG,
                QtMsgType.QtInfoMsg: logging.INFO,
                QtMsgType.QtWarningMsg: logging.WARNING,
                QtMsgType.QtCriticalMsg: logging.ERROR,
                QtMsgType.QtFatalMsg: logging.CRITICAL,
            }
            lvl = level_map.get(mode, logging.INFO)
            loc = ''
            if ctx and ctx.file:
                loc = f' [{ctx.file}:{ctx.line}]'
            qt_logger.log(lvl, '%s%s', message, loc)
        qInstallMessageHandler(_qt_handler)
    except Exception:
        pass

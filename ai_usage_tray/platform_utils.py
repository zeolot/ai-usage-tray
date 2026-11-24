# -*- coding: utf-8 -*-
"""Cross-platform helpers for Windows 10/11 and Linux (UOS/Deepin) taskbars."""

import os
import sys
from typing import Optional

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
APP_ID = "ai.usage.tray"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_RUN_VALUE = "AIUsageTray"
WINDOWS_MUTEX_NAME = "Local\\AIUsageTraySingleInstance"


def get_project_root():
    # type: () -> str
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_dir():
    # type: () -> str
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ai-usage-tray")
    return os.path.expanduser("~/.config/ai-usage-tray")


def get_cache_dir():
    # type: () -> str
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or os.path.expanduser("~")
        return os.path.join(base, "ai-usage-tray")
    return os.path.expanduser("~/.cache/ai-usage-tray")


def get_codex_sessions_dir():
    # type: () -> str
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return os.path.join(os.path.expanduser(codex_home), "sessions")
    return os.path.join(os.path.expanduser("~"), ".codex", "sessions")


def get_antigravity_brain_dir():
    # type: () -> str
    ag_home = os.environ.get("ANTIGRAVITY_HOME")
    if ag_home:
        return os.path.join(os.path.expanduser(ag_home), "brain")
    return os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain")


def setup_windows_app_id():
    # type: () -> None
    """Set Windows AppUserModelID so taskbar & notifications group cleanly."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def _get_windows_autostart_command():
    # type: () -> str
    if getattr(sys, "frozen", False):
        return '"{}"'.format(os.path.abspath(sys.executable))
    py_dir = os.path.dirname(os.path.abspath(sys.executable))
    pythonw = os.path.join(py_dir, "pythonw.exe")
    exe = pythonw if os.path.isfile(pythonw) else sys.executable
    entry = os.path.join(get_project_root(), "run.pyw")
    if not os.path.isfile(entry):
        entry = os.path.join(get_project_root(), "run.py")
    return '"{}" "{}"'.format(exe, entry)


def _get_linux_autostart_file():
    # type: () -> str
    return os.path.expanduser("~/.config/autostart/ai-usage-tray.desktop")


def is_autostart_enabled():
    # type: () -> bool
    if IS_WINDOWS:
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ
            )
            try:
                val, _ = winreg.QueryValueEx(key, WINDOWS_RUN_VALUE)
                return bool(val)
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False
    return os.path.isfile(_get_linux_autostart_file())


def set_autostart(enabled):
    # type: (bool) -> bool
    if IS_WINDOWS:
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
            )
            try:
                if enabled:
                    cmd = _get_windows_autostart_command()
                    winreg.SetValueEx(key, WINDOWS_RUN_VALUE, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, WINDOWS_RUN_VALUE)
                    except FileNotFoundError:
                        pass
                return True
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    # Linux (UOS / Deepin / GNOME / KDE XDG autostart)
    autostart_file = _get_linux_autostart_file()
    try:
        if enabled:
            os.makedirs(os.path.dirname(autostart_file), exist_ok=True)
            root = get_project_root()
            launch_script = os.path.join(root, "launch.sh")
            icon_path = os.path.join(root, "assets", "icon.png")
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=AI 用量统计\n"
                "Name[en]=AI Usage Monitor\n"
                "Comment=统计 Codex 与 Antigravity 的模型、Token 与生成速度\n"
                "Icon={}\n"
                "Exec=/bin/bash \"{}\"\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
                "X-Deepin-Autostart=true\n"
            ).format(icon_path, launch_script)
            with open(autostart_file, "w", encoding="utf-8") as fh:
                fh.write(content)
        else:
            if os.path.isfile(autostart_file):
                os.remove(autostart_file)
        return True
    except OSError:
        return False


class SingleInstanceLock(object):
    """Cross-platform single-instance lock (Windows Named Mutex / Unix flock)."""

    def __init__(self, lock_path=None):
        # type: (Optional[str]) -> None
        self.lock_path = lock_path or os.path.join(get_cache_dir(), "app.lock")
        self._fp = None
        self._win_mutex = None

    def acquire(self):
        # type: () -> bool
        if IS_WINDOWS:
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.CreateMutexW(None, False, WINDOWS_MUTEX_NAME)
                if not handle:
                    return True
                # ERROR_ALREADY_EXISTS = 183
                if kernel32.GetLastError() == 183:
                    kernel32.CloseHandle(handle)
                    return False
                self._win_mutex = handle
                return True
            except Exception:
                return True

        try:
            import fcntl
            os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
            self._fp = open(self.lock_path, "w")
            fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fp.write(str(os.getpid()))
            self._fp.flush()
            return True
        except Exception:
            if self._fp:
                try:
                    self._fp.close()
                except Exception:
                    pass
                self._fp = None
            return False

    def release(self):
        # type: () -> None
        if IS_WINDOWS:
            if self._win_mutex:
                try:
                    import ctypes
                    ctypes.windll.kernel32.CloseHandle(self._win_mutex)
                except Exception:
                    pass
                self._win_mutex = None
            return

        if self._fp:
            try:
                import fcntl
                fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
                self._fp.close()
            except Exception:
                pass
            self._fp = None

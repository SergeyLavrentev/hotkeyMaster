import glob
import os
import subprocess
import sys

class AutoLaunchManager:
    """
    Управляет автозапуском приложения через LaunchAgents (plist в ~/Library/LaunchAgents)
    """
    LABEL = "com.slavrentev.hotkeymaster"
    PLIST_FILENAME = f"{LABEL}.plist"
    LAUNCH_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")
    PLIST_PATH = os.path.join(LAUNCH_AGENTS_DIR, PLIST_FILENAME)

    @staticmethod
    def get_executable_path():
        return os.path.abspath(sys.argv[0])

    @classmethod
    def get_plist_content(cls, exec_path=None):
        if exec_path is None:
            exec_path = cls.get_executable_path()
        workdir = os.path.dirname(exec_path)
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{cls.LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exec_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>{workdir}</string>
    <key>StandardOutPath</key>
    <string>/tmp/hotkeymaster.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/hotkeymaster.err</string>
</dict>
</plist>
'''

    @classmethod
    def find_preferred_executable(cls):
        # 1. Ищем .app bundle (если есть)
        app_candidates = glob.glob(os.path.expanduser('~/Applications/HotkeyMaster.app'))
        app_candidates += glob.glob(os.path.join(os.path.dirname(__file__), 'build', 'hotkeymaster', 'HotkeyMaster'))
        # Можно добавить другие пути поиска, если нужно
        for path in app_candidates:
            if os.path.exists(path):
                return path
        # Fallback: текущий исполняемый файл
        return cls.get_executable_path()

    @classmethod
    def enable_autolaunch(cls):
        os.makedirs(cls.LAUNCH_AGENTS_DIR, exist_ok=True)
        exec_path = cls.find_preferred_executable()
        plist_content = cls.get_plist_content(exec_path=exec_path)
        with open(cls.PLIST_PATH, "w") as f:
            f.write(plist_content)
        subprocess.run(["launchctl", "unload", cls.PLIST_PATH], stderr=subprocess.DEVNULL)
        subprocess.run(["launchctl", "load", cls.PLIST_PATH])

    @classmethod
    def disable_autolaunch(cls):
        if os.path.exists(cls.PLIST_PATH):
            subprocess.run(["launchctl", "unload", cls.PLIST_PATH], stderr=subprocess.DEVNULL)
            os.remove(cls.PLIST_PATH)

    @classmethod
    def is_autolaunch_enabled(cls):
        return os.path.exists(cls.PLIST_PATH)

# Пример использования:
# AutoLaunchManager.enable_autolaunch()  # включить автозапуск
# AutoLaunchManager.disable_autolaunch() # выключить автозапуск
# AutoLaunchManager.is_autolaunch_enabled() # проверить статус

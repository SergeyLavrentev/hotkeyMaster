import sys
import threading
from AppKit import NSStatusBar, NSVariableStatusItemLength, NSMenu, NSMenuItem, NSApplication, NSImage
from Foundation import NSObject, NSLog
from objc import selector, super
from pynput import keyboard
import threading
import signal
import subprocess
import os
import json
import pystray
from PIL import Image, ImageDraw
import logging
from ui import show_settings_window
import Quartz


HOTKEYS_FILE = 'hotkeys.json'
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('hotkeymaster')

def load_hotkeys():
    try:
        with open(HOTKEYS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_hotkeys(hotkeys):
    with open(HOTKEYS_FILE, 'w', encoding='utf-8') as f:
        json.dump(hotkeys, f, ensure_ascii=False, indent=2)

def on_hotkey():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    QtWidgets.QMessageBox.information(None, 'Hotkey', 'Глобальный хоткей Option+T сработал!')

def start_hotkey_listener():
    COMBO = {keyboard.Key.alt, keyboard.KeyCode.from_char('t')}
    current = set()
    def on_press(key):
        if key in COMBO or (hasattr(key, 'char') and key.char and key.char.lower() == 't'):
            current.add(key)
            if all(k in current or (k == keyboard.KeyCode.from_char('t') and keyboard.KeyCode.from_char('t') in current) for k in COMBO):
                on_hotkey()
    def on_release(key):
        if key in current:
            current.remove(key)
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()

# Глобальные переменные для хранения хоткеев (заглушка)
hotkeys = {}
_hotkey_listeners = []

def unregister_hotkeys():
    global _hotkey_listeners
    for listener in _hotkey_listeners:
        listener.stop()
    _hotkey_listeners = []

def get_active_app_name():
    # Получить имя активного приложения через Quartz
    ws = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    for w in ws:
        if w.get('kCGWindowLayer') == 0 and w.get('kCGWindowOwnerName'):
            return w['kCGWindowOwnerName']
    return None

def run_action(action):
    logger.debug(f'Выполнение действия: {action}')
    if action.startswith('message:'):
        msg = action[len('message:'):]
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        QtWidgets.QMessageBox.information(None, 'Hotkey', msg)
    elif action.startswith('open '):
        url = action[len('open '):].strip()
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url
        logger.debug(f'Открываю URL: {url}')
        import webbrowser
        webbrowser.open(url)
    elif action.startswith('run '):
        cmd = action[len('run '):].strip()
        logger.debug(f'Запускаю команду: {cmd}')
        import subprocess
        try:
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            logger.error(f'Ошибка запуска команды: {e}')
    else:
        logger.debug(f'Неизвестное действие: {action}')

def parse_combo(combo):
    # combo — это dict: {'mods': [...], 'vk': int, 'disp': ...}
    if isinstance(combo, dict):
        mods = set(combo.get('mods', []))
        vk = combo.get('vk')
        return (frozenset(mods), vk)
    # для обратной совместимости со старыми строками
    return (frozenset(), None)

def register_hotkeys():
    unregister_hotkeys()
    hotkeys = load_hotkeys()
    logger.debug(f'Регистрируем хоткеи: {hotkeys}')
    for hk in hotkeys:
        mods, vk = parse_combo(hk.get('combo', {}))
        action = hk.get('action', '')
        scope = hk.get('scope', 'global')
        app_name = hk.get('app', '')
        current_mods = set()
        def make_on_press(mods, vk, action, scope, app_name):
            def on_press(key):
                key_vk = getattr(key, 'vk', None)
                logger.debug(f'[HOTKEY DEBUG] on_press вызван: key={key}, vk={key_vk}, current_mods={current_mods}, mods={mods}, vk_target={vk}')
                # Модификаторы
                if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                    current_mods.add('Ctrl')
                if key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                    current_mods.add('Alt')
                if key == keyboard.Key.shift or key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                    current_mods.add('Shift')
                if key == keyboard.Key.cmd or key == keyboard.Key.cmd_l or key == keyboard.Key.cmd_r:
                    current_mods.add('Cmd')
                # Проверяем хоткей по vk и модификаторам
                if vk is not None and key_vk == vk and mods.issubset(current_mods):
                    # Проверка области действия
                    if scope == 'app' and app_name:
                        active_app = get_active_app_name()
                        logger.debug(f'Требуется фокус приложения: {app_name}, сейчас активно: {active_app}')
                        if active_app and app_name not in active_app:
                            return
                    logger.debug(f'Хоткей сработал: {hk.get("combo", {})}')
                    run_action(action)
            return on_press
        def make_on_release():
            def on_release(key):
                if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                    current_mods.discard('Ctrl')
                if key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                    current_mods.discard('Alt')
                if key == keyboard.Key.shift or key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                    current_mods.discard('Shift')
                if key == keyboard.Key.cmd or key == keyboard.Key.cmd_l or key == keyboard.Key.cmd_r:
                    current_mods.discard('Cmd')
            return on_release
        logger.debug(f'[HOTKEY DEBUG] Стартую Listener для vk={vk}, mods={mods}, scope={scope}, app={app_name}')
        listener = keyboard.Listener(on_press=make_on_press(mods, vk, action, scope, app_name), on_release=make_on_release())
        listener.daemon = True
        listener.start()
        _hotkey_listeners.append(listener)

# Класс для обработки событий меню трея
class TrayDelegate(NSObject):
    def show_settings_(self, sender):
        open_settings_window()
    show_settings_ = selector(show_settings_, signature=b'v@:@')

    def quit_(self, sender):
        NSApplication.sharedApplication().terminate_(self)
    quit_ = selector(quit_, signature=b'v@:@')

    def validateMenuItem_(self, item):
        return True

def open_settings_window():
    subprocess.Popen([sys.executable, os.path.abspath(__file__), '--settings'])

def hotkey_thread_func():
    last_mtime = None
    while True:
        try:
            mtime = os.path.getmtime(HOTKEYS_FILE)
            if last_mtime is None or mtime != last_mtime:
                logger.debug('hotkeys.json изменён, перерегистрирую хоткеи')
                register_hotkeys()
                last_mtime = mtime
        except Exception as e:
            logger.debug(f'Ошибка проверки hotkeys.json: {e}')
        threading.Event().wait(1)

tray_delegate = None  # глобальная переменная для хранения делегата

def create_tray():
    def on_settings(icon, item):
        logger.debug('Открытие окна настроек')
        open_settings_window()
    def on_quit(icon, item):
        logger.debug('Выход через меню трея')
        icon.stop()
        os._exit(0)
    # Более заметная иконка: белый круг с чёрной рамкой и символом
    size = 64
    image = Image.new('RGBA', (size, size), (255, 255, 255, 255))
    d = ImageDraw.Draw(image)
    d.ellipse((0, 0, size-1, size-1), fill=(255,255,255,255), outline=(0,0,0,255), width=3)
    d.text((size//4, size//4), '⌨️', fill=(0, 0, 0, 255))
    menu = pystray.Menu(
        pystray.MenuItem('Настройки', on_settings),
        pystray.MenuItem('Выход', on_quit)
    )
    icon = pystray.Icon('HotkeyMaster', image, 'HotkeyMaster', menu)
    icon.run()

def check_accessibility():
    try:
        import Quartz
        if Quartz.CGPreflightListenEventAccess():
            logger.debug("Есть права Universal Access (Accessibility)")
            return True
        else:
            logger.debug("Нет прав Universal Access (Accessibility)")
            return False
    except Exception as e:
        logger.debug(f"Ошибка проверки прав: {e}")
        return False

def show_accessibility_warning():
    logger.debug('Показываю окно с инструкцией по выдаче прав Universal Access')
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    msg = QtWidgets.QMessageBox()
    msg.setIcon(QtWidgets.QMessageBox.Warning)
    msg.setWindowTitle("Требуется доступ")
    msg.setText(
        "Для работы глобальных хоткеев нужно разрешить доступ к управлению компьютером.\n\n"
        "1. Откройте: Системные настройки → Конфиденциальность и безопасность → Универсальный доступ\n"
        "2. Добавьте Terminal или Python и поставьте галочку.\n\n"
        "После этого перезапустите программу."
    )
    btn = msg.addButton("Открыть настройки", QtWidgets.QMessageBox.AcceptRole)
    msg.addButton("Закрыть", QtWidgets.QMessageBox.RejectRole)
    msg.exec_()
    if msg.clickedButton() == btn:
        logger.debug('Открываю настройки Universal Access через open ...')
        import subprocess
        subprocess.Popen(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'])

if __name__ == '__main__':
    if '--settings' in sys.argv:
        from PyQt5 import QtWidgets, QtCore
        if not check_accessibility():
            show_accessibility_warning()
            sys.exit(1)
        show_settings_window(load_hotkeys, save_hotkeys)
        sys.exit(0)
    else:
        if not check_accessibility():
            show_accessibility_warning()
            sys.exit(1)
        # Трей в главном потоке, хоткей-листенер — в отдельном
        hk_thread = threading.Thread(target=hotkey_thread_func, daemon=True)
        hk_thread.start()
        create_tray()
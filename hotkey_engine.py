import json
import logging
import threading
import Quartz
from PyQt5 import QtWidgets
import sys, os
import ctypes, ctypes.util
from Quartz import CGMainDisplayID
import platform  
import subprocess  # для coredisplay_helper

logger = logging.getLogger('hotkeymaster')

# Используем Application Support для хранения настроек
APP_SUPPORT_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'HotkeyMaster')
os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
HOTKEYS_FILE = os.path.join(APP_SUPPORT_DIR, 'hotkeys.json')

# --- Работа с хоткеями ---
def load_hotkeys():
    try:
        with open(HOTKEYS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        with open(HOTKEYS_FILE, 'w', encoding='utf-8') as f:
            f.write('[]')
        return []
    except json.JSONDecodeError:
        return []

def save_hotkeys(hotkeys):
    with open(HOTKEYS_FILE, 'w', encoding='utf-8') as f:
        json.dump(hotkeys, f, ensure_ascii=False, indent=2)

def get_hotkey_key(hk):
    hk_type = hk.get('type', 'keyboard')
    if hk_type == 'keyboard':
        combo = hk.get('combo', {})
        mods, vk = parse_combo(combo)
        return (hk_type, vk, frozenset(mods or []), hk.get('scope', 'global'), hk.get('app', ''))
    elif hk_type == 'trackpad':
        return (hk_type, hk.get('gesture', ''), hk.get('scope', 'global'), hk.get('app', ''))
    return None

def parse_combo(combo):
    if isinstance(combo, dict):
        mods = set(combo.get('mods', []))
        vk = combo.get('vk')
        return (frozenset(mods), vk)
    return (frozenset(), None)

def get_active_app_name():
    ws = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    for w in ws:
        if w.get('kCGWindowLayer') == 0 and w.get('kCGWindowOwnerName'):
            return w['kCGWindowOwnerName']
    return None

def run_action(action):
    import subprocess  # явный импорт для корректного обращения внутри функции
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
        try:
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            logger.error(f'Ошибка запуска команды: {e}')
    elif action.startswith('hotkey:'):
        import json
        try:
            combo = json.loads(action[7:])
            mods = set(combo.get('mods', []))
            vk = combo.get('vk')
            from Quartz import (
                CGEventCreateKeyboardEvent, CGEventSetFlags,
                CGEventPost, kCGHIDEventTap, kCGEventFlagMaskCommand,
                kCGEventFlagMaskShift, kCGEventFlagMaskAlternate, kCGEventFlagMaskControl
            )
            flags = 0
            if 'Cmd' in mods:
                flags |= kCGEventFlagMaskCommand
            if 'Shift' in mods:
                flags |= kCGEventFlagMaskShift
            if 'Alt' in mods:
                flags |= kCGEventFlagMaskAlternate
            if 'Ctrl' in mods:
                flags |= kCGEventFlagMaskControl
            for down in (True, False):
                ev = CGEventCreateKeyboardEvent(None, vk, down)
                CGEventSetFlags(ev, flags)
                CGEventPost(kCGHIDEventTap, ev)
        except Exception as e:
            logger.error(f'Ошибка эмуляции хоткея: {e}')
    elif action.startswith('brightness_set '):
        try:
            percent = int(action.split()[1])
            val = max(0.0, min(1.0, percent / 100.0))
            # Если есть скомпилированный хелпер, используем его на Apple Silicon
            helper = os.path.join(os.path.dirname(__file__), 'coredisplay_helper')
            if os.path.exists(helper) and os.access(helper, os.X_OK):
                subprocess.run([helper, str(val)], check=True)
                return
            # Если приватный CoreDisplay API загружен, вызываем напрямую
            if CoreDisplay_Display_SetUserBrightness:
                disp = CGMainDisplayID()
                res = CoreDisplay_Display_SetUserBrightness(disp, ctypes.c_float(val))
                if res != 0:
                    logger.error(f'Ошибка установки яркости via CoreDisplay: {res}')
                return
            # Fallback: IOKit + CoreFoundation
            set_display_brightness(val)
        except Exception as e:
            logger.error(f'Ошибка установки яркости: {e}')
    elif action == 'brightness_up':
        try:
            cur = get_display_brightness()
            new_val = min(1.0, cur + 0.1)
            helper = os.path.join(os.path.dirname(__file__), 'coredisplay_helper')
            if os.path.exists(helper) and os.access(helper, os.X_OK):
                subprocess.run([helper, str(new_val)], check=True)
                return
            if CoreDisplay_Display_SetUserBrightness:
                disp = CGMainDisplayID()
                res = CoreDisplay_Display_SetUserBrightness(disp, ctypes.c_float(new_val))
                if res != 0:
                    logger.error(f'Ошибка увеличения яркости via CoreDisplay: {res}')
                return
            set_display_brightness(new_val)
        except Exception as e:
            logger.error(f'Ошибка увеличения яркости: {e}')
    elif action == 'brightness_down':
        try:
            cur = get_display_brightness()
            new_val = max(0.0, cur - 0.1)
            helper = os.path.join(os.path.dirname(__file__), 'coredisplay_helper')
            if os.path.exists(helper) and os.access(helper, os.X_OK):
                subprocess.run([helper, str(new_val)], check=True)
                return
            if CoreDisplay_Display_SetUserBrightness:
                disp = CGMainDisplayID()
                res = CoreDisplay_Display_SetUserBrightness(disp, ctypes.c_float(new_val))
                if res != 0:
                    logger.error(f'Ошибка уменьшения яркости via CoreDisplay: {res}')
                return
            set_display_brightness(new_val)
        except Exception as e:
            logger.error(f'Ошибка уменьшения яркости: {e}')
    else:
        logger.debug(f'Неизвестное действие: {action}')

# --- Quartz глобальный слушатель ---
def start_quartz_hotkey_listener():
    import Quartz
    import AppKit
    from PyQt5.QtCore import QCoreApplication
    MODS_MAP = {
        Quartz.kCGEventFlagMaskCommand: 'Cmd',
        Quartz.kCGEventFlagMaskShift: 'Shift',
        Quartz.kCGEventFlagMaskAlternate: 'Alt',
        Quartz.kCGEventFlagMaskControl: 'Ctrl',
    }
    def get_mods_from_flags(flags):
        mods = set()
        for mask, name in MODS_MAP.items():
            if flags & mask:
                mods.add(name)
        return mods
    def event_callback(proxy, type_, event, refcon):
        if type_ != Quartz.kCGEventKeyDown:
            return event
        vk = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        mods = get_mods_from_flags(flags)
        logger.debug(f"CGEventTap: vk={vk}, mods={mods}")  # Логируем все нажатия
        # Отсекаем отключённые хоткеи
        hotkeys = [hk for hk in load_hotkeys() if hk.get('enabled', True)]
        for hk in hotkeys:
            if hk.get('type') != 'keyboard':
                continue
            combo = hk.get('combo', {})
            hk_mods = set(combo.get('mods', []))
            hk_vk = combo.get('vk')
            logger.debug(f"Сравниваем с хоткеем: vk={hk_vk}, mods={hk_mods}, disp={combo.get('disp')}")
            if hk_vk is None:
                continue
            if vk == hk_vk and hk_mods.issubset(mods):
                scope = hk.get('scope', 'global')
                app = hk.get('app', '')
                if scope == 'app' and app:
                    active_app = get_active_app_name()
                    if not active_app or app not in active_app:
                        continue
                logger.info(f'Hotkey triggered (Quartz): {combo.get("disp", str(hk))}')
                run_action(hk.get('action', ''))
                break
        return event
    def run_event_loop():
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGHIDEventTap,  # use HID tap for global key events
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            event_callback,
            None
        )
        if not tap:
            logger.error('Не удалось создать CGEventTap. Проверьте права Accessibility!')
            return
        run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(loop, run_loop_source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        logger.info('Quartz hotkey listener started.')
        Quartz.CFRunLoopRun()
    threading.Thread(target=run_event_loop, name="QuartzHotkeyThread", daemon=True).start()

# --- Добавлено: API управления яркостью на Apple Silicon через CoreDisplay ---
_core_display = None
CoreDisplay_Display_SetUserBrightness = None
try:
    # Попыток через PyObjC
    import CoreDisplay as _cd
    CoreDisplay_Display_SetUserBrightness = _cd.CoreDisplay_Display_SetUserBrightness
    logger.info('Loaded CoreDisplay via PyObjC')
except ImportError:
    # Fallback: поиск через ctypes.util
    _lib = ctypes.util.find_library('CoreDisplay')
    if _lib:
        try:
            _core_display = ctypes.cdll.LoadLibrary(_lib)
            CoreDisplay_Display_SetUserBrightness = getattr(_core_display, 'CoreDisplay_Display_SetUserBrightness', None)
            if CoreDisplay_Display_SetUserBrightness:
                CoreDisplay_Display_SetUserBrightness.argtypes = [ctypes.c_uint32, ctypes.c_float]
                CoreDisplay_Display_SetUserBrightness.restype = ctypes.c_int
                logger.info(f'Loaded CoreDisplay via ctypes.util.find_library: {_lib}')
        except Exception as e:
            logger.warning(f'Ошибка загрузки CoreDisplay из {_lib}: {e}')
    # Fallback явные пути
    possible_paths = [
        '/System/Library/PrivateFrameworks/CoreDisplay.framework/CoreDisplay',
        '/System/Library/PrivateFrameworks/CoreDisplay.framework/Versions/A/CoreDisplay',
    ]
    for pd in possible_paths:
        if os.path.exists(pd):
            try:
                _core_display = ctypes.cdll.LoadLibrary(pd)
                CoreDisplay_Display_SetUserBrightness = getattr(_core_display, 'CoreDisplay_Display_SetUserBrightness', None)
                if CoreDisplay_Display_SetUserBrightness:
                    CoreDisplay_Display_SetUserBrightness.argtypes = [ctypes.c_uint32, ctypes.c_float]
                    CoreDisplay_Display_SetUserBrightness.restype = ctypes.c_int
                    logger.info(f'Loaded CoreDisplay from {pd}')
                    break
            except Exception as e:
                logger.warning(f'Ошибка загрузки CoreDisplay из {pd}: {e}')
    else:
        if CoreDisplay_Display_SetUserBrightness is None:
            logger.warning('CoreDisplay framework not found in expected locations')
except Exception as e:
    logger.warning(f'Ошибка загрузки CoreDisplay framework: {e}')

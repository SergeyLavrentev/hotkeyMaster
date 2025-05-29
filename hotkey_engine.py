import sys # Добавляем импорт sys
import os # Убедимся, что os импортирован
import subprocess # Убедимся, что subprocess импортирован
import logging # Убедимся, что logging импортирован
import ctypes # Убедимся, что ctypes импортирован
import threading # Добавляем импорт threading
import json # Добавляем импорт json
import time # Добавляем импорт time
import Quartz
from PyQt5 import QtWidgets
from Quartz import CGMainDisplayID, CGEventPost, kCGHIDEventTap, CGEventCreateKeyboardEvent, CGEventSetFlags, kCGEventFlagMaskShift, kCGEventFlagMaskControl, kCGEventFlagMaskAlternate, kCGEventFlagMaskCommand

logger = logging.getLogger(__name__)

# --- Определяем путь к хелперу ---
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Запущено как собранное приложение (.app)
    # Хелпер ожидается рядом с исполняемым файлом в Contents/MacOS
    helper_base_path = os.path.dirname(sys.executable)
else:
    # Запущено как обычный скрипт
    # Хелпер ожидается рядом с этим скриптом (.py)
    helper_base_path = os.path.dirname(__file__)

helper_path = os.path.join(helper_base_path, 'coredisplay_helper')
logger.info(f"Путь к coredisplay_helper: {helper_path}") # Добавим лог для отладки


# --- Старая логика загрузки CoreDisplay (оставляем как fallback, если хелпер не найден) ---
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
    logger.info(f"Выполнение действия: {action}")
    import os
    logger.info(f"Текущий UID: {os.getuid()}, GID: {os.getgid()}")
    if action.startswith('open '):
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
            if os.path.exists(helper_path) and os.access(helper_path, os.X_OK):
                logger.debug(f"Запуск хелпера: {helper_path} {val}")
                result = subprocess.run([helper_path, str(val)], check=True, capture_output=True, text=True)
                logger.info(f"stdout: {result.stdout}")
                logger.info(f"stderr: {result.stderr}")
                logger.info(f"returncode: {result.returncode}")
                return
            else:
                logger.warning(f"Хелпер не найден или недоступен: {helper_path}. Попытка fallback...")
            # Fallback: Если хелпер не найден/не сработал, пробуем старые методы
            if CoreDisplay_Display_SetUserBrightness:
                disp = CGMainDisplayID()
                res = CoreDisplay_Display_SetUserBrightness(disp, ctypes.c_float(val))
                if res != 0:
                    logger.error(f'Ошибка установки яркости via CoreDisplay: {res}')
                return
            set_display_brightness(val) # IOKit fallback
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка выполнения хелпера: {e}. Output: {e.stdout}. Stderr: {e.stderr}")
        except Exception as e:
            logger.error(f'Ошибка установки яркости: {e}')
    elif action == 'brightness_up':
        try:
            cur = get_display_brightness()
            new_val = min(1.0, cur + 0.1)
            if os.path.exists(helper_path) and os.access(helper_path, os.X_OK):
                logger.debug(f"Запуск хелпера: {helper_path} {new_val}")
                result = subprocess.run([helper_path, str(new_val)], check=True, capture_output=True, text=True)
                logger.info(f"stdout: {result.stdout}")
                logger.info(f"stderr: {result.stderr}")
                logger.info(f"returncode: {result.returncode}")
                return
            else:
                logger.warning(f"Хелпер не найден или недоступен: {helper_path}. Попытка fallback...")
            # Fallback
            if CoreDisplay_Display_SetUserBrightness:
                disp = CGMainDisplayID()
                res = CoreDisplay_Display_SetUserBrightness(disp, ctypes.c_float(new_val))
                if res != 0:
                    logger.error(f'Ошибка увеличения яркости via CoreDisplay: {res}')
                return
            set_display_brightness(new_val) # IOKit fallback
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка выполнения хелпера: {e}. Output: {e.stdout}. Stderr: {e.stderr}")
        except Exception as e:
            logger.error(f'Ошибка увеличения яркости: {e}')
    elif action == 'brightness_down':
        try:
            cur = get_display_brightness()
            new_val = max(0.0, cur - 0.1)
            if os.path.exists(helper_path) and os.access(helper_path, os.X_OK):
                logger.debug(f"Запуск хелпера: {helper_path} {new_val}")
                result = subprocess.run([helper_path, str(new_val)], check=True, capture_output=True, text=True)
                logger.info(f"stdout: {result.stdout}")
                logger.info(f"stderr: {result.stderr}")
                logger.info(f"returncode: {result.returncode}")
                return
            else:
                logger.warning(f"Хелпер не найден или недоступен: {helper_path}. Попытка fallback...")
            # Fallback
            if CoreDisplay_Display_SetUserBrightness:
                disp = CGMainDisplayID()
                res = CoreDisplay_Display_SetUserBrightness(disp, ctypes.c_float(new_val))
                if res != 0:
                    logger.error(f'Ошибка уменьшения яркости via CoreDisplay: {res}')
                return
            set_display_brightness(new_val) # IOKit fallback
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка выполнения хелпера: {e}. Output: {e.stdout}. Stderr: {e.stderr}")
        except Exception as e:
            logger.error(f'Ошибка уменьшения яркости: {e}')
    else:
        logger.warning(f'Неизвестное действие: {action}')

# --- Глобальные переменные для управления слушателем ---
_hotkey_listener_thread = None
_hotkey_listener_stop_event = threading.Event()
_hotkey_tap = None
_hotkey_run_loop_source = None

# --- Quartz глобальный слушатель ---
def start_quartz_hotkey_listener():
    import Quartz
    import AppKit
    from PyQt5.QtCore import QCoreApplication
    global _hotkey_listener_thread
    
    # Если слушатель уже запущен, останавливаем его
    if _hotkey_listener_thread and _hotkey_listener_thread.is_alive():
        stop_quartz_hotkey_listener()
        
    _hotkey_listener_stop_event.clear()
    _hotkey_listener_thread = threading.Thread(target=_run_hotkey_listener, name="QuartzHotkeyThread", daemon=True)
    _hotkey_listener_thread.start()
    logger.info("Запуск нового Quartz hotkey listener thread")

def stop_quartz_hotkey_listener():
    """Остановить слушатель хоткеев"""
    global _hotkey_listener_thread, _hotkey_tap, _hotkey_run_loop_source
    
    logger.info("Остановка Quartz hotkey listener...")
    _hotkey_listener_stop_event.set()
    
    if _hotkey_listener_thread and _hotkey_listener_thread.is_alive():
        _hotkey_listener_thread.join(timeout=2.0)
        
    _hotkey_listener_thread = None
    _hotkey_tap = None
    _hotkey_run_loop_source = None

def restart_quartz_hotkey_listener():
    """Перезапустить слушатель хоткеев"""
    logger.info("Перезапуск Quartz hotkey listener после пробуждения...")
    stop_quartz_hotkey_listener()
    time.sleep(0.5)  # Небольшая пауза
    start_quartz_hotkey_listener()

def _run_hotkey_listener():
    """Основная функция слушателя хоткеев"""
    import Quartz
    
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
        # Проверяем, не был ли event tap отключен
        if not Quartz.CGEventTapIsEnabled(_hotkey_tap):
            logger.warning("CGEventTap был отключен, пытаемся включить обратно...")
            Quartz.CGEventTapEnable(_hotkey_tap, True)
            return event
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
    
    # Создаем event tap
    global _hotkey_tap, _hotkey_run_loop_source
    
    mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
    _hotkey_tap = Quartz.CGEventTapCreate(
        Quartz.kCGHIDEventTap,  # use HID tap for global key events
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        mask,
        event_callback,
        None
    )
    
    if not _hotkey_tap:
        logger.error('Не удалось создать CGEventTap. Проверьте права Accessibility!')
        return
        
    _hotkey_run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, _hotkey_tap, 0)
    loop = Quartz.CFRunLoopGetCurrent()
    Quartz.CFRunLoopAddSource(loop, _hotkey_run_loop_source, Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(_hotkey_tap, True)
    logger.info('Quartz hotkey listener started.')
    
    # Запускаем run loop с проверкой на остановку
    while not _hotkey_listener_stop_event.is_set():
        try:
            # Используем короткие интервалы для возможности проверки stop_event
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.1, False)
            
            # Периодически проверяем состояние event tap
            if _hotkey_tap and not Quartz.CGEventTapIsEnabled(_hotkey_tap):
                logger.warning("CGEventTap отключен, пытаемся включить...")
                Quartz.CGEventTapEnable(_hotkey_tap, True)
                
        except Exception as e:
            logger.error(f"Ошибка в run loop: {e}")
            break
    
    # Очистка ресурсов
    try:
        if _hotkey_run_loop_source and loop:
            Quartz.CFRunLoopRemoveSource(loop, _hotkey_run_loop_source, Quartz.kCFRunLoopCommonModes)
        if _hotkey_tap:
            Quartz.CFMachPortInvalidate(_hotkey_tap)
    except Exception as e:
        logger.error(f"Ошибка при очистке ресурсов: {e}")
        
    logger.info('Quartz hotkey listener stopped.')

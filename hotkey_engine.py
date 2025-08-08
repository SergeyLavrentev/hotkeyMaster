import sys # Добавляем импорт sys
import os # Убедимся, что os импортирован
import subprocess # Убедимся, что subprocess импортирован
import logging # Убедимся, что logging импортирован
import ctypes # Убедимся, что ctypes импортирован
import ctypes.util
import threading # Добавляем импорт threading
import json # Добавляем импорт json
import uuid
from typing import List, Dict, Any, Optional
import time # Добавляем импорт time
import Quartz
from PyQt5 import QtWidgets
from Quartz import CGMainDisplayID, CGEventPost, kCGHIDEventTap, CGEventCreateKeyboardEvent, CGEventSetFlags, kCGEventFlagMaskShift, kCGEventFlagMaskControl, kCGEventFlagMaskAlternate, kCGEventFlagMaskCommand
from actions import run_action as unified_run_action, get_active_app_name as unified_get_active_app_name, set_display_brightness, get_display_brightness

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

# Позволяем тестам переопределять путь к файлу хоткеев
HOTKEYS_FILE = os.environ.get('HOTKEYMASTER_HOTKEYS_FILE', os.path.join(APP_SUPPORT_DIR, 'hotkeys.json'))

# Кэш хоткеев
_hotkeys_cache: List[Dict[str, Any]] = []
_hotkeys_mtime: Optional[float] = None
_hotkeys_lock = threading.Lock()
_strict_mods = False
_settings_mtime = None
SETTINGS_PATH = os.path.join(APP_SUPPORT_DIR, 'settings.json')

def _ensure_ids(hotkeys: List[Dict[str, Any]]):
    """Гарантирует наличие уникального поля id у каждого хоткея."""
    seen = set()
    changed = False
    for hk in hotkeys:
        if 'id' not in hk or not isinstance(hk.get('id'), str):
            hk['id'] = uuid.uuid4().hex
            changed = True
        if hk['id'] in seen:
            hk['id'] = uuid.uuid4().hex
            changed = True
        seen.add(hk['id'])
    return changed

def _atomic_write_json(path: str, data: Any):
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)

def _load_hotkeys_raw() -> List[Dict[str, Any]]:
    try:
        with open(HOTKEYS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        # Обеспечиваем ID
        if _ensure_ids(data):
            try:
                _atomic_write_json(HOTKEYS_FILE, data)
            except Exception:
                pass
        return data
    except FileNotFoundError:
        try:
            _atomic_write_json(HOTKEYS_FILE, [])
        except Exception:
            pass
        return []
    except json.JSONDecodeError:
        return []
    except Exception as e:
        logger.error(f"Ошибка чтения hotkeys.json: {e}")
        return []

def refresh_hotkeys_cache(force: bool = False):
    global _hotkeys_cache, _hotkeys_mtime
    with _hotkeys_lock:
        try:
            mtime = os.path.getmtime(HOTKEYS_FILE) if os.path.exists(HOTKEYS_FILE) else None
            if force:
                logger.debug(f"[refresh_hotkeys_cache] FORCE reload path={HOTKEYS_FILE} exists={os.path.exists(HOTKEYS_FILE)} size={(os.path.getsize(HOTKEYS_FILE) if os.path.exists(HOTKEYS_FILE) else 'NA')}")
                _hotkeys_cache = _load_hotkeys_raw()
                _hotkeys_mtime = mtime
            elif (_hotkeys_mtime is None) or (mtime and _hotkeys_mtime != mtime):
                logger.debug(f"[refresh_hotkeys_cache] mtime change reload old={_hotkeys_mtime} new={mtime}")
                _hotkeys_cache = _load_hotkeys_raw()
                _hotkeys_mtime = mtime
        except Exception as e:
            logger.error(f"Ошибка обновления кэша хоткеев: {e}")

def load_hotkeys():
    """Возвращает список хоткеев (кэшируемый)."""
    refresh_hotkeys_cache()
    # Возвращаем копию чтобы внешние изменения не ломали кэш
    with _hotkeys_lock:
        return [dict(hk) for hk in _hotkeys_cache]

def save_hotkeys(hotkeys):
    """Сохраняет хоткеи атомарно и обновляет кэш."""
    with _hotkeys_lock:
        # гарантируем id перед записью
        _ensure_ids(hotkeys)
        _atomic_write_json(HOTKEYS_FILE, hotkeys)
        _hotkeys_cache = [dict(hk) for hk in hotkeys]
        try:
            _hotkeys_mtime = os.path.getmtime(HOTKEYS_FILE)
        except Exception:
            pass

def _load_general_settings():
    global _strict_mods, _settings_mtime
    try:
        if os.path.exists(SETTINGS_PATH):
            mtime = os.path.getmtime(SETTINGS_PATH)
            if _settings_mtime is None or mtime != _settings_mtime:
                with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                _strict_mods = bool(data.get('strict_mod_match', False))
                _settings_mtime = mtime
    except Exception:
        pass

def get_strict_mods() -> bool:
    """Публичный геттер режима строгих модификаторов (обновляет при необходимости)."""
    _load_general_settings()
    return _strict_mods

def hotkey_conflicts(new_hk: Dict[str, Any], existing: List[Dict[str, Any]], *, strict: Optional[bool]=None, ignore_id: Optional[str]=None) -> Optional[Dict[str, Any]]:
    """Проверяет конфликт нового хоткея c уже существующими.
    Возвращает конфликтующий хоткей или None.
    Правила:
      - trackpad: конфликт если совпадает gesture и (scope совпадает) либо один глобальный и другой app-специфичный той же app? Глобальный конфликтует со всеми жестами того же типа.
      - keyboard: конфликт если vk совпадает и множества модификаторов совпадают (строгий режим) либо
                  при нестрогом режиме один набор модификаторов является подмножеством другого (перекрытие) —
                  и области действия пересекаются (оба global или один global, другой app совпадает по app, либо оба app с одинаковым app).
    ignore_id: id хоткея, который редактируется (чтобы не детектить конфликт с самим собой).
    """
    if strict is None:
        strict = get_strict_mods()
    new_type = new_hk.get('type', 'keyboard')
    new_scope = new_hk.get('scope', 'global')
    new_app = new_hk.get('app', '') or ''
    def scopes_overlap(s1, a1, s2, a2):
        if s1 == 'global' or s2 == 'global':
            # global конфликтует со всем
            if s1 == 'app' and s2 == 'global':
                return True
            if s2 == 'app' and s1 == 'global':
                return True
            return True
        # оба app-специфичные
        return (a1 or '') == (a2 or '')
    for hk in existing:
        if ignore_id and hk.get('id') == ignore_id:
            continue
        if hk.get('type', 'keyboard') != new_type:
            continue
        if new_type == 'trackpad':
            if hk.get('gesture') == new_hk.get('gesture') and scopes_overlap(hk.get('scope','global'), hk.get('app',''), new_scope, new_app):
                return hk
        else:  # keyboard
            combo_a = hk.get('combo') or {}
            combo_b = new_hk.get('combo') or {}
            vk_a = combo_a.get('vk')
            vk_b = combo_b.get('vk')
            if vk_a is None or vk_b is None or vk_a != vk_b:
                continue
            mods_a = set(combo_a.get('mods', []))
            mods_b = set(combo_b.get('mods', []))
            conflict = False
            if strict:
                conflict = mods_a == mods_b
            else:
                # пересечение по подмножеству — любой из наборов покрывает другой
                conflict = mods_a.issubset(mods_b) or mods_b.issubset(mods_a)
            if conflict and scopes_overlap(hk.get('scope','global'), hk.get('app',''), new_scope, new_app):
                return hk
    return None

def compare_hotkey_event(event_vk, event_mods, hk_combo, strict: bool):
    """Сравнивает событие с хоткеем.
    event_mods: set(str)
    hk_combo: dict {mods:[...], vk:int}
    strict: True -> точное совпадение множества модификаторов; False -> hk.mods ⊆ event_mods
    """
    if hk_combo is None:
        return False
    hk_vk = hk_combo.get('vk')
    if hk_vk is None or hk_vk != event_vk:
        return False
    hk_mods = set(hk_combo.get('mods', []))
    # Нормализуем регистр (UI сохраняет в нижнем, Quartz даёт с заглавной первой буквой)
    hk_mods_l = {m.lower() for m in hk_mods}
    event_mods_l = {m.lower() for m in event_mods}
    if strict:
        return hk_mods_l == event_mods_l
    return hk_mods_l.issubset(event_mods_l)

# --- Работа с хоткеями ---
## Старые функции load_hotkeys / save_hotkeys заменены обновлёнными версиями выше

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
    # Deprecated local wrapper — use unified version
    return unified_get_active_app_name()

def run_action(action):
    # Proxy to unified implementation for backwards compatibility
    unified_run_action(action)

# --- Глобальные переменные для управления слушателем ---
_hotkey_listener_thread = None
_hotkey_listener_stop_event = threading.Event()
_hotkey_tap = None
_hotkey_run_loop_source = None
KEY_REPEAT_DEBOUNCE = 0.4  # секунды подавления повтора удержанной клавиши
_last_hotkey_fire = {}  # key -> timestamp последнего срабатывания

def _hotkey_fire_key(hk: Dict[str, Any]):
    """Возвращает ключ для системы подавления повторов."""
    if 'id' in hk:
        return hk['id']
    if hk.get('type') == 'keyboard':
        combo = hk.get('combo') or {}
        return ('kbd', combo.get('vk'), tuple(sorted(combo.get('mods', []))), hk.get('scope'), hk.get('app'))
    if hk.get('type') == 'trackpad':
        return ('tp', hk.get('gesture'), hk.get('scope'), hk.get('app'))
    return ('unknown', id(hk))

def allow_hotkey_fire(hk: Dict[str, Any], now: Optional[float]=None) -> bool:
    """Возвращает True если действие можно выполнить (не подавлено)."""
    if now is None:
        now = time.time()
    key = _hotkey_fire_key(hk)
    last = _last_hotkey_fire.get(key)
    if last is not None and (now - last) < KEY_REPEAT_DEBOUNCE:
        return False
    _last_hotkey_fire[key] = now
    return True

# --- Quartz глобальный слушатель ---
def start_quartz_hotkey_listener():
    import Quartz
    import AppKit
    from PyQt5.QtCore import QCoreApplication
    global _hotkey_listener_thread
    
    logger.info("Запуск Quartz hotkey listener...")
    
    # Если слушатель уже запущен, останавливаем его
    if _hotkey_listener_thread and _hotkey_listener_thread.is_alive():
        logger.info("Останавливаем существующий hotkey listener")
        stop_quartz_hotkey_listener()
        
    # Небольшая пауза для очистки ресурсов
    time.sleep(0.1)
        
    _hotkey_listener_stop_event.clear()
    _hotkey_listener_thread = threading.Thread(target=_run_hotkey_listener, name="QuartzHotkeyThread", daemon=True)
    _hotkey_listener_thread.start()
    
    logger.info("Новый Quartz hotkey listener thread запущен")

def stop_quartz_hotkey_listener():
    """Остановить слушатель хоткеев"""
    global _hotkey_listener_thread, _hotkey_tap, _hotkey_run_loop_source
    
    logger.info("Остановка Quartz hotkey listener...")
    _hotkey_listener_stop_event.set()
    
    # Очищаем CGEventTap первым делом
    if _hotkey_tap:
        try:
            import Quartz
            Quartz.CGEventTapEnable(_hotkey_tap, False)
            if _hotkey_run_loop_source:
                try:
                    # Получаем текущий run loop потока
                    if _hotkey_listener_thread and _hotkey_listener_thread.is_alive():
                        # Сигнализируем потоку о необходимости остановки
                        pass  # stop event уже установлен
                except Exception as e:
                    logger.error(f"Ошибка остановки run loop source: {e}")
        except Exception as e:
            logger.error(f"Ошибка остановки CGEventTap: {e}")
    
    # Ждем завершения потока
    if _hotkey_listener_thread and _hotkey_listener_thread.is_alive():
        try:
            _hotkey_listener_thread.join(timeout=3.0)
            if _hotkey_listener_thread.is_alive():
                logger.warning("Поток hotkey listener не завершился за 3 секунды")
        except Exception as e:
            logger.error(f"Ошибка при ожидании завершения потока: {e}")
        
    # Очищаем глобальные переменные
    _hotkey_listener_thread = None
    _hotkey_tap = None
    _hotkey_run_loop_source = None
    
    logger.info("Quartz hotkey listener остановлен")

def restart_quartz_hotkey_listener():
    """Перезапустить слушатель хоткеев"""
    logger.info("Перезапуск Quartz hotkey listener после пробуждения...")
    
    try:
        # Останавливаем с тайм-аутом
        stop_quartz_hotkey_listener()
        
        # Даем системе время для очистки ресурсов
        time.sleep(1.0)
        
        # Запускаем заново
        start_quartz_hotkey_listener()
        
        logger.info("Hotkey listener успешно перезапущен")
    except Exception as e:
        logger.error(f"Ошибка перезапуска hotkey listener: {e}")
        # Попытаемся запустить заново даже при ошибке остановки
        try:
            time.sleep(0.5)
            start_quartz_hotkey_listener()
            logger.info("Hotkey listener запущен после ошибки остановки")
        except Exception as restart_error:
            logger.error(f"Критическая ошибка запуска hotkey listener: {restart_error}")

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
        # Загружаем настройки (strict_mod_match) при необходимости
        _load_general_settings()
        # Отсекаем отключённые хоткеи
        hotkeys = [hk for hk in load_hotkeys() if hk.get('enabled', True)]
        for hk in hotkeys:
            if hk.get('type') != 'keyboard':
                continue
            combo = hk.get('combo', {})
            logger.debug(f"Сравниваем с хоткеем: vk={combo.get('vk')}, mods={combo.get('mods')}, disp={combo.get('disp')} strict={_strict_mods}")
            if compare_hotkey_event(vk, mods, combo, _strict_mods):
                scope = hk.get('scope', 'global')
                app = hk.get('app', '')
                if scope == 'app' and app:
                    active_app = get_active_app_name()
                    if not active_app or app not in active_app:
                        continue
                # Подавление повторов удержания
                if not allow_hotkey_fire(hk):
                    logger.debug("[DEBOUNCE] suppressed repeat hotkey fire")
                    break
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
    logger.info('Hotkey listener run loop запущен')
    while not _hotkey_listener_stop_event.is_set():
        try:
            # Используем короткие интервалы для возможности проверки stop_event
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.1, False)
            
            # Периодически проверяем состояние event tap
            if _hotkey_tap and not Quartz.CGEventTapIsEnabled(_hotkey_tap):
                logger.warning("CGEventTap отключен, пытаемся включить...")
                try:
                    Quartz.CGEventTapEnable(_hotkey_tap, True)
                except Exception as e:
                    logger.error(f"Не удалось включить CGEventTap: {e}")
                    break  # Выходим из цикла при критической ошибке
                
        except Exception as e:
            logger.error(f"Ошибка в run loop: {e}")
            # При критической ошибке пытаемся продолжить, но ограничиваем количество попыток
            time.sleep(0.1)
    
    logger.info('Hotkey listener run loop завершен')
    
    # Очистка ресурсов
    try:
        if _hotkey_run_loop_source and loop:
            try:
                Quartz.CFRunLoopRemoveSource(loop, _hotkey_run_loop_source, Quartz.kCFRunLoopCommonModes)
                logger.debug("Run loop source удален")
            except Exception as e:
                logger.error(f"Ошибка удаления run loop source: {e}")
        
        if _hotkey_tap:
            try:
                Quartz.CGEventTapEnable(_hotkey_tap, False)
                Quartz.CFMachPortInvalidate(_hotkey_tap)
                logger.debug("CGEventTap отключен и инвалидирован")
            except Exception as e:
                logger.error(f"Ошибка инвалидации CGEventTap: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при очистке ресурсов: {e}")
        
    logger.info('Quartz hotkey listener stopped.')

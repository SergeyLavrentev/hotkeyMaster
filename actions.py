"""Centralized actions and helpers for HotkeyMaster.

Содержит единые реализации:
 - get_active_app_name
 - run_action (open / run / hotkey: / message: / brightness_*)
 - управление яркостью (helper бинарь / CoreDisplay / IOKit fallback / файл cache)

Важно: модуль не должен тянуть PyQt5 на импорт, кроме случая message: (ленивая загрузка).
"""
from __future__ import annotations

import os
import sys
import json
import logging
import subprocess
import ctypes
import ctypes.util

logger = logging.getLogger("hotkeymaster.actions")

# ---------------------------------------------------------------------------
# Active app helper
# ---------------------------------------------------------------------------
def get_active_app_name():
    try:
        import Quartz
        ws = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
        for w in ws:
            if w.get('kCGWindowLayer') == 0 and w.get('kCGWindowOwnerName'):
                return w['kCGWindowOwnerName']
    except Exception as e:
        logger.debug(f"Не удалось получить активное приложение: {e}")
    return None

# ---------------------------------------------------------------------------
# Brightness helpers
# ---------------------------------------------------------------------------
_last_brightness_cache_path = os.path.join(
    os.path.expanduser('~'), 'Library', 'Application Support', 'HotkeyMaster', 'last_brightness.json'
)

def _get_helper_path():
    # В дев-режиме helper ожидается рядом со скриптом, в frozen — рядом с binary
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(__file__)
    return os.path.join(base, 'coredisplay_helper')

def _core_display_func():
    """Попытка получить CoreDisplay_Display_SetUserBrightness функцию или None."""
    try:
        import CoreDisplay as _cd  # type: ignore
        return _cd.CoreDisplay_Display_SetUserBrightness
    except Exception:
        pass
    lib = ctypes.util.find_library('CoreDisplay')
    if lib:
        try:
            cd = ctypes.cdll.LoadLibrary(lib)
            fn = getattr(cd, 'CoreDisplay_Display_SetUserBrightness', None)
            if fn:
                fn.argtypes = [ctypes.c_uint32, ctypes.c_float]
                fn.restype = ctypes.c_int
                return fn
        except Exception:
            return None
    # Явные пути
    for p in [
        '/System/Library/PrivateFrameworks/CoreDisplay.framework/CoreDisplay',
        '/System/Library/PrivateFrameworks/CoreDisplay.framework/Versions/A/CoreDisplay'
    ]:
        if os.path.exists(p):
            try:
                cd = ctypes.cdll.LoadLibrary(p)
                fn = getattr(cd, 'CoreDisplay_Display_SetUserBrightness', None)
                if fn:
                    fn.argtypes = [ctypes.c_uint32, ctypes.c_float]
                    fn.restype = ctypes.c_int
                    return fn
            except Exception:
                continue
    return None

_core_display_set = _core_display_func()

def _io_kit_set(val: float) -> bool:
    """Минимальный fallback через IOKit (Best effort). Возвращает успех."""
    try:
        # Используем DisplayServicesSetBrightness если доступна
        handle_ds = ctypes.cdll.LoadLibrary('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
        fn = getattr(handle_ds, 'DisplayServicesSetBrightness', None)
        if not fn:
            return False
        fn.argtypes = [ctypes.c_uint32, ctypes.c_float]
        fn.restype = ctypes.c_int
        from Quartz import CGMainDisplayID  # type: ignore
        disp = CGMainDisplayID()
        res = fn(disp, ctypes.c_float(val))
        return res == 0
    except Exception:
        return False

def set_display_brightness(val: float) -> bool:
    val = max(0.0, min(1.0, float(val)))
    helper = _get_helper_path()
    # 1. Helper binary
    if os.path.exists(helper) and os.access(helper, os.X_OK):
        try:
            r = subprocess.run([helper, str(val)], check=True, capture_output=True, text=True)
            logger.debug(f"helper stdout={r.stdout.strip()} stderr={r.stderr.strip()}")
            _persist_last_brightness(val)
            return True
        except Exception as e:
            logger.warning(f"Helper brightness ошибка: {e}")
    # 2. CoreDisplay
    if _core_display_set:
        try:
            from Quartz import CGMainDisplayID  # type: ignore
            disp = CGMainDisplayID()
            res = _core_display_set(disp, ctypes.c_float(val))
            if res == 0:
                _persist_last_brightness(val)
                return True
            logger.warning(f"CoreDisplay возвратил код {res}")
        except Exception as e:
            logger.debug(f"CoreDisplay set fail: {e}")
    # 3. IOKit / DisplayServices fallback
    if _io_kit_set(val):
        _persist_last_brightness(val)
        return True
    # 4. Cache only
    _persist_last_brightness(val)
    return False

def _persist_last_brightness(val: float):
    try:
        os.makedirs(os.path.dirname(_last_brightness_cache_path), exist_ok=True)
        with open(_last_brightness_cache_path, 'w', encoding='utf-8') as f:
            json.dump({'value': float(val)}, f)
    except Exception:
        pass

def get_display_brightness() -> float:
    # Мы не имеем простой публичной API чтения; используем cache
    try:
        if os.path.exists(_last_brightness_cache_path):
            with open(_last_brightness_cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            v = float(data.get('value', 0.5))
            return max(0.0, min(1.0, v))
    except Exception:
        pass
    return 0.5

# ---------------------------------------------------------------------------
# run_action
# ---------------------------------------------------------------------------

def run_action(action: str):
    logger.debug(f"Выполнение действия: {action}")
    if not action:
        return
    try:
        if action.startswith('message:'):
            # Lazy import PyQt5 (если интерфейс уже есть)
            from PyQt5 import QtWidgets
            app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
            QtWidgets.QMessageBox.information(None, 'HotkeyMaster', action[len('message:'):])
            return
        if action.startswith('open '):
            url = action[5:].strip()
            if url and not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            if url:
                logger.debug(f"Открытие URL: {url}")
                import webbrowser
                webbrowser.open(url)
            return
        if action.startswith('open_app '):
            app_name = action[9:].strip()
            if not app_name:
                logger.debug('open_app без имени — пропуск')
                return
            # Попытаемся найти .app bundle в /Applications; если пользователь ввёл без .app — добавим
            bundle = app_name if app_name.endswith('.app') else app_name + '.app'
            candidate_paths = [
                f"/Applications/{bundle}",
                f"/System/Applications/{bundle}",
                f"/Applications/Utilities/{bundle}"
            ]
            path = next((p for p in candidate_paths if os.path.exists(p)), None)
            try:
                if path:
                    logger.debug(f"Открытие приложения по пути: {path}")
                    subprocess.Popen(['open', path])
                    logger.info(f"open_app: launched '{app_name}' via path")
                else:
                    logger.debug(f"Открытие приложения через -a: {app_name}")
                    # fallback через -a (macOS сам найдёт)
                    subprocess.Popen(['open', '-a', app_name])
                    logger.info(f"open_app: launched '{app_name}' via -a")
            except Exception as e:
                logger.error(f"Не удалось открыть приложение '{app_name}': {e}")
            return
        if action.startswith('run '):
            cmd = action[4:].strip()
            if not cmd:
                return
            # Без shell=True — безопаснее; если нужен shell, пользователь может указать /bin/sh -c
            try:
                parts = cmd.split() if ' ' in cmd else [cmd]
                logger.debug(f"Запуск команды: {parts}")
                subprocess.Popen(parts)
            except Exception:
                logger.debug("Ошибка Popen без shell, пробуем shell=True")
                subprocess.Popen(cmd, shell=True)
            return
        if action.startswith('hotkey:'):
            try:
                combo = json.loads(action[7:])
                mods = set(combo.get('mods', []))
                vk = combo.get('vk')
                if vk is None:
                    logger.debug('Эмуляция хоткея: vk отсутствует')
                    return
                logger.debug(f"Эмуляция хоткея mods={mods} vk={vk}")
                from Quartz import (
                    CGEventCreateKeyboardEvent, CGEventSetFlags, CGEventPost, kCGHIDEventTap,
                    kCGEventFlagMaskCommand, kCGEventFlagMaskShift, kCGEventFlagMaskAlternate, kCGEventFlagMaskControl
                )
                flags = 0
                if 'Cmd' in mods: flags |= kCGEventFlagMaskCommand
                if 'Shift' in mods: flags |= kCGEventFlagMaskShift
                if 'Alt' in mods: flags |= kCGEventFlagMaskAlternate
                if 'Ctrl' in mods: flags |= kCGEventFlagMaskControl
                for down in (True, False):
                    ev = CGEventCreateKeyboardEvent(None, vk, down)
                    CGEventSetFlags(ev, flags)
                    CGEventPost(kCGHIDEventTap, ev)
            except Exception as e:
                logger.error(f"Ошибка эмуляции хоткея: {e}")
            return
        if action.startswith('brightness_set '):
            try:
                percent = int(action.split()[1])
                logger.debug(f"Установка яркости: {percent}%")
                set_display_brightness(percent / 100.0)
            except Exception as e:
                logger.error(f"Ошибка установки яркости: {e}")
            return
        if action == 'brightness_up':
            cur = get_display_brightness()
            logger.debug("Повышение яркости на +10%")
            set_display_brightness(min(1.0, cur + 0.1))
            return
        if action == 'brightness_down':
            cur = get_display_brightness()
            logger.debug("Понижение яркости на -10%")
            set_display_brightness(max(0.0, cur - 0.1))
            return
        logger.warning(f"Неизвестное действие: {action}")
    except Exception as e:
        logger.error(f"Критическая ошибка run_action: {e}")

__all__ = [
    'get_active_app_name',
    'run_action',
    'get_display_brightness',
    'set_display_brightness'
]

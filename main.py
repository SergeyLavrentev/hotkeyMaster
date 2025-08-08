import sys
import threading
import signal
import subprocess
import os
import json
import time # Добавим импорт time
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon
import logging
from ui import show_settings_window
import Quartz
import socket
from trackpad_engine import TrackpadGestureEngine
# --- Добавляем импорты Qt ---
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QCoreApplication
from PyQt5 import QtWidgets
# --- Конец импортов Qt ---
from Foundation import NSObject
from objc import selector

from hotkey_engine import (
    load_hotkeys, save_hotkeys, start_quartz_hotkey_listener,
    stop_quartz_hotkey_listener, restart_quartz_hotkey_listener
)
from actions import run_action, get_active_app_name
from sleep_wake_monitor import get_sleep_wake_monitor

HOTKEYS_FILE = 'hotkeys.json'
# --- Настройка логирования только в файл ---
LOG_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Logs')
LOG_FILE = os.path.join(LOG_DIR, 'HotkeyMaster.log')
os.makedirs(LOG_DIR, exist_ok=True)

DEV_MODE = bool(os.environ.get('HOTKEYMASTER_DEV')) and not getattr(sys, 'frozen', False)
if DEV_MODE:
    log_level = logging.DEBUG
else:
    log_level = logging.ERROR  # в проде пишем минимально

# Настраиваем ротацию логов для предотвращения переполнения
from logging.handlers import RotatingFileHandler

handlers = []
fmt = '[%(asctime)s] %(levelname)s [%(name)s]: %(message)s'
if DEV_MODE:
    # Все в stdout
    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setLevel(log_level)
    stream_h.setFormatter(logging.Formatter(fmt))
    handlers.append(stream_h)
else:
    # Только файл, уровень ERROR
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(fmt))
    handlers.append(file_handler)

logging.basicConfig(level=log_level, handlers=handlers, format=fmt)

# Добавляем дополнительный обработчик для критических ошибок
critical_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, 'HotkeyMaster_errors.log'),
    maxBytes=5*1024*1024,  # 5MB
    backupCount=3,
    encoding='utf-8'
)
critical_handler.setLevel(logging.ERROR)
critical_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] CRITICAL [%(name)s]: %(message)s\nTraceback: %(exc_info)s\n---'
))

logger = logging.getLogger('hotkeymaster')
logger.addHandler(critical_handler)

# Логируем старт приложения
logger.info("=" * 60)
logger.log(logging.DEBUG if DEV_MODE else logging.ERROR, "HotkeyMaster запускается (dev=%s, level=%s)", DEV_MODE, logging.getLevelName(log_level))
logger.info("=" * 60)

def handle_exception(exc_type, exc_value, exc_traceback):
    """Обработчик неперехваченных исключений"""
    if issubclass(exc_type, KeyboardInterrupt):
        # Разрешаем KeyboardInterrupt работать как обычно
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger.critical("Неперехваченное исключение:", 
                   exc_info=(exc_type, exc_value, exc_traceback))
    
    # Пытаемся корректно завершить работу
    try:
        logger.info("Попытка корректного завершения после критической ошибки...")
        cleanup_listeners()
        
        # Останавливаем мониторинг сна
        from sleep_wake_monitor import get_sleep_wake_monitor
        sleep_monitor = get_sleep_wake_monitor()
        sleep_monitor.stop_monitoring()
        
    except Exception as cleanup_error:
        logger.critical(f"Ошибка при cleanup после критической ошибки: {cleanup_error}")
    
    # Завершаем с кодом ошибки
    sys.exit(1)

# Устанавливаем обработчик неперехваченных исключений
sys.excepthook = handle_exception

## run_action и get_active_app_name теперь импортируются из actions

def open_settings_window():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    try:
        # Активируем приложение и приводим окно настроек на передний план
        import AppKit
        NSApp = AppKit.NSApp
        NSApp.activateIgnoringOtherApps_(True)
        # Временно меняем политику активации, чтобы окно QDialog отображалось
        NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    except Exception:
        pass
    try:
        show_settings_window(load_hotkeys, save_hotkeys)
    finally:
        # Возвращаем политику к Accessory, чтобы скрыть из Dock
        try:
            import AppKit
            NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        except Exception:
            pass

def resource_path(rel_path):
    import sys, os
    if getattr(sys, 'frozen', False):
        exec_dir = os.path.dirname(sys.executable)
        resources_icons = os.path.abspath(os.path.join(exec_dir, '..', 'Resources', 'icons', rel_path))
        if os.path.exists(resources_icons):
            return resources_icons
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), 'icons', rel_path)

def create_tray_qt(app):
    # Создание системного трей-икон
    icon_path = resource_path('tray_icon.png')
    tray_icon = QSystemTrayIcon(QIcon(icon_path), parent=app)
    menu = QMenu()
    settings_action = QAction('Настройки', parent=app)
    settings_action.triggered.connect(open_settings_window)
    quit_action = QAction('Выход', parent=app)
    quit_action.triggered.connect(app.quit)
    menu.addAction(settings_action)
    menu.addAction(quit_action)
    tray_icon.setContextMenu(menu)
    tray_icon.show()
    return tray_icon

def check_accessibility_and_warn():
    try:
        import Quartz
        if Quartz.CGPreflightListenEventAccess():
            logger.info("Есть права Universal Access (Accessibility)")
            return True
        else:
            logger.warning("Нет прав Universal Access (Accessibility)")
            app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
            msg = QtWidgets.QMessageBox()
            msg.setIcon(QtWidgets.QMessageBox.Warning)
            msg.setWindowTitle("Требуется доступ к управлению компьютером")
            msg.setText(
                "Для работы глобальных хоткеев нужно разрешить доступ к управлению компьютером.\n\n"
                "1. Откройте: Системные настройки → Конфиденциальность и безопасность → Универсальный доступ\n"
                "2. Добавьте сюда ваш терминал (или HotkeyMaster.app) и поставьте галочку.\n\n"
                "После этого перезапустите программу."
            )
            btn = msg.addButton("Открыть настройки", QtWidgets.QMessageBox.AcceptRole)
            msg.addButton("Закрыть", QtWidgets.QMessageBox.RejectRole)
            msg.exec_()
            if msg.clickedButton() == btn:
                import subprocess
                subprocess.Popen(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'])
            return False
    except Exception as e:
        logger.error(f"Ошибка проверки прав Accessibility: {e}")
        return False

def is_another_instance_running():
    """Return True if another HotkeyMaster instance is already running."""
    import fcntl
    LOCK_PATH = '/tmp/hotkeymaster.lock'
    try:
        lock_fd = open(LOCK_PATH, 'w')
    except Exception:
        return False

    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        return True

    import atexit

    def _release_lock():
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            os.unlink(LOCK_PATH)
        except Exception:
            pass

    atexit.register(_release_lock)
    return False

# Убедимся, что при выходе все слушатели останавливаются
def cleanup_listeners():
    logger.info("Cleaning up listeners before exit...")
    try:
        stop_quartz_hotkey_listener()
    except Exception as e:
        logger.error(f"Ошибка остановки hotkey listener: {e}")
    
    # Остановим trackpad engine, если он есть в глобальной области
    try:
        import gc
        for obj in gc.get_objects():
            if isinstance(obj, TrackpadGestureEngine):
                obj.stop()
                break
    except Exception as e:
        logger.error(f"Ошибка остановки trackpad engine: {e}")

def load_general_settings():
    import os, json
    path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'HotkeyMaster', 'settings.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'autostart': False}

def main():
    # --- Устанавливаем путь к Qt-плагинам для PyQt5 (важно для .app) ---
    try:
        if getattr(sys, 'frozen', False):
            # Для собранного .app
            plugin_path = os.path.join(os.path.dirname(sys.executable), 'platforms')
        else:
            # Для dev-режима
            from PyQt5 import QtCore
            plugin_path = os.path.join(os.path.dirname(QtCore.__file__), 'plugins')
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
        logger.info(f'Set QT_QPA_PLATFORM_PLUGIN_PATH={plugin_path}')
    except Exception as e:
        logger.warning(f'Не удалось установить QT_QPA_PLATFORM_PLUGIN_PATH: {e}')
    # --- Конец установки пути к плагинам ---

    # --- Создаём QApplication и скрываем из Dock ---
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # Скрываем из Dock и Cmd+Tab (dev-режим)
    try:
        import AppKit
        AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        logger.info('App hidden from Dock/Cmd+Tab (Accessory mode)')
    except Exception as e:
        logger.warning(f'Не удалось скрыть из Dock: {e}')
    # Устанавливаем QuitOnLastWindowClosed в False
    app.setQuitOnLastWindowClosed(False)

    # Регистрируем очистку при выходе
    import atexit
    atexit.register(cleanup_listeners)

    # Основной режим работы
    logger.info("Running in normal mode.")
    if is_another_instance_running():
        logger.warning('HotkeyMaster уже запущен.')
        logger.warning("Another instance is running. Exiting.")
        sys.exit(0)

    general_settings = load_general_settings()

    # Проверяем права Accessibility и предупреждаем пользователя
    if not check_accessibility_and_warn():
        logger.warning("Нет прав Accessibility — глобальные хоткеи работать не будут!")

    # Запуск глобального слушателя клавиатурных хоткеев через Quartz
    start_quartz_hotkey_listener()

    # Запуск трекпад-движка в отдельном потоке
    def get_gesture_actions():
        return load_hotkeys()
    trackpad_engine = TrackpadGestureEngine(get_gesture_actions, run_action, get_active_app_name)
    try:
        trackpad_engine.start()
        logger.info("Trackpad engine started.")
    except Exception as e:
        logger.error(f'Ошибка запуска трекпад-движка: {e}')
    
    # --- Настройка мониторинга сна/пробуждения ---
    sleep_monitor = get_sleep_wake_monitor()
    
    # Обработчики событий сна/пробуждения
    def on_system_will_sleep():
        logger.info("Система засыпает - останавливаем слушатели")
        try:
            stop_quartz_hotkey_listener()
            if trackpad_engine:
                trackpad_engine.stop()
        except Exception as e:
            logger.error(f"Ошибка остановки слушателей перед сном: {e}")
        
    def on_system_did_wake():
        logger.info("Система проснулась - перезапускаем слушатели")
        
        # Используем QtTimer для отложенного перезапуска в главном потоке
        from PyQt5.QtCore import QTimer
        
        def delayed_restart():
            try:
                logger.info("Начинаем отложенный перезапуск слушателей...")
                
                # Перезапускаем hotkey listener
                try:
                    restart_quartz_hotkey_listener()
                    logger.info("Hotkey listener перезапущен")
                except Exception as e:
                    logger.error(f"Ошибка перезапуска hotkey listener: {e}")
                
                # Небольшая пауза между перезапусками
                import time
                time.sleep(0.2)
                
                # Перезапускаем trackpad engine
                if trackpad_engine:
                    try:
                        trackpad_engine.restart()
                        logger.info("Trackpad engine перезапущен")
                    except Exception as e:
                        logger.error(f"Ошибка перезапуска trackpad engine: {e}")
                        
                logger.info("Все слушатели успешно перезапущены после пробуждения")
            except Exception as e:
                logger.error(f"Критическая ошибка перезапуска слушателей: {e}")
        
        # Задержка 2 секунды для стабилизации системы после пробуждения
        QTimer.singleShot(2000, delayed_restart)
    
    # Подключаем обработчики
    sleep_monitor.add_sleep_callback(on_system_will_sleep)
    sleep_monitor.add_wake_callback(on_system_did_wake)
    
    # Запускаем мониторинг
    try:
        sleep_monitor.start_monitoring()
        logger.info("Мониторинг сна/пробуждения запущен")
    except Exception as e:
        logger.error(f"Ошибка запуска мониторинга сна/пробуждения: {e}")
    
    # Убедимся, что мониторинг останавливается при выходе
    def cleanup_sleep_monitor():
        try:
            sleep_monitor.stop_monitoring()
            logger.info("Мониторинг сна/пробуждения остановлен")
        except Exception as e:
            logger.error(f"Ошибка остановки мониторинга: {e}")
    
    atexit.register(cleanup_sleep_monitor)

    # --- Показывать/скрывать трей ---
    tray_icon = create_tray_qt(app)

    # Запуск основного цикла событий Qt
    logger.info("Starting Qt application event loop...")
    app_exit_code = app.exec_()
    logger.info(f"Qt application event loop finished with code {app_exit_code}.")
    sys.exit(app_exit_code)

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""
Модуль для мониторинга событий сна/пробуждения macOS
и автоматического перезапуска слушателей событий
"""

import logging
import threading
import time
from typing import Callable, List
from Foundation import NSNotificationCenter, NSWorkspace
from PyQt5.QtCore import QTimer, QObject, pyqtSignal

logger = logging.getLogger(__name__)


class SleepWakeMonitor(QObject):
    """Монитор событий сна/пробуждения системы"""
    
    # Сигналы для событий сна/пробуждения
    system_will_sleep = pyqtSignal()
    system_did_wake = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._callbacks_will_sleep: List[Callable] = []
        self._callbacks_did_wake: List[Callable] = []
        self._is_monitoring = False
        self._notification_center = None
        
        # Таймер для проверки состояния (fallback)
        self._check_timer = QTimer()
        self._check_timer.timeout.connect(self._periodic_check)
        self._last_wake_time = time.time()
        
    def add_sleep_callback(self, callback: Callable):
        """Добавить callback для события засыпания"""
        self._callbacks_will_sleep.append(callback)
        
    def add_wake_callback(self, callback: Callable):
        """Добавить callback для события пробуждения"""
        self._callbacks_did_wake.append(callback)
        
    def start_monitoring(self):
        """Запустить мониторинг событий сна/пробуждения"""
        if self._is_monitoring:
            return
            
        try:
            # Подписываемся на уведомления NSWorkspace
            workspace = NSWorkspace.sharedWorkspace()
            self._notification_center = NSNotificationCenter.defaultCenter()
            
            # Уведомление о засыпании
            self._notification_center.addObserver_selector_name_object_(
                self, 'systemWillSleep:', 'NSWorkspaceWillSleepNotification', None
            )
            
            # Уведомление о пробуждении
            self._notification_center.addObserver_selector_name_object_(
                self, 'systemDidWake:', 'NSWorkspaceDidWakeNotification', None
            )
            
            # Соединяем сигналы
            self.system_will_sleep.connect(self._handle_will_sleep)
            self.system_did_wake.connect(self._handle_did_wake)
            
            # Запускаем периодическую проверку как fallback
            self._check_timer.start(30000)  # каждые 30 секунд
            
            self._is_monitoring = True
            logger.info("Мониторинг сна/пробуждения запущен")
            
        except Exception as e:
            logger.error(f"Ошибка запуска мониторинга сна/пробуждения: {e}")
            # Используем только периодическую проверку
            self._check_timer.start(10000)  # каждые 10 секунд
            self._is_monitoring = True
            
    def stop_monitoring(self):
        """Остановить мониторинг"""
        if not self._is_monitoring:
            return
            
        try:
            if self._notification_center:
                self._notification_center.removeObserver_(self)
            self._check_timer.stop()
            self._is_monitoring = False
            logger.info("Мониторинг сна/пробуждения остановлен")
        except Exception as e:
            logger.error(f"Ошибка остановки мониторинга: {e}")
            
    def systemWillSleep_(self, notification):
        """Обработчик уведомления о засыпании (Objective-C selector)"""
        logger.info("Система засыпает...")
        self.system_will_sleep.emit()
        
    def systemDidWake_(self, notification):
        """Обработчик уведомления о пробуждении (Objective-C selector)"""
        logger.info("Система проснулась!")
        self._last_wake_time = time.time()
        self.system_did_wake.emit()
        
    def _handle_will_sleep(self):
        """Обработка события засыпания"""
        logger.info("Обрабатываем событие засыпания...")
        for callback in self._callbacks_will_sleep:
            try:
                callback()
            except Exception as e:
                logger.error(f"Ошибка в callback засыпания: {e}")
                
    def _handle_did_wake(self):
        """Обработка события пробуждения"""
        logger.info("Обрабатываем событие пробуждения...")
        for callback in self._callbacks_did_wake:
            try:
                callback()
            except Exception as e:
                logger.error(f"Ошибка в callback пробуждения: {e}")
                
    def _periodic_check(self):
        """Периодическая проверка состояния (fallback)"""
        current_time = time.time()
        
        # Если прошло более 2 минут с последней проверки, 
        # возможно, система спала
        if hasattr(self, '_last_check_time'):
            time_diff = current_time - self._last_check_time
            if time_diff > 120:  # 2 минуты
                logger.info(f"Обнаружен пропуск времени {time_diff:.1f}с - возможно пробуждение")
                self._last_wake_time = current_time
                self.system_did_wake.emit()
                
        self._last_check_time = current_time


# Глобальный экземпляр монитора
_sleep_wake_monitor = None

def get_sleep_wake_monitor() -> SleepWakeMonitor:
    """Получить глобальный экземпляр монитора сна/пробуждения"""
    global _sleep_wake_monitor
    if _sleep_wake_monitor is None:
        _sleep_wake_monitor = SleepWakeMonitor()
    return _sleep_wake_monitor

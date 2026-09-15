import ctypes
import threading
import time
from ctypes.util import find_library
from Quartz import (
    CGEventCreateKeyboardEvent, CGEventSetFlags,
    CGEventPost, kCGHIDEventTap, kCGEventFlagMaskCommand,
)
import os
import subprocess
import sys

# ---
# АНТИ-ФАНТОМНАЯ ФИЛЬТРАЦИЯ 3/4-FINGER TAP (PHANTOM TAP FILTER)
#
# Проблема:
#   При системных свайпах трекпада (Mission Control, рабочие столы и т.п.)
#   macOS генерирует последовательность событий, похожую на короткий тап тремя/четырьмя пальцами.
#   Это приводило к ложным срабатываниям горячих клавиш (например, ⌘T/⌘W),
#   хотя пользователь делал свайп, а не тап.
#
# Причина:
#   Старый алгоритм определял тап только по количеству пальцев и короткой длительности касания,
#   не учитывая траекторию и скорость движения пальцев.
#
# Решение (см. on_frame, блок PHANTOM TAP):
#   1. Введён отдельный строгий порог смещения MAX_DPOS_SWIPE для фантомных тапов.
#   2. Анализируется траектория каждого пальца за последние 7 кадров (SWIPE_TRAJ_WINDOW).
#   3. Если хотя бы один палец сместился больше порога — событие не считается тапом.
#   4. Если все пальцы двигались синхронно (разброс углов < 20°) — это свайп, не тап.
#   5. Если скорость хотя бы одного пальца превышает порог — это свайп, не тап.
#   6. Дебаунс по времени и количеству пальцев исключает повторные срабатывания.
#
# Итог:
#   Фантомные срабатывания при OS-свайпах практически исключены,
#   а настоящие короткие "тапы" по-прежнему надёжно распознаются.
# ---

# --- MultitouchSupport.framework ctypes binding ---
def load_multitouch():
    try:
        return ctypes.CDLL("/System/Library/PrivateFrameworks/MultitouchSupport.framework/MultitouchSupport")
    except OSError:
        lib = find_library("MultitouchSupport")
        if lib:
            return ctypes.CDLL(lib)
    raise FileNotFoundError("MultitouchSupport.framework not found")

MT = load_multitouch()
CF = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
CFArrayRef = ctypes.c_void_p
CFIndex = ctypes.c_long
CF.CFArrayGetCount.argtypes = [CFArrayRef]
CF.CFArrayGetCount.restype = CFIndex
CF.CFArrayGetValueAtIndex.argtypes = [CFArrayRef, CFIndex]
CF.CFArrayGetValueAtIndex.restype = ctypes.c_void_p

CB_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_double, ctypes.c_int)
MT.MTDeviceCreateList.restype = CFArrayRef
MT.MTRegisterContactFrameCallback.argtypes = [ctypes.c_void_p, CB_TYPE]
MT.MTDeviceStart.argtypes = [ctypes.c_void_p, ctypes.c_int]
try:
    MT.MTDeviceStop.argtypes = [ctypes.c_void_p]
except Exception:
    pass

class MTPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float)]
class MTReadout(ctypes.Structure):
    _fields_ = [("pos", MTPoint), ("vel", MTPoint)]
class Finger(ctypes.Structure):
    _fields_ = [
        ("frame", ctypes.c_int32), ("timestamp", ctypes.c_double), ("identifier", ctypes.c_int32), ("state", ctypes.c_int32),
        ("_pad1", ctypes.c_int32 * 4), ("norm", MTReadout), ("size", ctypes.c_float), ("_pad2", ctypes.c_int32),
        ("angle", ctypes.c_float), ("major", ctypes.c_float), ("minor", ctypes.c_float), ("_pad3", ctypes.c_int32 * 5),
    ]

# --- Trackpad gesture detection logic ---
DEFAULT_MAX_DT = 0.25
DEFAULT_MAX_DPOS = 0.2  # Увеличено с 0.1 до 0.2 для более реалистичного порога движения
DEFAULT_MAX_DPOS_SWIPE = 0.07  # Новый, более строгий порог для анти-свайп фильтра
SWIPE_TRAJ_WINDOW = 7  # Окно анализа траектории (кадров)
DEFAULT_MAX_SWIPE_SPEED = 1.2  # Максимальная скорость (норм.ед./сек) для тапа
DEFAULT_SYNC_ANGLE_THRESHOLD = 20  # градусы, допустимое расхождение направлений
DEFAULT_GESTURE_RELEASE_GAP = 0.02  # минимальная пауза (сек) пустого трекпада (ускорено для быстрого повторного тапа)
DEFAULT_HISTORY_MAX_SEC = 0.25  # сколько хранить историю позиций (сек)
DEFAULT_TAP_MAX_CENTROID_PATH = 0.04  # максимум суммарного пути центроида для тапа
DEFAULT_TAP_MAX_CENTROID_NET = 0.03  # максимум смещения центроида для тапа
DEFAULT_TAP_MAX_CENTROID_SPEED = 0.6  # максимум скорости центроида для тапа (норм.ед./сек)
MIN_CENTROID_SAMPLES = 2  # минимум точек центроида для уверенной проверки

class TrackpadGestureEngine:
    def __init__(self, get_gesture_actions, run_action_func, get_active_app_name_func=None):
            # Основные колбэки и зависимости
            self.get_gesture_actions = get_gesture_actions
            self.run_action = run_action_func
            self.get_active_app_name = get_active_app_name_func

            # Служебные структуры состояния жеста
            self._active = {}               # active fingers: fid -> (x,y,ts_down)
            self._gesture_fingers = set()   # все пальцы, участвующие в текущем жесте
            self._released_fingers = set()  # уже отпущенные пальцы
            self._last_down = {}            # fid -> (x0,y0) для расчёта смещения
            self._max_move = {}             # fid -> max distance
            self._finger_history = []       # [(ts, {fid:(x,y)})] для анти-свайп анализа
            self._centroid_history = []     # [(ts, count, (cx,cy))] для анализа движений
            self._last_pos = {}             # fid -> (x,y,ts) последняя позиция

            # Тайминги
            self.start_ts = None
            self._last_activity_ts = None
            self._gesture_timeout = 1.0     # таймаут форс-сброса

            # Флаги / debounce
            self._gesture_triggered = False
            self._gesture_last_fire = {}    # gesture_name -> ts
            self._gesture_debounce = 0.6    # сек. подавления повторного жеста (может быть переопределено настройкой)
            # Дополнительный контроль: время, когда трекпад стал полностью пустым после жеста
            self._empty_since = None
            self._last_frame_ids = set()
            # Возможная переопределяемая пауза освобождения
            self._release_gap = DEFAULT_GESTURE_RELEASE_GAP
            # Пороговые значения (могут переопределяться настройками)
            self._max_dt = DEFAULT_MAX_DT
            self._max_dpos = DEFAULT_MAX_DPOS
            self._max_dpos_swipe = DEFAULT_MAX_DPOS_SWIPE
            self._max_swipe_speed = DEFAULT_MAX_SWIPE_SPEED
            self._sync_angle_threshold = DEFAULT_SYNC_ANGLE_THRESHOLD
            self._history_max_sec = DEFAULT_HISTORY_MAX_SEC
            self._tap_max_centroid_path = DEFAULT_TAP_MAX_CENTROID_PATH
            self._tap_max_centroid_net = DEFAULT_TAP_MAX_CENTROID_NET
            self._tap_max_centroid_speed = DEFAULT_TAP_MAX_CENTROID_SPEED
            self._load_gesture_settings()

            # Общие служебные поля
            self._cb = CB_TYPE(self.on_frame)
            self._running = False

    def start(self):
        """Запустить слушатель трекпада"""
        import logging
        logger = logging.getLogger("trackpad")
        
        try:
            # Проверяем, что мы не запущены уже
            if self._running:
                logger.warning("Trackpad engine уже запущен")
                return
            
            logger.info("Запуск trackpad engine...")
            
            # Получаем список устройств
            dev_array = MT.MTDeviceCreateList()
            if not dev_array:
                raise RuntimeError("Не удалось получить список multitouch устройств")
                
            device_count = CF.CFArrayGetCount(dev_array)
            if device_count == 0:
                raise RuntimeError("Trackpad не найден - список устройств пуст")
            
            logger.info(f"Найдено {device_count} multitouch устройств")
            
            # Берём первое устройство (обычно это основной trackpad)
            self.DEV = CF.CFArrayGetValueAtIndex(dev_array, 0)
            if not self.DEV:
                raise RuntimeError("Не удалось получить указатель на trackpad устройство")
            
            logger.info(f"Использую устройство с указателем: 0x{self.DEV:x}")
            
            # Регистрируем callback
            result = MT.MTRegisterContactFrameCallback(self.DEV, self._cb)
            if result != 0:
                logger.warning(f"MTRegisterContactFrameCallback вернул код: {result}")
            
            # Запускаем устройство
            result = MT.MTDeviceStart(self.DEV, 0)
            if result != 0:
                logger.warning(f"MTDeviceStart вернул код: {result}")
            
            # Помечаем как запущенный и стартуем поток мониторинга
            self._running = True
            threading.Thread(target=self._run, daemon=True).start()
            
            logger.info("Trackpad engine успешно запущен")
            
        except Exception as e:
            logger.error(f"Критическая ошибка запуска trackpad engine: {e}")
            # Очищаем состояние при ошибке
            self._running = False
            if hasattr(self, 'DEV'):
                self.DEV = None
            raise

    def _run(self):
        import logging
        logger = logging.getLogger("trackpad")
        while self._running:
            time.sleep(0.1)  # Проверяем каждые 100мс
            # Проверка таймаута для принудительного сброса застрявших жестов
            if (self._gesture_fingers and self._last_activity_ts and 
                time.time() - self._last_activity_ts > self._gesture_timeout):
                logger.debug(f"[TIMEOUT] Forcing gesture reset after {self._gesture_timeout}s of inactivity")
                logger.debug(f"[TIMEOUT] Active fingers before reset: {list(self._active.keys())}")
                logger.debug(f"[TIMEOUT] Gesture fingers before reset: {list(self._gesture_fingers)}")
                # Принудительный сброс состояния
                self._reset_gesture_state()
                logger.debug(f"[TIMEOUT] Gesture state reset complete")

    def stop(self):
        """Остановить слушатель трекпада"""
        import logging
        logger = logging.getLogger("trackpad")
        logger.info("Остановка trackpad engine...")
        
        self._running = False
        
        try:
            if hasattr(self, 'DEV') and self.DEV:
                try:
                    # Сначала пытаемся отписаться от callback
                    try:
                        # Устанавливаем пустой callback
                        empty_cb = CB_TYPE(lambda *args: None)
                        MT.MTRegisterContactFrameCallback(self.DEV, empty_cb)
                    except Exception as e:
                        logger.warning(f"Ошибка отписки от callback: {e}")
                    
                    # Останавливаем устройство
                    MT.MTDeviceStop(self.DEV)
                    logger.info("Trackpad device остановлен")
                except Exception as e:
                    logger.error(f"Ошибка остановки трекпада: {e}")
                finally:
                    # Обнуляем ссылку на устройство
                    self.DEV = None
        except Exception as e:
            logger.error(f"Критическая ошибка при остановке trackpad engine: {e}")
        
        # Сбрасываем состояние независимо от ошибок
        try:
            self._reset_gesture_state(reason="stop")
        except Exception as e:
            logger.error(f"Ошибка сброса состояния: {e}")
        
        logger.info("Trackpad engine остановлен")

    def restart(self):
        """Перезапустить слушатель трекпада"""
        import logging
        logger = logging.getLogger("trackpad")
        logger.info("Перезапуск trackpad engine после пробуждения...")
        
        try:
            # Останавливаем старый слушатель с защитой от ошибок
            old_dev = getattr(self, 'DEV', None)
            self.stop()
            
            # Даем время для полной остановки
            time.sleep(1.0)
            
            # Полностью сбрасываем состояние
            self._reset_gesture_state(reason="restart")
            
            # Очищаем старые ссылки на устройство
            if hasattr(self, 'DEV'):
                delattr(self, 'DEV')
            
            # Пытаемся запустить заново несколько раз
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    self.start()
                    logger.info(f"Trackpad engine перезапущен успешно с попытки {attempt + 1}")
                    return
                except Exception as e:
                    logger.warning(f"Попытка {attempt + 1} перезапуска trackpad engine неудачна: {e}")
                    if attempt < max_attempts - 1:
                        time.sleep(0.5)
                    else:
                        raise
            
        except Exception as e:
            logger.error(f"Критическая ошибка перезапуска trackpad engine: {e}")
            # Попытаемся хотя бы сбросить состояние
            try:
                self._reset_gesture_state(reason="restart_error")
            except:
                pass

    def _reset_gesture_state(self, reason=None):
            import logging
            logger = logging.getLogger("trackpad")
            logger.debug(f"[RESET_GESTURE_STATE] called. Reason: {reason if reason else 'unspecified'}")
            self.start_ts = None
            self._last_activity_ts = None
            self._last_down = {}
            self._max_move = {}
            self._gesture_fingers = set()
            self._released_fingers = set()
            self._active = {}
            # Не сбрасываем _gesture_triggered здесь: он освободится только после реального “пустого окна”
            # Это предотвращает бесконечные повторные срабатывания при удержании пальцев.

    def on_frame(self, dev, data, count, ts, frame):
        """Обработчик событий трекпада"""
        try:
            self._on_frame_impl(dev, data, count, ts, frame)
        except Exception as e:
            import logging
            logger = logging.getLogger("trackpad")
            logger.error(f"Критическая ошибка в on_frame: {e}", exc_info=True)
            # Сбрасываем состояние при ошибке
            try:
                self._reset_gesture_state(reason="error_recovery")
            except:
                pass
    
    def _on_frame_impl(self, dev, data, count, ts, frame):
        import logging
        logger = logging.getLogger("trackpad")
        fingers = ctypes.cast(data, ctypes.POINTER(Finger))
        # Логируем все состояния пальцев в кадре и собираем уникальные state
        fingers = ctypes.cast(data, ctypes.POINTER(Finger))
        # --- История пальцев для анти-свайп фильтра ---
        try:
            snapshot = {}
            for i in range(count):
                f = fingers[i]
                snapshot[f.identifier] = (f.norm.pos.x, f.norm.pos.y)
                self._last_pos[f.identifier] = (f.norm.pos.x, f.norm.pos.y, ts)
            # Добавляем (timestamp, snapshot)
            self._finger_history.append((ts, snapshot))
            # Обрезаем окно по длине и времени
            cutoff = ts - self._history_max_sec
            if cutoff > 0:
                self._finger_history = [(t, fr) for t, fr in self._finger_history if t >= cutoff]
            if len(self._finger_history) > SWIPE_TRAJ_WINDOW * 3:
                self._finger_history = self._finger_history[-SWIPE_TRAJ_WINDOW:]
            # История центроида для оценки общего движения
            if count > 0:
                cx = sum(pos[0] for pos in snapshot.values()) / count
                cy = sum(pos[1] for pos in snapshot.values()) / count
                self._centroid_history.append((ts, count, (cx, cy)))
                if cutoff > 0:
                    self._centroid_history = [(t, c, xy) for t, c, xy in self._centroid_history if t >= cutoff]
                if len(self._centroid_history) > SWIPE_TRAJ_WINDOW * 3:
                    self._centroid_history = self._centroid_history[-SWIPE_TRAJ_WINDOW:]
        except Exception:
            pass
        # 1. Обновляем карту активных пальцев и сохраняем DOWN-координаты и максимальное смещение
        for i in range(count):
            f = fingers[i]
            if f.state == 1:  # DOWN
                self._gesture_fingers.add(f.identifier)
                if self.start_ts is None:
                    self.start_ts = ts
                if f.identifier not in self._active:
                    self._active[f.identifier] = (f.norm.pos.x, f.norm.pos.y, ts)
                    self._last_down[f.identifier] = (f.norm.pos.x, f.norm.pos.y)
                    self._max_move[f.identifier] = 0.0
                self._last_activity_ts = time.time()
            elif f.state == 2:  # MOVE
                if f.identifier in self._last_down:
                    x0, y0 = self._last_down[f.identifier]
                    dx = abs(f.norm.pos.x - x0)
                    dy = abs(f.norm.pos.y - y0)
                    dist = (dx ** 2 + dy ** 2) ** 0.5
                    self._max_move[f.identifier] = max(self._max_move.get(f.identifier, 0.0), dist)
                    self._last_activity_ts = time.time()
            elif f.state == 4:  # UP
                if f.identifier in self._released_fingers:
                    continue
                if f.identifier not in self._gesture_fingers:
                    continue
                self._active.pop(f.identifier, None)
                self._released_fingers.add(f.identifier)
                self._last_activity_ts = time.time()
                if f.identifier in self._last_down:
                    x0, y0 = self._last_down[f.identifier]
                    current_x, current_y = f.norm.pos.x, f.norm.pos.y
                    dx = abs(current_x - x0)
                    dy = abs(current_y - y0)
                    dist = (dx ** 2 + dy ** 2) ** 0.5
                    self._max_move[f.identifier] = max(self._max_move.get(f.identifier, 0.0), dist)
        # --- СИНТЕТИЧЕСКИЙ UP: если палец исчез из кадра, считаем его отпущенным ---
        current_ids = set(fingers[i].identifier for i in range(count))
        previously_active = set(self._active.keys())
        disappeared = previously_active - current_ids
        for fid in disappeared:
            if fid in self._released_fingers:
                continue
            self._active.pop(fid, None)
            self._released_fingers.add(fid)
            self._last_activity_ts = time.time()
            if fid in self._last_down:
                x0, y0 = self._last_down[fid]
                if fid in self._last_pos:
                    current_x, current_y, _ = self._last_pos[fid]
                else:
                    current_x, current_y = x0, y0
                dx = abs(current_x - x0)
                dy = abs(current_y - y0)
                dist = (dx ** 2 + dy ** 2) ** 0.5
                self._max_move[fid] = max(self._max_move.get(fid, 0.0), dist)
        # 2. Анализ жеста когда все пальцы отпущены (активных пальцев = 0) 
        # ИЛИ когда все пальцы из gesture_fingers получили UP события
        gesture_complete = (self._gesture_fingers and len(self._active) == 0) or \
                          (self._gesture_fingers and 
                           all(fid in self._released_fingers for fid in self._gesture_fingers))
        any_down_or_move = any(f.state in (1,2) for f in fingers[:count])
        if gesture_complete and self.start_ts is not None and not any_down_or_move:
            duration = ts - self.start_ts
            nfingers = len(self._gesture_fingers)
            gesture_name = None
            max_moves = [self._max_move.get(fid, 0.0) for fid in self._gesture_fingers]
            is_tap = all(mv <= self._max_dpos for mv in max_moves)
            # Доп. фильтр против свайпа: анализ движения центроида
            centroid_points = [(t, xy) for t, c, xy in self._centroid_history if c == nfingers]
            centroid_ok = True
            if len(centroid_points) >= MIN_CENTROID_SAMPLES:
                (t0, (x0, y0)) = centroid_points[0]
                (t1, (x1, y1)) = centroid_points[-1]
                dt = t1 - t0 if t1 > t0 else 1e-6
                net = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
                path = 0.0
                for i in range(1, len(centroid_points)):
                    (ta, (xa, ya)) = centroid_points[i - 1]
                    (tb, (xb, yb)) = centroid_points[i]
                    path += ((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5
                speed = path / dt
                if net > self._tap_max_centroid_net or path > self._tap_max_centroid_path or speed > self._tap_max_centroid_speed:
                    centroid_ok = False
            if duration <= self._max_dt and is_tap and centroid_ok:
                if nfingers == 1:
                    gesture_name = 'Тап одним пальцем'
                elif nfingers == 2:
                    gesture_name = 'Тап двумя пальцами'
                elif nfingers == 3:
                    gesture_name = 'Тап тремя пальцами'
                elif nfingers == 4:
                    gesture_name = 'Тап четырьмя пальцами'
            if gesture_name and not self._gesture_triggered:
                self.handle_gesture(gesture_name)
                self._gesture_triggered = True  # блокируем до полной “тишины”
            # Сбрасываем периферийные структуры, но не снимаем флаг
            self._reset_gesture_state(reason="gesture_complete (all fingers UP)")

        # --- PHANTOM TAP: если только UP, но их 3 или 4, и нет активных пальцев/жеста ---
        if not hasattr(self, '_last_phantom_tap_ts'):
            self._last_phantom_tap_ts = 0
            self._last_phantom_tap_count = 0
        only_ups = all(f.state == 4 for f in fingers[:count])
        now = time.time()
        debounce_time = 0.3
        if only_ups and count in (3, 4) and not self._active and not self._gesture_fingers:
            # Если нет достаточной истории центроида — считаем событие неоднозначным и не распознаём тап
            centroid_points = [(t, xy) for t, c, xy in self._centroid_history if c == count]
            if len(centroid_points) < MIN_CENTROID_SAMPLES:
                return
            positions = [(f.norm.pos.x, f.norm.pos.y) for f in fingers[:count]]
            max_dist = 0.0
            for i in range(len(positions)):
                for j in range(i+1, len(positions)):
                    dx = positions[i][0] - positions[j][0]
                    dy = positions[i][1] - positions[j][1]
                    dist = (dx**2 + dy**2) ** 0.5
                    if dist > max_dist:
                        max_dist = dist
            # --- Новая фильтрация: анализируем перемещение каждого пальца за последние SWIPE_TRAJ_WINDOW кадров ---
            moved_too_much = False
            directions = []
            speeds = []
            for f in fingers[:count]:
                fid = f.identifier
                traj = [(t, fr[fid]) for t, fr in self._finger_history if fid in fr]
                if len(traj) >= 2:
                    (t0, (x0, y0)), (t1, (x1, y1)) = traj[0], traj[-1]
                    dtraj = ((x1 - x0)**2 + (y1 - y0)**2) ** 0.5
                    dt = t1 - t0 if t1 > t0 else 1e-6
                    speed = dtraj / dt
                    speeds.append(speed)
                    angle = None
                    if dtraj > 1e-4:
                        import math
                        angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
                        directions.append(angle)
                    if dtraj > self._max_dpos_swipe:
                        moved_too_much = True
                        break
            # Проверка синхронности направления (характерно для свайпа)
            sync = False
            if len(directions) >= 2:
                min_angle = min(directions)
                max_angle = max(directions)
                if abs(max_angle - min_angle) < self._sync_angle_threshold:
                    sync = True
            # Проверка скорости
            fast = any(s > self._max_swipe_speed for s in speeds)
            # Движение центроида (характерно для свайпа рабочих столов)
            (t0, (x0, y0)) = centroid_points[0]
            (t1, (x1, y1)) = centroid_points[-1]
            dt = t1 - t0 if t1 > t0 else 1e-6
            net = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            path = 0.0
            for i in range(1, len(centroid_points)):
                (ta, (xa, ya)) = centroid_points[i - 1]
                (tb, (xb, yb)) = centroid_points[i]
                path += ((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5
            centroid_fast = (path / dt) > self._tap_max_centroid_speed
            centroid_far = net > self._tap_max_centroid_net or path > self._tap_max_centroid_path
            if max_dist > self._max_dpos_swipe or moved_too_much or sync or fast or centroid_fast or centroid_far:
                logger.debug(f"[PHANTOM] filtered: max_dist={max_dist:.3f}, moved_too_much={moved_too_much}, sync={sync}, fast={fast}, speeds={speeds}")
                return
            if (
                self._last_phantom_tap_count == count and
                now - self._last_phantom_tap_ts < debounce_time
            ):
                return
            gesture_name = None
            if count == 3:
                gesture_name = 'Тап тремя пальцами'
            elif count == 4:
                gesture_name = 'Тап четырьмя пальцами'
            if gesture_name and not self._gesture_triggered:
                self.handle_gesture(gesture_name)
                self._gesture_triggered = True
                self._reset_gesture_state(reason="phantom_tap (all UP, no DOWN)")
                self._last_phantom_tap_ts = now
                self._last_phantom_tap_count = count
            return

        # --- Разблокировка жестового cooldown после реального освобождения поверхности ---
        # Условия “пусто”: нет активных пальцев, нет новых DOWN/MOVE в кадре
        # Текущие идентификаторы пальцев в кадре
        current_ids_frame = set(fingers[i].identifier for i in range(count))
        any_down_or_move_frame = any(f.state in (1,2) for f in fingers[:count])
        # Условие “пусто” теперь расширено: либо совсем нет пальцев, либо нет активных DOWN/MOVE и наши структуры пусты
        release_condition = (not current_ids_frame) or (not any_down_or_move_frame and not self._active)
        if release_condition:
            if self._gesture_triggered:
                # Засекаем момент, когда стало пусто
                if self._empty_since is None:
                    self._empty_since = time.time()
                elif time.time() - self._empty_since >= self._release_gap:
                    # Достаточная пауза — разрешаем следующий жест
                    self._gesture_triggered = False
                    self._empty_since = None
            else:
                # Пусто и не заблокировано — сбрасываем таймер
                self._empty_since = None
        else:
            # Есть активность — сбрасываем маркер пустоты
            self._empty_since = None
        self._last_frame_ids = current_ids_frame

    def handle_gesture(self, gesture_name):
        import logging
        logger = logging.getLogger("trackpad")
        logger.debug(f"[GESTURE] handle_gesture called with: {gesture_name}")

        # Подавление повтора одинакового жеста (быстрое многократное определение)
        now = time.time()
        last = self._gesture_last_fire.get(gesture_name)
        if last is not None and (now - last) < self._gesture_debounce:
            logger.debug(f"[GESTURE][DEBOUNCE] suppressed repeat of {gesture_name} ({now - last:.3f}s < {self._gesture_debounce}s)")
            return
        self._gesture_last_fire[gesture_name] = now
        
        actions = self.get_gesture_actions()
        logger.debug(f"[GESTURE] Found {len(actions)} total actions")
        
        matching_actions = [hk for hk in actions if hk.get('type') == 'trackpad' and hk.get('gesture') == gesture_name]
        logger.debug(f"[GESTURE] Found {len(matching_actions)} matching trackpad actions for '{gesture_name}'")
        
        for hk in actions:
            if hk.get('type') == 'trackpad' and hk.get('gesture') == gesture_name:
                logger.debug(f"[GESTURE] Processing action: {hk}")
                scope = hk.get('scope', 'global')
                app = hk.get('app', '')
                if scope == 'app' and app and self.get_active_app_name:
                    active_app = self.get_active_app_name()
                    logger.debug(f"[GESTURE] App scope check: need={app}, active={active_app}")
                    if not active_app or app not in active_app:
                        logger.debug(f"[GESTURE] Skipping action - app mismatch")
                        continue
                logger.debug(f"[GESTURE] Executing action: {hk.get('action')}")
                self.run_action(hk.get('action'))

    # --- Settings integration ---
    def _load_gesture_settings(self):
        """Пытаемся загрузить gesture настройки из settings.json (не критично). Формат:
        {
          "gesture_debounce": 0.5,
          "gesture_release_gap": 0.03,
          "tap_sensitivity": 60,
          "swipe_filter_strength": 70,
          "gesture_repeat_speed": 50,
          "tap_release_gap": 30
        }
        """
        try:
            import json, os
            # Используем единый путь с hotkey_engine/ui (Application Support)
            settings_path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'HotkeyMaster', 'settings.json')
            if not os.path.exists(settings_path):
                return
            st = os.stat(settings_path)
            if not hasattr(self, '_settings_mtime') or self._settings_mtime != st.st_mtime:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                def _clamp(v, lo, hi):
                    return max(lo, min(hi, v))
                def _lerp(a, b, t):
                    return a + (b - a) * t

                # --- User-friendly sliders ---
                tap_sens = data.get('tap_sensitivity')
                if isinstance(tap_sens, (int, float)):
                    t = _clamp(float(tap_sens), 0, 100) / 100.0
                    self._max_dt = _lerp(0.18, 0.32, t)
                    self._max_dpos = _lerp(0.06, 0.24, t)
                    self._tap_max_centroid_path = _lerp(0.02, 0.06, t)
                    self._tap_max_centroid_net = _lerp(0.015, 0.04, t)
                    self._tap_max_centroid_speed = _lerp(0.35, 0.8, t)

                swipe_strength = data.get('swipe_filter_strength')
                if isinstance(swipe_strength, (int, float)):
                    s = _clamp(float(swipe_strength), 0, 100) / 100.0
                    self._max_dpos_swipe = _lerp(0.10, 0.045, s)
                    self._max_swipe_speed = _lerp(1.6, 0.8, s)
                    self._sync_angle_threshold = _lerp(30, 15, s)

                repeat_speed = data.get('gesture_repeat_speed')
                if isinstance(repeat_speed, (int, float)):
                    r = _clamp(float(repeat_speed), 0, 100) / 100.0
                    self._gesture_debounce = _lerp(1.0, 0.2, r)

                release_gap = data.get('tap_release_gap')
                if isinstance(release_gap, (int, float)):
                    g = _clamp(float(release_gap), 0, 100) / 100.0
                    self._release_gap = _lerp(0.08, 0.01, g)

                # --- Backward-compatible low-level overrides ---
                gd = data.get('gesture_debounce')
                if isinstance(gd, (int, float)) and gd >= 0:
                    self._gesture_debounce = float(gd)
                rg = data.get('gesture_release_gap')
                if isinstance(rg, (int, float)) and 0 <= rg <= 0.5:
                    self._release_gap = float(rg)
                self._settings_mtime = st.st_mtime
        except Exception:
            pass

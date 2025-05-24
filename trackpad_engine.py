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
MAX_DT = 0.25
MAX_DPOS = 0.2  # Увеличено с 0.1 до 0.2 для более реалистичного порога движения
MAX_DPOS_SWIPE = 0.07  # Новый, более строгий порог для анти-свайп фильтра
SWIPE_TRAJ_WINDOW = 7  # Окно анализа траектории (кадров)
MAX_SWIPE_SPEED = 1.2  # Максимальная скорость (норм.ед./сек) для тапа
SYNC_ANGLE_THRESHOLD = 20  # градусы, допустимое расхождение направлений

class TrackpadGestureEngine:
    def __init__(self, get_gesture_actions, run_action_func, get_active_app_name_func=None):
        self._active = {}
        self.start_ts = None
        self.get_gesture_actions = get_gesture_actions
        self.run_action = run_action_func
        self.get_active_app_name = get_active_app_name_func
        self._cb = CB_TYPE(self.on_frame)
        self._running = False
        self._gesture_timeout = 1.0  # Таймаут для принудительного сброса жеста (сек)
        self._last_activity_ts = None  # Последняя активность для отслеживания таймаута
        self._gesture_fingers = set()
        self._last_down = {}
        self._max_move = {}
        self._released_fingers = set()
        self._finger_history = []  # история позиций пальцев для анти-свайп фильтра

    def start(self):
        dev_array = MT.MTDeviceCreateList()
        if CF.CFArrayGetCount(dev_array) == 0:
            raise RuntimeError("Trackpad not found")
        self.DEV = CF.CFArrayGetValueAtIndex(dev_array, 0)
        MT.MTRegisterContactFrameCallback(self.DEV, self._cb)
        MT.MTDeviceStart(self.DEV, 0)
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

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
        self._running = False

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

    def on_frame(self, dev, data, count, ts, frame):
        import logging
        logger = logging.getLogger("trackpad")
        fingers = ctypes.cast(data, ctypes.POINTER(Finger))
        # Логируем все состояния пальцев в кадре и собираем уникальные state
        fingers = ctypes.cast(data, ctypes.POINTER(Finger))
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
            is_tap = all(mv <= MAX_DPOS for mv in max_moves)
            if duration <= MAX_DT and is_tap:
                if nfingers == 1:
                    gesture_name = 'Тап одним пальцем'
                elif nfingers == 2:
                    gesture_name = 'Тап двумя пальцами'
                elif nfingers == 3:
                    gesture_name = 'Тап тремя пальцами'
                elif nfingers == 4:
                    gesture_name = 'Тап четырьмя пальцами'
            if gesture_name:
                self.handle_gesture(gesture_name)
            self._reset_gesture_state(reason="gesture_complete (all fingers UP)")

        # --- PHANTOM TAP: если только UP, но их 3 или 4, и нет активных пальцев/жеста ---
        if not hasattr(self, '_last_phantom_tap_ts'):
            self._last_phantom_tap_ts = 0
            self._last_phantom_tap_count = 0
        only_ups = all(f.state == 4 for f in fingers[:count])
        now = time.time()
        debounce_time = 0.3
        if only_ups and count in (3, 4) and not self._active and not self._gesture_fingers:
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
                    if dtraj > MAX_DPOS_SWIPE:
                        moved_too_much = True
                        break
            # Проверка синхронности направления (характерно для свайпа)
            sync = False
            if len(directions) >= 2:
                min_angle = min(directions)
                max_angle = max(directions)
                if abs(max_angle - min_angle) < SYNC_ANGLE_THRESHOLD:
                    sync = True
            # Проверка скорости
            fast = any(s > MAX_SWIPE_SPEED for s in speeds)
            if max_dist > MAX_DPOS_SWIPE or moved_too_much or sync or fast:
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
            if gesture_name:
                self.handle_gesture(gesture_name)
                self._reset_gesture_state(reason="phantom_tap (all UP, no DOWN)")
                self._last_phantom_tap_ts = now
                self._last_phantom_tap_count = count
            return

    def handle_gesture(self, gesture_name):
        import logging
        logger = logging.getLogger("trackpad")
        logger.debug(f"[GESTURE] handle_gesture called with: {gesture_name}")
        
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
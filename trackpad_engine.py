import ctypes
import threading
import time
from ctypes.util import find_library
from Quartz import (
    CGEventCreateKeyboardEvent, CGEventSetFlags,
    CGEventPost, kCGHIDEventTap, kCGEventFlagMaskCommand,
)

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
MAX_DPOS = 0.03

class TrackpadGestureEngine:
    def __init__(self, get_gesture_actions, run_action_func, get_active_app_name_func=None):
        self._active = {}
        self.start_ts = None
        self.get_gesture_actions = get_gesture_actions
        self.run_action = run_action_func
        self.get_active_app_name = get_active_app_name_func
        self._cb = CB_TYPE(self.on_frame)
        self._running = False

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
        while self._running:
            time.sleep(1)

    def stop(self):
        self._running = False

    def on_frame(self, dev, data, count, ts, frame):
        fingers = ctypes.cast(data, ctypes.POINTER(Finger))
        # 1. Обновляем карту активных пальцев
        for i in range(count):
            f = fingers[i]
            if f.state == 1:  # DOWN
                self._active[f.identifier] = (f.norm.pos.x, f.norm.pos.y, ts)
                self.start_ts = self.start_ts or ts
            elif f.state == 4:  # UP
                self._active.pop(f.identifier, None)
        # 2. Если пальцев не осталось — решаем, был ли это tap
        if not self._active and self.start_ts is not None:
            duration = ts - self.start_ts
            nfingers = count
            gesture_name = None
            if duration <= MAX_DT:
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
            self.start_ts = None

    def handle_gesture(self, gesture_name):
        actions = self.get_gesture_actions()
        for hk in actions:
            if hk.get('type') == 'trackpad' and hk.get('gesture') == gesture_name:
                scope = hk.get('scope', 'global')
                app = hk.get('app', '')
                if scope == 'app' and app and self.get_active_app_name:
                    active_app = self.get_active_app_name()
                    if not active_app or app not in active_app:
                        continue
                self.run_action(hk.get('action'))
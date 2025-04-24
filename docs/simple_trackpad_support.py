#!/usr/bin/env python3
"""
tap.py — 3-finger tap → ⌘T, 4-finger tap → ⌘W
         флаг -d / --debug выводит события
         работает на Intel- и Apple-чипах Ventura/Sonoma (14.5)
"""

import ctypes, os, time, glob, argparse, sys
from ctypes.util import find_library
from Quartz import (
    CGEventCreateKeyboardEvent, CGEventSetFlags, CGEventPost,
    kCGHIDEventTap, kCGEventFlagMaskCommand,
)

# ──────────────── CLI ────────────────
argp = argparse.ArgumentParser()
argp.add_argument("-d", "--debug", action="store_true", help="подробный лог")
args = argp.parse_args()
log = print if args.debug else (lambda *a, **k: None)

# ──────────────── MultitouchSupport ────────────────
def load_multitouch():
    fixed = ("/System/Library/PrivateFrameworks/MultitouchSupport.framework/"
             "MultitouchSupport")
    try:
        return ctypes.CDLL(fixed)
    except OSError:
        pass
    lib = find_library("MultitouchSupport")
    if lib:
        try:
            return ctypes.CDLL(lib)
        except OSError:
            pass
    pat = ("/System/Library/PrivateFrameworks/**/MultitouchSupport.framework/**/"
           "MultitouchSupport")
    for p in glob.glob(pat, recursive=True):
        if p.endswith(".tbd"):
            continue
        try:
            return ctypes.CDLL(p)
        except OSError:
            continue
    raise FileNotFoundError("MultitouchSupport.framework not found")

MT = load_multitouch()

# ──────────────── CoreFoundation helpers ────────────────
CF = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
CFArrayRef = ctypes.c_void_p
CFIndex    = ctypes.c_long

CF.CFArrayGetCount.argtypes  = [CFArrayRef]
CF.CFArrayGetCount.restype   = CFIndex
CF.CFArrayGetValueAtIndex.argtypes = [CFArrayRef, CFIndex]
CF.CFArrayGetValueAtIndex.restype  = ctypes.c_void_p

# ──────────────── приватные сигнатуры ────────────────
CB_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_void_p), ctypes.c_int,
                           ctypes.c_double, ctypes.c_int)

MT.MTDeviceCreateList.restype = CFArrayRef
MT.MTRegisterContactFrameCallback.argtypes = [ctypes.c_void_p, CB_TYPE]
MT.MTDeviceStart.argtypes = [ctypes.c_void_p, ctypes.c_int]

# ──────────────── структуры пальца ────────────────
class MTPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float)]

class MTReadout(ctypes.Structure):
    _fields_ = [("pos", MTPoint), ("vel", MTPoint)]

class Finger(ctypes.Structure):
    _fields_ = [
        ("frame",      ctypes.c_int32),
        ("timestamp",  ctypes.c_double),
        ("identifier", ctypes.c_int32),
        ("state",      ctypes.c_int32),  # 1=DOWN 2=MOVE 4=UP
        ("unk1",       ctypes.c_int32 * 4),
        ("norm",       MTReadout),
        ("size",       ctypes.c_float),
        ("z",          ctypes.c_int32),
        ("angle",      ctypes.c_float),
        ("major",      ctypes.c_float),
        ("minor",      ctypes.c_float),
        ("unk2",       ctypes.c_int32 * 5),
    ]

# ──────────────── hotkey sender ────────────────
K_T, K_W = 0x11, 0x0D
def send_cmd(code):
    if code is None:
        return
    for down in (True, False):
        ev = CGEventCreateKeyboardEvent(None, code, down)
        CGEventSetFlags(ev, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, ev)
        time.sleep(0.005)

# ──────────────── tap-детектор ────────────────
MAX_DT, MAX_DPOS = 0.25, 0.03
_active, start_ts = {}, None

def on_frame(dev, data, count, ts, frame):
    global _active, start_ts
    fingers = ctypes.cast(data, ctypes.POINTER(Finger))

    log(f"\nframe {frame}  ts={ts:.3f}  count={count}")
    for i in range(count):
        f = fingers[i]
        log(f" id={f.identifier} st={f.state} "
            f"pos=({f.norm.pos.x:.3f},{f.norm.pos.y:.3f})")

    for i in range(count):
        f = fingers[i]
        if f.state == 1:                 # DOWN
            _active[f.identifier] = (f.norm.pos.x, f.norm.pos.y, ts)
            start_ts = start_ts or ts
        elif f.state == 4:               # UP
            _active.pop(f.identifier, None)

    if not _active and start_ts:
        duration = ts - start_ts
        nfingers = count
        log(f" all-up  dt={duration:.3f}s  fingers={nfingers}")
        if duration <= MAX_DT:
            send_cmd(K_T if nfingers == 3 else K_W if nfingers == 4 else None)
            log("  ↳ TAP detected → shortcut fired")
        start_ts = None

# ──────────────── main ────────────────
def main():
    dev_list = MT.MTDeviceCreateList()
    n = CF.CFArrayGetCount(dev_list)
    if n == 0:
        sys.exit("🛑 Trackpad device list empty")

    # берём первый тач-девайс
    dev = CF.CFArrayGetValueAtIndex(dev_list, 0)
    log(f"✨ got device ptr 0x{dev:x}, total={n}")

    cb = CB_TYPE(on_frame)           # держим ссылку!

    MT.MTRegisterContactFrameCallback(dev, cb)
    MT.MTDeviceStart(dev, 0)

    print("🔥 tap-hotkeys running… Ctrl-C to quit")
    if args.debug:
        print("  (debug ON)\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()


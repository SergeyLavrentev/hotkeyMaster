import sys
import json
import threading
import Quartz
import logging

logger = logging.getLogger('hotkeymaster.capture_helper')

def main():
    result = {}
    captured = threading.Event()
    def get_mods(flags):
        MODS_MAP = {
            Quartz.kCGEventFlagMaskCommand: 'Cmd',
            Quartz.kCGEventFlagMaskShift: 'Shift',
            Quartz.kCGEventFlagMaskAlternate: 'Alt',
            Quartz.kCGEventFlagMaskControl: 'Ctrl',
        }
        mods = set()
        for mask, name in MODS_MAP.items():
            if flags & mask:
                mods.add(name)
        return sorted(mods)
    def event_callback(proxy, type_, event, refcon):
        if type_ != Quartz.kCGEventKeyDown:
            return event
        vk = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        mods = get_mods(flags)
        result['vk'] = vk
        result['mods'] = mods
        captured.set()
        Quartz.CFRunLoopStop(Quartz.CFRunLoopGetCurrent())
        return None
    mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGHIDEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        mask,
        event_callback,
        None
    )
    if not tap:
        # Print to stdout so the caller can detect the failure
        print(json.dumps({'error': 'CGEventTapCreate failed'}))
        sys.exit(1)
    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    loop = Quartz.CFRunLoopGetCurrent()
    Quartz.CFRunLoopAddSource(loop, run_loop_source, Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(tap, True)
    # Ждём нажатия
    while not captured.is_set():
        Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.1, False)
    # Output the captured combo to stdout for the parent process
    print(json.dumps(result))
    sys.exit(0)

if __name__ == '__main__':
    main()

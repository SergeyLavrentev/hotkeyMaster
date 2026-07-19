import CoreGraphics
import Foundation
import HotkeyMasterKit

final class KeyboardMonitor {
    typealias Handler = (KeyCombination) -> Void
    private var eventTap: CFMachPort?
    private var source: CFRunLoopSource?
    private var runLoop: CFRunLoop?
    private var thread: Thread?
    private let handler: Handler
    private let diagnostics: DiagnosticLog

    init(diagnostics: DiagnosticLog, handler: @escaping Handler) {
        self.diagnostics = diagnostics
        self.handler = handler
    }

    func start() {
        guard eventTap == nil else { return }
        let mask = CGEventMask(1 << CGEventType.keyDown.rawValue)
        let pointer = Unmanaged.passUnretained(self).toOpaque()
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: mask,
            callback: keyboardTapCallback,
            userInfo: pointer
        ) else {
            diagnostics.append(.error, category: "Клавиатура", message: "Event tap не создан", details: "Проверьте разрешение Accessibility.")
            return
        }
        eventTap = tap
        source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        let source = source
        thread = Thread { [weak self] in
            guard let self, let source else { return }
            let loop = CFRunLoopGetCurrent()
            self.runLoop = loop
            CFRunLoopAddSource(loop, source, .commonModes)
            CGEvent.tapEnable(tap: tap, enable: true)
            self.diagnostics.append(.success, category: "Клавиатура", message: "Глобальные хоткеи активны")
            CFRunLoopRun()
        }
        thread?.name = "HotkeyMaster.KeyboardMonitor"
        thread?.start()
    }

    func stop() {
        if let eventTap { CGEvent.tapEnable(tap: eventTap, enable: false) }
        if let runLoop { CFRunLoopStop(runLoop) }
        eventTap = nil
        source = nil
        runLoop = nil
        thread = nil
    }

    fileprivate func received(_ event: CGEvent) {
        if event.getIntegerValueField(.eventSourceUserData) == 0x484D { return }
        if event.getIntegerValueField(.keyboardEventAutorepeat) != 0 { return }
        let keyCode = UInt16(event.getIntegerValueField(.keyboardEventKeycode))
        let flags = event.flags
        var modifiers: Set<KeyModifier> = []
        if flags.contains(.maskCommand) { modifiers.insert(.command) }
        if flags.contains(.maskControl) { modifiers.insert(.control) }
        if flags.contains(.maskAlternate) { modifiers.insert(.option) }
        if flags.contains(.maskShift) { modifiers.insert(.shift) }
        handler(KeyCombination(virtualKey: keyCode, modifiers: modifiers, keyLabel: KeyLabels.label(for: keyCode)))
    }

    fileprivate func reenableTap() {
        if let eventTap { CGEvent.tapEnable(tap: eventTap, enable: true) }
    }
}

private let keyboardTapCallback: CGEventTapCallBack = { _, type, event, userInfo in
    guard let userInfo else { return Unmanaged.passUnretained(event) }
    let monitor = Unmanaged<KeyboardMonitor>.fromOpaque(userInfo).takeUnretainedValue()
    if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
        monitor.reenableTap()
    } else if type == .keyDown {
        monitor.received(event)
    }
    return Unmanaged.passUnretained(event)
}

enum KeyLabels {
    private static let map: [UInt16: String] = [
        0:"A", 1:"S", 2:"D", 3:"F", 4:"H", 5:"G", 6:"Z", 7:"X", 8:"C", 9:"V",
        11:"B", 12:"Q", 13:"W", 14:"E", 15:"R", 16:"Y", 17:"T", 18:"1", 19:"2", 20:"3",
        21:"4", 22:"6", 23:"5", 24:"=", 25:"9", 26:"7", 27:"-", 28:"8", 29:"0", 31:"O",
        32:"U", 34:"I", 35:"P", 36:"↩", 37:"L", 38:"J", 40:"K", 45:"N", 46:"M", 48:"⇥",
        49:"Space", 51:"⌫", 53:"Esc", 76:"⌤", 96:"F5", 97:"F6", 98:"F7", 99:"F3",
        100:"F8", 101:"F9", 103:"F11", 109:"F10", 111:"F12", 117:"⌦", 118:"F4", 120:"F2",
        122:"F1", 123:"←", 124:"→", 125:"↓", 126:"↑"
    ]
    static func label(for keyCode: UInt16) -> String { map[keyCode] ?? "VK_\(keyCode)" }
}

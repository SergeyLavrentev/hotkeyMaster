import AppKit
import HotkeyMasterKit
import SwiftUI

struct KeyRecorderView: NSViewRepresentable {
    @Binding var combination: KeyCombination

    func makeNSView(context: Context) -> RecorderField {
        let field = RecorderField()
        field.onCombination = { combination = $0 }
        field.stringValue = combination.displayName
        return field
    }

    func updateNSView(_ field: RecorderField, context: Context) {
        field.onCombination = { combination = $0 }
        if !field.isCapturing { field.stringValue = combination.displayName }
    }
}

final class RecorderField: NSTextField {
    var onCombination: ((KeyCombination) -> Void)?
    var isCapturing = false

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        isEditable = false
        isSelectable = false
        isBezeled = true
        bezelStyle = .roundedBezel
        alignment = .center
        placeholderString = "Нажмите сочетание…"
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override var acceptsFirstResponder: Bool { true }

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        isCapturing = true
        stringValue = "Нажмите сочетание…"
    }

    override func keyDown(with event: NSEvent) {
        guard !event.isARepeat else { return }
        var modifiers: Set<KeyModifier> = []
        if event.modifierFlags.contains(.command) { modifiers.insert(.command) }
        if event.modifierFlags.contains(.control) { modifiers.insert(.control) }
        if event.modifierFlags.contains(.option) { modifiers.insert(.option) }
        if event.modifierFlags.contains(.shift) { modifiers.insert(.shift) }
        let combo = KeyCombination(virtualKey: event.keyCode, modifiers: modifiers, keyLabel: KeyLabels.label(for: event.keyCode))
        stringValue = combo.displayName
        isCapturing = false
        onCombination?(combo)
        window?.makeFirstResponder(nil)
    }

    override func resignFirstResponder() -> Bool {
        isCapturing = false
        return super.resignFirstResponder()
    }
}

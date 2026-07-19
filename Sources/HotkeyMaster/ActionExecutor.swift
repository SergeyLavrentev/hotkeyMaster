import AppKit
import CoreGraphics
import HotkeyMasterKit

final class ActionExecutor {
    private let diagnostics: DiagnosticLog

    init(diagnostics: DiagnosticLog) { self.diagnostics = diagnostics }

    func execute(_ action: RuleAction) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            do {
                try self.executeOnMain(action)
                self.diagnostics.append(.success, category: "Действие", message: action.displayName)
            } catch {
                self.diagnostics.append(.error, category: "Действие", message: "Не удалось выполнить действие", details: error.localizedDescription)
            }
        }
    }

    private func executeOnMain(_ action: RuleAction) throws {
        switch action {
        case .openURL(let raw):
            let normalized = raw.contains("://") ? raw : "https://\(raw)"
            guard let url = URL(string: normalized), NSWorkspace.shared.open(url) else { throw ExecutionError.invalidURL }
        case .openApplication(let app):
            let url: URL?
            if !app.bundleIdentifier.isEmpty {
                url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: app.bundleIdentifier)
            } else if let path = app.path {
                url = URL(fileURLWithPath: path)
            } else {
                url = nil
            }
            guard let url else { throw ExecutionError.applicationNotFound(app.displayName) }
            let configuration = NSWorkspace.OpenConfiguration()
            NSWorkspace.shared.openApplication(at: url, configuration: configuration)
        case .runCommand(let command):
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            process.arguments = ["-lc", command]
            try process.run()
        case .pressKeys(let combination):
            guard let down = CGEvent(keyboardEventSource: nil, virtualKey: CGKeyCode(combination.virtualKey), keyDown: true),
                  let up = CGEvent(keyboardEventSource: nil, virtualKey: CGKeyCode(combination.virtualKey), keyDown: false) else {
                throw ExecutionError.eventCreationFailed
            }
            let flags = eventFlags(for: combination.modifiers)
            down.flags = flags; up.flags = flags
            down.setIntegerValueField(.eventSourceUserData, value: 0x484D)
            up.setIntegerValueField(.eventSourceUserData, value: 0x484D)
            down.post(tap: .cghidEventTap); up.post(tap: .cghidEventTap)
        case .setBrightness(let value):
            try setBrightness(value)
        case .changeBrightness(let delta):
            let current = UserDefaults.standard.integer(forKey: "lastBrightness")
            try setBrightness(min(100, max(0, (current == 0 ? 50 : current) + delta)))
        }
    }

    private func eventFlags(for modifiers: Set<KeyModifier>) -> CGEventFlags {
        var flags: CGEventFlags = []
        if modifiers.contains(.command) { flags.insert(.maskCommand) }
        if modifiers.contains(.control) { flags.insert(.maskControl) }
        if modifiers.contains(.option) { flags.insert(.maskAlternate) }
        if modifiers.contains(.shift) { flags.insert(.maskShift) }
        return flags
    }

    private func setBrightness(_ value: Int) throws {
        let candidates = [
            Bundle.main.resourceURL?.appendingPathComponent("coredisplay_helper"),
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("coredisplay_helper"),
        ].compactMap { $0 }
        guard let helper = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) else {
            throw ExecutionError.brightnessHelperMissing
        }
        let process = Process()
        process.executableURL = helper
        process.arguments = [String(Double(value) / 100.0)]
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw ExecutionError.brightnessHelperFailed }
        UserDefaults.standard.set(value, forKey: "lastBrightness")
    }
}

private enum ExecutionError: LocalizedError {
    case invalidURL, applicationNotFound(String), eventCreationFailed, brightnessHelperMissing, brightnessHelperFailed
    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Некорректный URL"
        case .applicationNotFound(let name): return "Приложение \(name) не найдено"
        case .eventCreationFailed: return "Не удалось создать клавиатурное событие"
        case .brightnessHelperMissing: return "Компонент управления яркостью не найден"
        case .brightnessHelperFailed: return "Компонент управления яркостью завершился с ошибкой"
        }
    }
}

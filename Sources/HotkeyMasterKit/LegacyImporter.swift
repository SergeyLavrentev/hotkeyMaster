import Foundation

public struct LegacyImportResult: Sendable {
    public var configuration: Configuration
    public var warnings: [String]
}

public enum LegacyImporter {
    public typealias ApplicationResolver = (String) -> ApplicationReference?

    private struct LegacyRule: Decodable {
        var id: String?
        var type: String?
        var combo: LegacyCombo?
        var gesture: String?
        var action: String?
        var scope: String?
        var app: String?
        var enabled: Bool?
    }

    private struct LegacyCombo: Decodable {
        var mods: [String]?
        var vk: UInt16?
        var disp: String?
    }

    public static func importConfiguration(
        hotkeysURL: URL,
        settingsURL: URL? = nil,
        resolveApplication: ApplicationResolver = { _ in nil }
    ) throws -> LegacyImportResult {
        let data = try Data(contentsOf: hotkeysURL)
        let legacy = try JSONDecoder().decode([LegacyRule].self, from: data)
        var warnings: [String] = []
        var rules: [Rule] = []

        for (index, item) in legacy.enumerated() {
            guard let trigger = parseTrigger(item, warning: { warnings.append("Правило \(index + 1): \($0)") }) else { continue }
            guard let action = parseAction(item.action ?? "", resolveApplication: resolveApplication) else {
                warnings.append("Правило \(index + 1): неизвестное действие «\(item.action ?? "")».")
                continue
            }
            let scope: RuleScope
            if item.scope == "app", let name = item.app, !name.isEmpty {
                scope = .application(resolveApplication(name) ?? ApplicationReference(bundleIdentifier: "", displayName: name))
            } else {
                scope = .global
            }
            rules.append(Rule(
                id: item.id.flatMap(UUID.init(uuidString:)) ?? UUID(),
                isEnabled: item.enabled ?? true,
                trigger: trigger,
                action: action,
                scope: scope
            ))
        }

        var preferences = Preferences()
        if let settingsURL, let settingsData = try? Data(contentsOf: settingsURL),
           let json = try? JSONSerialization.jsonObject(with: settingsData) as? [String: Any] {
            preferences.launchAtLogin = json["autostart"] as? Bool ?? false
            preferences.strictModifierMatching = json["strict_mod_match"] as? Bool ?? true
            let sensitivity = json["tap_sensitivity"] as? Double ?? 60
            preferences.gesturePreset = sensitivity < 40 ? .precise : (sensitivity > 75 ? .responsive : .balanced)
        }
        return LegacyImportResult(configuration: Configuration(rules: rules, preferences: preferences), warnings: warnings)
    }

    private static func parseTrigger(_ item: LegacyRule, warning: (String) -> Void) -> Trigger? {
        if item.type == "trackpad" {
            let map: [String: GestureKind] = [
                "Тап одним пальцем": .oneFingerTap,
                "Тап двумя пальцами": .twoFingerTap,
                "Тап тремя пальцами": .threeFingerTap,
                "Тап четырьмя пальцами": .fourFingerTap,
            ]
            guard let gesture = item.gesture.flatMap({ map[$0] }) else {
                warning("неизвестный жест.")
                return nil
            }
            return .gesture(gesture)
        }
        guard let combo = item.combo, let vk = combo.vk else {
            warning("не задано сочетание клавиш.")
            return nil
        }
        return .keyboard(KeyCombination(
            virtualKey: vk,
            modifiers: Set((combo.mods ?? []).compactMap(parseModifier)),
            keyLabel: keyLabel(from: combo.disp ?? "", virtualKey: vk)
        ))
    }

    private static func parseAction(_ raw: String, resolveApplication: ApplicationResolver) -> RuleAction? {
        if raw.hasPrefix("open_app ") {
            let name = String(raw.dropFirst(9)).trimmingCharacters(in: .whitespaces)
            return .openApplication(resolveApplication(name) ?? ApplicationReference(bundleIdentifier: "", displayName: name))
        }
        if raw.hasPrefix("open ") { return .openURL(String(raw.dropFirst(5)).trimmingCharacters(in: .whitespaces)) }
        if raw.hasPrefix("run ") { return .runCommand(String(raw.dropFirst(4)).trimmingCharacters(in: .whitespaces)) }
        if raw.hasPrefix("hotkey:"),
           let data = String(raw.dropFirst(7)).data(using: .utf8),
           let combo = try? JSONDecoder().decode(LegacyCombo.self, from: data),
           let vk = combo.vk {
            return .pressKeys(KeyCombination(
                virtualKey: vk,
                modifiers: Set((combo.mods ?? []).compactMap(parseModifier)),
                keyLabel: keyLabel(from: combo.disp ?? "", virtualKey: vk)
            ))
        }
        if raw.hasPrefix("brightness_set "), let value = Int(raw.split(separator: " ").last ?? "") {
            return .setBrightness(value)
        }
        if raw == "brightness_up" { return .changeBrightness(10) }
        if raw == "brightness_down" { return .changeBrightness(-10) }
        return nil
    }

    private static func parseModifier(_ value: String) -> KeyModifier? {
        switch value.lowercased() {
        case "cmd", "command": return .command
        case "ctrl", "control": return .control
        case "alt", "option": return .option
        case "shift": return .shift
        default: return nil
        }
    }

    private static func keyLabel(from display: String, virtualKey: UInt16) -> String {
        let tokens = display.split(separator: "+").map { $0.trimmingCharacters(in: .whitespaces) }
        if let last = tokens.last, !last.isEmpty { return last }
        return "VK_\(virtualKey)"
    }
}

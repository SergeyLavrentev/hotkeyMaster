import Foundation

public enum KeyModifier: String, Codable, CaseIterable, Hashable, Sendable {
    case command
    case control
    case option
    case shift

    public var symbol: String {
        switch self {
        case .command: return "⌘"
        case .control: return "⌃"
        case .option: return "⌥"
        case .shift: return "⇧"
        }
    }
}

public struct KeyCombination: Codable, Hashable, Sendable {
    public var virtualKey: UInt16
    public var modifiers: Set<KeyModifier>
    public var keyLabel: String

    public init(virtualKey: UInt16, modifiers: Set<KeyModifier> = [], keyLabel: String) {
        self.virtualKey = virtualKey
        self.modifiers = modifiers
        self.keyLabel = keyLabel
    }

    public var displayName: String {
        let order: [KeyModifier] = [.control, .option, .shift, .command]
        return order.filter(modifiers.contains).map(\.symbol).joined() + keyLabel.uppercased()
    }
}

public enum GestureKind: Int, Codable, CaseIterable, Hashable, Sendable, Identifiable {
    case threeFingerTap = 3
    case fourFingerTap = 4
    case oneFingerTap = 1
    case twoFingerTap = 2

    public var id: Int { rawValue }
    public var fingerCount: Int { rawValue }
    public var isExperimental: Bool { rawValue < 3 }
    public var displayName: String {
        switch self {
        case .oneFingerTap: return "Тап одним пальцем"
        case .twoFingerTap: return "Тап двумя пальцами"
        case .threeFingerTap: return "Тап тремя пальцами"
        case .fourFingerTap: return "Тап четырьмя пальцами"
        }
    }
}

public enum Trigger: Codable, Hashable, Sendable {
    case keyboard(KeyCombination)
    case gesture(GestureKind)

    public var displayName: String {
        switch self {
        case .keyboard(let combination): return combination.displayName
        case .gesture(let gesture): return gesture.displayName
        }
    }
}

public struct ApplicationReference: Codable, Hashable, Sendable, Identifiable {
    public var bundleIdentifier: String
    public var displayName: String
    public var path: String?

    public init(bundleIdentifier: String, displayName: String, path: String? = nil) {
        self.bundleIdentifier = bundleIdentifier
        self.displayName = displayName
        self.path = path
    }

    public var id: String { bundleIdentifier.isEmpty ? displayName : bundleIdentifier }
}

public enum RuleScope: Codable, Hashable, Sendable {
    case global
    case application(ApplicationReference)

    public var displayName: String {
        switch self {
        case .global: return "Все приложения"
        case .application(let app): return app.displayName
        }
    }
}

public enum RuleAction: Codable, Hashable, Sendable {
    case openURL(String)
    case openApplication(ApplicationReference)
    case runCommand(String)
    case pressKeys(KeyCombination)
    case setBrightness(Int)
    case changeBrightness(Int)

    public var displayName: String {
        switch self {
        case .openURL(let url): return "Открыть \(url)"
        case .openApplication(let app): return "Открыть \(app.displayName)"
        case .runCommand(let command): return "Выполнить \(command)"
        case .pressKeys(let combination): return "Нажать \(combination.displayName)"
        case .setBrightness(let value): return "Яркость \(value)%"
        case .changeBrightness(let delta): return delta >= 0 ? "Яркость +\(delta)%" : "Яркость \(delta)%"
        }
    }
}

public struct Rule: Identifiable, Codable, Hashable, Sendable {
    public var id: UUID
    public var name: String
    public var isEnabled: Bool
    public var trigger: Trigger
    public var action: RuleAction
    public var scope: RuleScope

    public init(
        id: UUID = UUID(),
        name: String = "",
        isEnabled: Bool = true,
        trigger: Trigger,
        action: RuleAction,
        scope: RuleScope = .global
    ) {
        self.id = id
        self.name = name
        self.isEnabled = isEnabled
        self.trigger = trigger
        self.action = action
        self.scope = scope
    }
}

public enum GesturePreset: String, Codable, CaseIterable, Sendable, Identifiable {
    case precise
    case balanced
    case responsive
    case custom

    public var id: String { rawValue }
    public var displayName: String {
        switch self {
        case .precise: return "Точный"
        case .balanced: return "Сбалансированный"
        case .responsive: return "Отзывчивый"
        case .custom: return "Свой"
        }
    }
}

public struct GestureThresholds: Codable, Equatable, Sendable {
    public var maximumDuration: TimeInterval
    public var maximumFingerMovement: Double
    public var maximumCentroidMovement: Double
    public var maximumStartSpread: TimeInterval
    public var minimumReleaseGap: TimeInterval
    public var repeatDelay: TimeInterval

    public init(
        maximumDuration: TimeInterval,
        maximumFingerMovement: Double,
        maximumCentroidMovement: Double,
        maximumStartSpread: TimeInterval,
        minimumReleaseGap: TimeInterval,
        repeatDelay: TimeInterval
    ) {
        self.maximumDuration = maximumDuration
        self.maximumFingerMovement = maximumFingerMovement
        self.maximumCentroidMovement = maximumCentroidMovement
        self.maximumStartSpread = maximumStartSpread
        self.minimumReleaseGap = minimumReleaseGap
        self.repeatDelay = repeatDelay
    }

    public static let precise = GestureThresholds(
        maximumDuration: 0.32, maximumFingerMovement: 0.075,
        maximumCentroidMovement: 0.050, maximumStartSpread: 0.12,
        minimumReleaseGap: 0.035, repeatDelay: 0.55
    )
    public static let balanced = GestureThresholds(
        maximumDuration: 0.42, maximumFingerMovement: 0.11,
        maximumCentroidMovement: 0.075, maximumStartSpread: 0.16,
        minimumReleaseGap: 0.025, repeatDelay: 0.38
    )
    public static let responsive = GestureThresholds(
        maximumDuration: 0.55, maximumFingerMovement: 0.15,
        maximumCentroidMovement: 0.10, maximumStartSpread: 0.20,
        minimumReleaseGap: 0.015, repeatDelay: 0.22
    )
}

public struct Preferences: Codable, Equatable, Sendable {
    public var launchAtLogin: Bool
    public var strictModifierMatching: Bool
    public var gesturePreset: GesturePreset
    public var customGestureThresholds: GestureThresholds
    public var experimentalGestures: Bool
    public var showMenuBarIcon: Bool

    public init(
        launchAtLogin: Bool = false,
        strictModifierMatching: Bool = true,
        gesturePreset: GesturePreset = .balanced,
        customGestureThresholds: GestureThresholds = .balanced,
        experimentalGestures: Bool = false,
        showMenuBarIcon: Bool = true
    ) {
        self.launchAtLogin = launchAtLogin
        self.strictModifierMatching = strictModifierMatching
        self.gesturePreset = gesturePreset
        self.customGestureThresholds = customGestureThresholds
        self.experimentalGestures = experimentalGestures
        self.showMenuBarIcon = showMenuBarIcon
    }

    public var effectiveGestureThresholds: GestureThresholds {
        switch gesturePreset {
        case .precise: return .precise
        case .balanced: return .balanced
        case .responsive: return .responsive
        case .custom: return customGestureThresholds
        }
    }
}

public struct Configuration: Codable, Equatable, Sendable {
    public var schemaVersion: Int
    public var rules: [Rule]
    public var preferences: Preferences

    public init(schemaVersion: Int = 2, rules: [Rule] = [], preferences: Preferences = Preferences()) {
        self.schemaVersion = schemaVersion
        self.rules = rules
        self.preferences = preferences
    }
}

public enum DiagnosticLevel: String, Codable, Sendable { case info, success, warning, error }

public struct DiagnosticEvent: Identifiable, Codable, Sendable, Equatable {
    public var id: UUID
    public var timestamp: Date
    public var level: DiagnosticLevel
    public var category: String
    public var message: String
    public var details: String?

    public init(
        id: UUID = UUID(), timestamp: Date = Date(), level: DiagnosticLevel,
        category: String, message: String, details: String? = nil
    ) {
        self.id = id
        self.timestamp = timestamp
        self.level = level
        self.category = category
        self.message = message
        self.details = details
    }
}

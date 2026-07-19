import Foundation

public enum RuleValidationIssue: Equatable, Sendable {
    case missingKey
    case missingURL
    case missingApplication
    case missingCommand
    case invalidBrightness
    case conflictingRule(UUID)

    public var message: String {
        switch self {
        case .missingKey: return "Укажите клавишу для сочетания."
        case .missingURL: return "Укажите адрес сайта."
        case .missingApplication: return "Выберите приложение."
        case .missingCommand: return "Укажите команду."
        case .invalidBrightness: return "Яркость должна быть от 0 до 100%."
        case .conflictingRule: return "Триггер конфликтует с другим включённым правилом."
        }
    }
}

public enum RuleValidator {
    public static func validate(_ rule: Rule, among rules: [Rule], strictModifiers: Bool) -> [RuleValidationIssue] {
        var issues: [RuleValidationIssue] = []
        if case .keyboard(let combination) = rule.trigger, combination.keyLabel.isEmpty {
            issues.append(.missingKey)
        }
        switch rule.action {
        case .openURL(let value) where value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty:
            issues.append(.missingURL)
        case .openApplication(let app) where app.id.isEmpty:
            issues.append(.missingApplication)
        case .runCommand(let value) where value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty:
            issues.append(.missingCommand)
        case .pressKeys(let combination) where combination.keyLabel.isEmpty:
            issues.append(.missingKey)
        case .setBrightness(let value) where !(0...100).contains(value):
            issues.append(.invalidBrightness)
        default:
            break
        }
        if let conflict = firstConflict(for: rule, among: rules, strictModifiers: strictModifiers) {
            issues.append(.conflictingRule(conflict.id))
        }
        return issues
    }

    public static func firstConflict(for candidate: Rule, among rules: [Rule], strictModifiers: Bool) -> Rule? {
        guard candidate.isEnabled else { return nil }
        return rules.first { other in
            guard other.id != candidate.id, other.isEnabled, scopesOverlap(candidate.scope, other.scope) else { return false }
            switch (candidate.trigger, other.trigger) {
            case (.gesture(let lhs), .gesture(let rhs)):
                return lhs == rhs
            case (.keyboard(let lhs), .keyboard(let rhs)):
                guard lhs.virtualKey == rhs.virtualKey else { return false }
                if strictModifiers { return lhs.modifiers == rhs.modifiers }
                return lhs.modifiers.isSubset(of: rhs.modifiers) || rhs.modifiers.isSubset(of: lhs.modifiers)
            default:
                return false
            }
        }
    }

    public static func scopesOverlap(_ lhs: RuleScope, _ rhs: RuleScope) -> Bool {
        switch (lhs, rhs) {
        case (.global, _), (_, .global): return true
        case (.application(let left), .application(let right)):
            if !left.bundleIdentifier.isEmpty && !right.bundleIdentifier.isEmpty {
                return left.bundleIdentifier == right.bundleIdentifier
            }
            return left.displayName.caseInsensitiveCompare(right.displayName) == .orderedSame
        }
    }
}

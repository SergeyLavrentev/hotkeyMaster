import Foundation
import HotkeyMasterKit

enum CheckFailure: Error, CustomStringConvertible {
    case failed(String)
    var description: String {
        switch self { case .failed(let message): return message }
    }
}

@main
struct HotkeyMasterChecks {
    static func main() throws {
        try recognizesThreeFingerTap()
        try rejectsSwipe()
        try rejectsShortCoherentSwipeInResponsiveProfile()
        try acceptsIncoherentTapMovement()
        try rejectsLongPress()
        try rejectsNonSimultaneousFingers()
        try checksExperimentalGestureGate()
        try checksGestureIsolation()
        try recognizesFourFingerTapWithSequentialRelease()
        try checksPresetOrdering()
        try checksConfigurationRoundTrip()
        try checksLegacyImport()
        try checksConflicts()
        try checksBundleIdentifierScopes()
        print("HotkeyMasterChecks: 14 checks passed")
    }

    static func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
        if !condition() { throw CheckFailure.failed(message) }
    }

    static func recognizesThreeFingerTap() throws {
        let result = replay([
            frame(0.00, touching: points(3, offset: 0)),
            frame(0.07, moving: points(3, offset: 0.01)),
            frame(0.15, lifted: points(3, offset: 0.01)),
        ])
        guard case .recognized(.threeFingerTap, let metrics) = result else { throw CheckFailure.failed("Three-finger tap was not recognized") }
        try require(metrics.fingerCount == 3, "Wrong finger count")
        try require(abs(metrics.duration - 0.15) < 0.001, "Wrong gesture duration")
    }

    static func rejectsSwipe() throws {
        let result = replay([
            frame(0.00, touching: points(3, offset: 0)),
            frame(0.08, moving: points(3, offset: 0.08)),
            frame(0.14, lifted: points(3, offset: 0.08)),
        ])
        guard case .rejected(let reason, _) = result else { throw CheckFailure.failed("Swipe was recognized as a tap") }
        switch reason {
        case .fingerMovedTooFar, .centroidMovedTooFar, .coherentSwipe: break
        default: throw CheckFailure.failed("Unexpected swipe rejection reason")
        }
    }

    static func rejectsShortCoherentSwipeInResponsiveProfile() throws {
        let classifier = GestureClassifier(thresholds: .responsive)
        let result = replay([
            frame(0.00, touching: points(3, offset: 0)),
            frame(0.08, moving: points(3, offset: 0.045)),
            frame(0.14, lifted: points(3, offset: 0.045)),
        ], classifier: classifier)
        guard case .rejected(.coherentSwipe, let metrics) = result else {
            throw CheckFailure.failed("Responsive profile accepted a short coherent swipe")
        }
        try require((metrics?.directionalCoherence ?? 0) > 0.95, "Coherent swipe direction was not measured")
    }

    static func acceptsIncoherentTapMovement() throws {
        let start = points(3, offset: 0)
        let moved = [
            (start[0].0 + 0.025, start[0].1),
            (start[1].0 - 0.020, start[1].1 + 0.015),
            (start[2].0, start[2].1 - 0.020),
        ]
        let result = replay([
            frame(0.00, touching: start),
            frame(0.08, moving: moved),
            frame(0.15, lifted: moved),
        ], classifier: GestureClassifier(thresholds: .responsive))
        guard case .recognized(.threeFingerTap, let metrics) = result else {
            throw CheckFailure.failed("Small incoherent tap movement was rejected as a swipe")
        }
        try require(metrics.directionalCoherence < 0.5, "Tap jitter looked directionally coherent")
    }

    static func rejectsLongPress() throws {
        let result = replay([frame(0, touching: points(4, offset: 0)), frame(0.6, lifted: points(4, offset: 0))])
        guard case .rejected(.tooLong, _) = result else { throw CheckFailure.failed("Long press was not rejected") }
    }

    static func rejectsNonSimultaneousFingers() throws {
        let first = [TouchContact(id: 0, state: .touching, x: 0.2, y: 0.3)]
        let second = first + [TouchContact(id: 1, state: .touching, x: 0.4, y: 0.3)]
        let third = second + [TouchContact(id: 2, state: .touching, x: 0.6, y: 0.3)]
        let result = replay([
            TouchFrame(timestamp: 0, contacts: first),
            TouchFrame(timestamp: 0.09, contacts: second),
            TouchFrame(timestamp: 0.18, contacts: third),
            frame(0.22, lifted: points(3, offset: 0)),
        ])
        guard case .rejected(.fingersStartedTooFarApart, _) = result else { throw CheckFailure.failed("Sequential fingers were not rejected") }
    }

    static func checksExperimentalGestureGate() throws {
        let frames = [frame(0, touching: points(1, offset: 0)), frame(0.1, lifted: points(1, offset: 0))]
        guard case .rejected(.experimentalGestureDisabled, _) = replay(frames) else { throw CheckFailure.failed("Experimental gesture was not gated") }
        let classifier = GestureClassifier(thresholds: .balanced, experimentalGesturesEnabled: true)
        guard case .recognized(.oneFingerTap, _) = replay(frames, classifier: classifier) else { throw CheckFailure.failed("Enabled experimental gesture failed") }
    }

    static func checksGestureIsolation() throws {
        let classifier = GestureClassifier()
        _ = replay([frame(0, touching: points(3, offset: 0)), frame(0.6, lifted: points(3, offset: 0))], classifier: classifier)
        guard case .recognized(.fourFingerTap, let metrics) = replay([frame(1, touching: points(4, offset: 0)), frame(1.1, lifted: points(4, offset: 0))], classifier: classifier) else {
            throw CheckFailure.failed("Gesture state leaked into the next gesture")
        }
        try require(metrics.fingerCount == 4, "Gesture state was not isolated")
    }

    static func recognizesFourFingerTapWithSequentialRelease() throws {
        let initial = points(4, offset: 0)
        let firstLift = initial.enumerated().map { index, point in
            TouchContact(id: Int32(index), state: index == 0 ? .lifted : .moving, x: point.0, y: point.1)
        }
        let secondLift = initial.enumerated().map { index, point in
            TouchContact(id: Int32(index), state: index < 2 ? .lifted : .moving, x: point.0, y: point.1)
        }
        let result = replay([
            frame(0, touching: initial),
            TouchFrame(timestamp: 0.10, contacts: firstLift),
            TouchFrame(timestamp: 0.13, contacts: secondLift),
            frame(0.17, lifted: initial),
        ])
        guard case .recognized(.fourFingerTap, _) = result else {
            throw CheckFailure.failed("Sequential finger release was mistaken for centroid movement")
        }
    }

    static func checksPresetOrdering() throws {
        try require(GestureThresholds.precise.maximumDuration < GestureThresholds.balanced.maximumDuration, "Precise duration must be stricter")
        try require(GestureThresholds.balanced.maximumDuration < GestureThresholds.responsive.maximumDuration, "Responsive duration must be looser")
        try require(GestureThresholds.precise.maximumFingerMovement < GestureThresholds.balanced.maximumFingerMovement, "Precise movement must be stricter")
        try require(GestureThresholds.balanced.maximumFingerMovement < GestureThresholds.responsive.maximumFingerMovement, "Responsive movement must be looser")
    }

    static func checksConfigurationRoundTrip() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = ConfigurationStore(configurationURL: directory.appendingPathComponent("configuration.json"))
        let configuration = Configuration(rules: [Rule(trigger: .gesture(.threeFingerTap), action: .pressKeys(KeyCombination(virtualKey: 17, modifiers: [.command], keyLabel: "T")))])
        try store.save(configuration)
        let loaded = try store.load()
        try require(loaded == configuration, "Configuration round-trip failed")
    }

    static func checksLegacyImport() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("hotkeys.json")
        let json = """
        [{"type":"trackpad","gesture":"Тап тремя пальцами","action":"hotkey:{\\"mods\\":[\\"cmd\\",\\"shift\\"],\\"vk\\":17,\\"disp\\":\\"Cmd + Shift + T\\"}","scope":"global","enabled":true}]
        """
        try Data(json.utf8).write(to: url)
        let result = try LegacyImporter.importConfiguration(hotkeysURL: url)
        try require(result.configuration.rules.count == 1, "Legacy rule was not imported")
        guard case .pressKeys(let combination) = result.configuration.rules[0].action else { throw CheckFailure.failed("Legacy action has wrong type") }
        try require(combination.modifiers == [.command, .shift], "Legacy modifiers were not normalized")
    }

    static func checksConflicts() throws {
        let trigger = Trigger.keyboard(KeyCombination(virtualKey: 40, modifiers: [.command], keyLabel: "K"))
        let base = Rule(trigger: trigger, action: .openURL("https://example.com"))
        let conflicting = Rule(trigger: trigger, action: .openURL("https://example.org"))
        try require(RuleValidator.firstConflict(for: conflicting, among: [base], strictModifiers: true)?.id == base.id, "Conflict was not found")
        var disabled = base; disabled.isEnabled = false
        try require(RuleValidator.firstConflict(for: conflicting, among: [disabled], strictModifiers: true) == nil, "Disabled rule caused a conflict")
    }

    static func checksBundleIdentifierScopes() throws {
        let first = RuleScope.application(ApplicationReference(bundleIdentifier: "com.example.one", displayName: "Example"))
        let second = RuleScope.application(ApplicationReference(bundleIdentifier: "com.example.two", displayName: "Example"))
        try require(!RuleValidator.scopesOverlap(first, second), "Application scopes used display name instead of bundle ID")
    }

    static func replay(_ frames: [TouchFrame], classifier: GestureClassifier = GestureClassifier()) -> GestureClassification? {
        GestureReplay(name: "check", frames: frames).classify(using: classifier)
    }
    static func points(_ count: Int, offset: Double) -> [(Double, Double)] { (0..<count).map { (0.2 + Double($0) * 0.15 + offset, 0.4 + offset) } }
    static func frame(_ time: Double, touching points: [(Double, Double)]) -> TouchFrame { makeFrame(time, state: .touching, points: points) }
    static func frame(_ time: Double, moving points: [(Double, Double)]) -> TouchFrame { makeFrame(time, state: .moving, points: points) }
    static func frame(_ time: Double, lifted points: [(Double, Double)]) -> TouchFrame { makeFrame(time, state: .lifted, points: points) }
    static func makeFrame(_ time: Double, state: TouchState, points: [(Double, Double)]) -> TouchFrame {
        TouchFrame(timestamp: time, contacts: points.enumerated().map { TouchContact(id: Int32($0.offset), state: state, x: $0.element.0, y: $0.element.1) })
    }
}

import AppKit
import Combine
import HotkeyMasterKit

@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()

    @Published var configuration: Configuration
    @Published var selectedRuleID: Rule.ID?
    @Published var lastFrame = TouchFrame(timestamp: 0, contacts: [])
    @Published var lastClassification: GestureClassification?
    @Published var accessibilityGranted = PermissionManager.accessibilityGranted
    @Published var availableApplications: [ApplicationReference] = []
    @Published var migrationWarnings: [String] = []

    let diagnostics = DiagnosticLog()
    private let store = ConfigurationStore()
    private lazy var executor = ActionExecutor(diagnostics: diagnostics)
    private var keyboardMonitor: KeyboardMonitor?
    private var trackpadMonitor: TrackpadMonitor?
    private var lastGestureFire: [GestureKind: TimeInterval] = [:]
    private var saveWorkItem: DispatchWorkItem?
    private var hasStarted = false

    private init() {
        configuration = Configuration()
        availableApplications = ApplicationCatalog.applications()
        configuration = loadInitialConfiguration()
    }

    func start() {
        guard !hasStarted else { return }
        hasStarted = true
        accessibilityGranted = PermissionManager.accessibilityGranted
        keyboardMonitor = KeyboardMonitor(diagnostics: diagnostics) { [weak self] combination in
            Task { @MainActor in self?.handleKeyboard(combination) }
        }
        keyboardMonitor?.start()
        trackpadMonitor = TrackpadMonitor(
            diagnostics: diagnostics,
            thresholds: configuration.preferences.effectiveGestureThresholds,
            experimentalGestures: configuration.preferences.experimentalGestures,
            classificationHandler: { [weak self] result in
                Task { @MainActor in self?.handleGestureClassification(result) }
            },
            frameHandler: { [weak self] frame in
                Task { @MainActor in self?.lastFrame = frame }
            }
        )
        trackpadMonitor?.start()
        diagnostics.append(.info, category: "Приложение", message: "HotkeyMaster запущен")
    }

    func stop() {
        keyboardMonitor?.stop()
        trackpadMonitor?.stop()
        keyboardMonitor = nil
        trackpadMonitor = nil
        hasStarted = false
        persistNow()
    }

    func addRule(_ rule: Rule) {
        configuration.rules.append(rule)
        selectedRuleID = rule.id
        configurationChanged()
    }

    func updateRule(_ rule: Rule) {
        guard let index = configuration.rules.firstIndex(where: { $0.id == rule.id }) else { return }
        configuration.rules[index] = rule
        configurationChanged()
    }

    func deleteRules(at offsets: IndexSet) {
        configuration.rules.remove(atOffsets: offsets)
        configurationChanged()
    }

    func deleteRule(id: Rule.ID) {
        configuration.rules.removeAll { $0.id == id }
        if selectedRuleID == id { selectedRuleID = nil }
        configurationChanged()
    }

    func setRuleEnabled(id: Rule.ID, enabled: Bool) {
        guard let index = configuration.rules.firstIndex(where: { $0.id == id }) else { return }
        configuration.rules[index].isEnabled = enabled
        configurationChanged()
    }

    func preferencesChanged() {
        trackpadMonitor?.update(
            thresholds: configuration.preferences.effectiveGestureThresholds,
            experimentalGestures: configuration.preferences.experimentalGestures
        )
        configurationChanged()
    }

    func setLaunchAtLogin(_ enabled: Bool) {
        do {
            try LoginItemManager.setEnabled(enabled)
            configuration.preferences.launchAtLogin = LoginItemManager.isEnabled
            configurationChanged()
        } catch {
            configuration.preferences.launchAtLogin = LoginItemManager.isEnabled
            diagnostics.append(.error, category: "Автозапуск", message: "Не удалось изменить автозапуск", details: error.localizedDescription)
        }
    }

    func refreshPermissions() { accessibilityGranted = PermissionManager.accessibilityGranted }

    func persistNow() {
        saveWorkItem?.cancel()
        do { try store.save(configuration) }
        catch { diagnostics.append(.error, category: "Настройки", message: "Не удалось сохранить настройки", details: error.localizedDescription) }
    }

    private func configurationChanged() {
        saveWorkItem?.cancel()
        let snapshot = configuration
        let item = DispatchWorkItem { [store, weak diagnostics] in
            do { try store.save(snapshot) }
            catch { diagnostics?.append(.error, category: "Настройки", message: "Не удалось сохранить настройки", details: error.localizedDescription) }
        }
        saveWorkItem = item
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 0.25, execute: item)
    }

    private func loadInitialConfiguration() -> Configuration {
        if store.exists {
            do { return try store.load() }
            catch { diagnostics.append(.error, category: "Миграция", message: "Новая конфигурация повреждена", details: error.localizedDescription) }
        }
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("HotkeyMaster", isDirectory: true)
        let candidates = [support.appendingPathComponent("hotkeys.json"), URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("hotkeys.json")]
        if let source = candidates.first(where: { FileManager.default.fileExists(atPath: $0.path) }) {
            do {
                let result = try LegacyImporter.importConfiguration(
                    hotkeysURL: source,
                    settingsURL: support.appendingPathComponent("settings.json"),
                    resolveApplication: ApplicationCatalog.resolveLegacyName
                )
                migrationWarnings = result.warnings
                try store.save(result.configuration)
                diagnostics.append(.success, category: "Миграция", message: "Импортировано правил: \(result.configuration.rules.count)")
                return result.configuration
            } catch {
                diagnostics.append(.error, category: "Миграция", message: "Не удалось импортировать Python-конфигурацию", details: error.localizedDescription)
            }
        }
        return Configuration(rules: Self.defaultRules)
    }

    private func handleKeyboard(_ incoming: KeyCombination) {
        for rule in matchingRules where rule.isEnabled {
            guard case .keyboard(let expected) = rule.trigger, expected.virtualKey == incoming.virtualKey else { continue }
            let matches = configuration.preferences.strictModifierMatching
                ? expected.modifiers == incoming.modifiers
                : expected.modifiers.isSubset(of: incoming.modifiers)
            if matches { fire(rule); break }
        }
    }

    private func handleGestureClassification(_ result: GestureClassification) {
        lastClassification = result
        switch result {
        case .recognized(let gesture, let metrics):
            diagnostics.append(.success, category: "Жест", message: "Распознан: \(gesture.displayName)", details: Self.metricsDescription(metrics))
            let now = ProcessInfo.processInfo.systemUptime
            let delay = configuration.preferences.effectiveGestureThresholds.repeatDelay
            if let last = lastGestureFire[gesture], now - last < delay {
                diagnostics.append(.info, category: "Жест", message: "Повтор подавлен", details: String(format: "Пауза %.0f мс", (now - last) * 1000))
                return
            }
            lastGestureFire[gesture] = now
            for rule in matchingRules where rule.isEnabled {
                if case .gesture(gesture) = rule.trigger { fire(rule); break }
            }
        case .rejected(let reason, let metrics):
            diagnostics.append(.warning, category: "Жест", message: "Отклонён", details: [reason.message, metrics.map(Self.metricsDescription)].compactMap { $0 }.joined(separator: " "))
        }
    }

    private var matchingRules: [Rule] {
        let frontmost = NSWorkspace.shared.frontmostApplication
        return configuration.rules.filter { rule in
            switch rule.scope {
            case .global: return true
            case .application(let app):
                if !app.bundleIdentifier.isEmpty { return frontmost?.bundleIdentifier == app.bundleIdentifier }
                return frontmost?.localizedName?.caseInsensitiveCompare(app.displayName) == .orderedSame
            }
        }
    }

    private func fire(_ rule: Rule) {
        diagnostics.append(.info, category: "Правило", message: rule.name.isEmpty ? rule.trigger.displayName : rule.name, details: rule.action.displayName)
        executor.execute(rule.action)
    }

    private static func metricsDescription(_ metrics: GestureMetrics) -> String {
        String(format: "%d пальца, %.0f мс, движение %.3f, центр %.3f", metrics.fingerCount, metrics.duration * 1000, metrics.maximumFingerMovement, metrics.centroidMovement)
    }

    private static let defaultRules: [Rule] = [
        Rule(trigger: .gesture(.threeFingerTap), action: .pressKeys(KeyCombination(virtualKey: 17, modifiers: [.command], keyLabel: "T"))),
        Rule(trigger: .gesture(.fourFingerTap), action: .pressKeys(KeyCombination(virtualKey: 13, modifiers: [.command], keyLabel: "W"))),
    ]
}

import HotkeyMasterKit
import SwiftUI

struct RuleEditorView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var model: AppModel
    @State private var draft: Rule
    let allRules: [Rule]
    let onSave: (Rule) -> Void

    init(rule: Rule, allRules: [Rule], onSave: @escaping (Rule) -> Void) {
        _draft = State(initialValue: rule)
        self.allRules = allRules
        self.onSave = onSave
    }

    private var issues: [RuleValidationIssue] {
        RuleValidator.validate(draft, among: allRules, strictModifiers: model.configuration.preferences.strictModifierMatching)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Настройка правила").font(.title2.bold())
                Spacer()
                Toggle("Включено", isOn: $draft.isEnabled).toggleStyle(.switch)
            }
            .padding(20)
            Divider()
            Form {
                Section("Название") {
                    TextField("Необязательно", text: $draft.name)
                }
                Section("Триггер") { triggerEditor }
                Section("Действие") { actionEditor }
                Section("Где работает") { scopeEditor }
                if !issues.isEmpty {
                    Section {
                        ForEach(Array(issues.enumerated()), id: \.offset) { _, issue in
                            Label(issue.message, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                        }
                    }
                }
            }
            .formStyle(.grouped)
            Divider()
            HStack {
                Button("Отменить", role: .cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Сохранить") { onSave(draft); dismiss() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!issues.isEmpty)
            }
            .padding(20)
        }
        .frame(width: 610, height: 610)
    }

    @ViewBuilder private var triggerEditor: some View {
        Picker("Тип", selection: Binding(
            get: { if case .keyboard = draft.trigger { return 0 }; return 1 },
            set: { draft.trigger = $0 == 0 ? .keyboard(KeyCombination(virtualKey: 49, modifiers: [.command], keyLabel: "Space")) : .gesture(.threeFingerTap) }
        )) { Text("Клавиатура").tag(0); Text("Трекпад").tag(1) }
        .pickerStyle(.segmented)

        switch draft.trigger {
        case .keyboard(let combo):
            KeyRecorderView(combination: Binding(get: { combo }, set: { draft.trigger = .keyboard($0) }))
        case .gesture(let gesture):
            Picker("Жест", selection: Binding(get: { gesture }, set: { draft.trigger = .gesture($0) })) {
                ForEach(GestureKind.allCases.filter { !$0.isExperimental || model.configuration.preferences.experimentalGestures }) { gesture in
                    Text(gesture.displayName + (gesture.isExperimental ? " (экспериментальный)" : "")).tag(gesture)
                }
            }
        }
    }

    @ViewBuilder private var actionEditor: some View {
        Picker("Тип", selection: Binding(get: { actionType }, set: setActionType)) {
            Text("Открыть сайт").tag(0)
            Text("Открыть приложение").tag(1)
            Text("Выполнить команду").tag(2)
            Text("Нажать клавиши").tag(3)
            Text("Установить яркость").tag(4)
            Text("Изменить яркость").tag(5)
        }
        switch draft.action {
        case .openURL(let value):
            TextField("https://example.com", text: Binding(get: { value }, set: { draft.action = .openURL($0) }))
        case .openApplication(let app):
            ApplicationPicker(selection: Binding(get: { app }, set: { draft.action = .openApplication($0) }))
        case .runCommand(let command):
            TextField("/path/to/command", text: Binding(get: { command }, set: { draft.action = .runCommand($0) }))
            Text("Команда выполняется через `/bin/zsh -lc` с правами текущего пользователя.").font(.caption).foregroundStyle(.secondary)
        case .pressKeys(let combo):
            KeyRecorderView(combination: Binding(get: { combo }, set: { draft.action = .pressKeys($0) }))
        case .setBrightness(let value):
            HStack { Slider(value: Binding(get: { Double(value) }, set: { draft.action = .setBrightness(Int($0.rounded())) }), in: 0...100); Text("\(value)%").monospacedDigit().frame(width: 45) }
        case .changeBrightness(let delta):
            Stepper("Изменение: \(delta > 0 ? "+" : "")\(delta)%", value: Binding(get: { delta }, set: { draft.action = .changeBrightness($0) }), in: -50...50, step: 5)
        }
    }

    @ViewBuilder private var scopeEditor: some View {
        Picker("Область", selection: Binding(
            get: { if case .global = draft.scope { return 0 }; return 1 },
            set: { value in
                if value == 0 { draft.scope = .global }
                else { draft.scope = .application(model.availableApplications.first ?? ApplicationReference(bundleIdentifier: "", displayName: "")) }
            }
        )) { Text("Все приложения").tag(0); Text("Одно приложение").tag(1) }
        .pickerStyle(.segmented)
        if case .application(let app) = draft.scope {
            ApplicationPicker(selection: Binding(get: { app }, set: { draft.scope = .application($0) }))
        }
    }

    private var actionType: Int {
        switch draft.action {
        case .openURL: return 0
        case .openApplication: return 1
        case .runCommand: return 2
        case .pressKeys: return 3
        case .setBrightness: return 4
        case .changeBrightness: return 5
        }
    }

    private func setActionType(_ value: Int) {
        switch value {
        case 0: draft.action = .openURL("https://")
        case 1: draft.action = .openApplication(model.availableApplications.first ?? ApplicationReference(bundleIdentifier: "", displayName: ""))
        case 2: draft.action = .runCommand("")
        case 3: draft.action = .pressKeys(KeyCombination(virtualKey: 49, modifiers: [.command], keyLabel: "Space"))
        case 4: draft.action = .setBrightness(80)
        default: draft.action = .changeBrightness(10)
        }
    }
}

private struct ApplicationPicker: View {
    @EnvironmentObject private var model: AppModel
    @Binding var selection: ApplicationReference
    var body: some View {
        Picker("Приложение", selection: $selection) {
            ForEach(model.availableApplications) { app in Text(app.displayName).tag(app) }
        }
        .searchable(text: .constant(""))
    }
}

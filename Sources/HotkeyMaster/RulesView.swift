import HotkeyMasterKit
import SwiftUI

private struct EditableRule: Identifiable {
    var rule: Rule
    var id: UUID { rule.id }
}

struct RulesView: View {
    @EnvironmentObject private var model: AppModel
    @State private var editor: EditableRule?
    @State private var query = ""
    @State private var filter: TriggerFilter = .all

    private enum TriggerFilter: String, CaseIterable, Identifiable {
        case all, keyboard, gestures
        var id: String { rawValue }
        var title: String { self == .all ? "Все" : (self == .keyboard ? "Клавиатура" : "Жесты") }
    }

    private var visibleRules: [Rule] {
        model.configuration.rules.filter { rule in
            let typeMatches: Bool
            switch (filter, rule.trigger) {
            case (.all, _), (.keyboard, .keyboard), (.gestures, .gesture): typeMatches = true
            default: typeMatches = false
            }
            let text = [rule.name, rule.trigger.displayName, rule.action.displayName, rule.scope.displayName].joined(separator: " ")
            return typeMatches && (query.isEmpty || text.localizedCaseInsensitiveContains(query))
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if visibleRules.isEmpty {
                EmptyStateView(
                    title: query.isEmpty ? "Правил пока нет" : "Ничего не найдено",
                    icon: query.isEmpty ? "keyboard.badge.plus" : "magnifyingglass",
                    description: query.isEmpty ? "Добавьте хоткей или жест и назначьте действие." : "Измените поиск или фильтр."
                )
            } else {
                List {
                    ForEach(visibleRules) { rule in
                        RuleRow(rule: rule) { enabled in model.setRuleEnabled(id: rule.id, enabled: enabled) }
                            .contentShape(Rectangle())
                            .onTapGesture { editor = EditableRule(rule: rule) }
                            .contextMenu {
                                Button("Изменить") { editor = EditableRule(rule: rule) }
                                Button("Дублировать") {
                                    var copy = rule
                                    copy.id = UUID(); copy.name = copy.name.isEmpty ? "Копия" : "\(copy.name) — копия"
                                    model.addRule(copy)
                                }
                                Divider()
                                Button("Удалить", role: .destructive) { model.deleteRule(id: rule.id) }
                            }
                    }
                }
                .listStyle(.inset)
            }
        }
        .sheet(item: $editor) { item in
            RuleEditorView(rule: item.rule, allRules: model.configuration.rules) { model.updateRule($0) }
                .environmentObject(model)
        }
    }

    private var header: some View {
        VStack(spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Правила").font(.title2.bold())
                    Text("Триггер → действие → область применения").foregroundStyle(.secondary)
                }
                Spacer()
                Menu {
                    Button("Сочетание клавиш", systemImage: "keyboard") { createKeyboardRule() }
                    Button("Тап тремя пальцами", systemImage: "hand.tap") { createGestureRule(.threeFingerTap) }
                    Button("Тап четырьмя пальцами", systemImage: "hand.tap.fill") { createGestureRule(.fourFingerTap) }
                } label: { Label("Добавить", systemImage: "plus") }
                .menuStyle(.borderlessButton)
                .fixedSize()
            }
            HStack {
                TextField("Поиск правил", text: $query).textFieldStyle(.roundedBorder)
                Picker("Фильтр", selection: $filter) {
                    ForEach(TriggerFilter.allCases) { Text($0.title).tag($0) }
                }
                .pickerStyle(.segmented).frame(width: 280)
            }
        }
        .padding(20)
    }

    private func createKeyboardRule() {
        let rule = Rule(trigger: .keyboard(KeyCombination(virtualKey: 49, modifiers: [.command], keyLabel: "Space")), action: .openURL("https://"))
        model.addRule(rule); editor = EditableRule(rule: rule)
    }

    private func createGestureRule(_ gesture: GestureKind) {
        let rule = Rule(trigger: .gesture(gesture), action: .pressKeys(KeyCombination(virtualKey: 17, modifiers: [.command], keyLabel: "T")))
        model.addRule(rule); editor = EditableRule(rule: rule)
    }
}

private struct EmptyStateView: View {
    let title: String
    let icon: String
    let description: String
    var body: some View {
        VStack(spacing: 10) {
            Spacer()
            Image(systemName: icon).font(.system(size: 38)).foregroundStyle(.secondary)
            Text(title).font(.title3.bold())
            Text(description).foregroundStyle(.secondary)
            Spacer()
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct RuleRow: View {
    let rule: Rule
    let onEnabledChange: (Bool) -> Void
    @EnvironmentObject private var model: AppModel

    private var issues: [RuleValidationIssue] {
        RuleValidator.validate(rule, among: model.configuration.rules, strictModifiers: model.configuration.preferences.strictModifierMatching)
    }

    var body: some View {
        HStack(spacing: 14) {
            Toggle("", isOn: Binding(get: { rule.isEnabled }, set: onEnabledChange)).labelsHidden()
            Image(systemName: triggerIcon).font(.title3).frame(width: 25).foregroundStyle(rule.isEnabled ? Color.accentColor : .secondary)
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(rule.trigger.displayName).font(.headline)
                    Image(systemName: "arrow.right").foregroundStyle(.tertiary)
                    Text(rule.action.displayName).lineLimit(1)
                }
                HStack(spacing: 6) {
                    Label(rule.scope.displayName, systemImage: rule.scope == .global ? "globe" : "app")
                    if !issues.isEmpty { Label("Конфликт", systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange) }
                }
                .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
        }
        .padding(.vertical, 7)
        .opacity(rule.isEnabled ? 1 : 0.55)
    }

    private var triggerIcon: String {
        if case .keyboard = rule.trigger { return "keyboard" }
        return "hand.tap"
    }
}

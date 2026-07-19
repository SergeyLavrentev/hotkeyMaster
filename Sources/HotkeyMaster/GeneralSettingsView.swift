import SwiftUI

struct GeneralSettingsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Основные").font(.title2.bold())
                    Text("Состояние приложения и системные разрешения.").foregroundStyle(.secondary)
                }
                GroupBox("Доступ") {
                    HStack(spacing: 14) {
                        Image(systemName: model.accessibilityGranted ? "checkmark.shield.fill" : "exclamationmark.shield.fill")
                            .font(.system(size: 30)).foregroundStyle(model.accessibilityGranted ? .green : .orange)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(model.accessibilityGranted ? "Accessibility разрешён" : "Требуется Accessibility").font(.headline)
                            Text("Нужен для глобальных хоткеев и отправки клавиш.").foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button("Проверить") { model.refreshPermissions() }
                        Button("Открыть настройки") {
                            PermissionManager.requestAccessibility()
                            PermissionManager.openAccessibilitySettings()
                        }
                    }.padding(10)
                }
                GroupBox("Запуск") {
                    VStack(alignment: .leading, spacing: 9) {
                        Toggle("Запускать HotkeyMaster при входе", isOn: Binding(
                            get: { LoginItemManager.isEnabled },
                            set: { model.setLaunchAtLogin($0) }
                        ))
                        Text("Используется системный Login Item через ServiceManagement.").font(.caption).foregroundStyle(.secondary)
                        if model.configuration.preferences.launchAtLogin != LoginItemManager.isEnabled {
                            Button("Открыть системные Login Items") { LoginItemManager.openSettings() }
                        }
                    }.padding(10)
                }
                GroupBox("Клавиатура") {
                    VStack(alignment: .leading, spacing: 9) {
                        Toggle("Точное совпадение модификаторов", isOn: Binding(
                            get: { model.configuration.preferences.strictModifierMatching },
                            set: { model.configuration.preferences.strictModifierMatching = $0; model.preferencesChanged() }
                        ))
                        Text("Если включено, ⌘K не сработает при дополнительно зажатом Option или Shift.").font(.caption).foregroundStyle(.secondary)
                    }.padding(10)
                }
                if !model.migrationWarnings.isEmpty {
                    GroupBox("Импорт legacy") {
                        VStack(alignment: .leading, spacing: 5) {
                            ForEach(model.migrationWarnings, id: \.self) { Label($0, systemImage: "exclamationmark.triangle") }
                        }.padding(10)
                    }
                }
                GroupBox("О приложении") {
                    HStack {
                        Image(systemName: "keyboard.badge.ellipsis").font(.system(size: 32)).foregroundStyle(.tint)
                        VStack(alignment: .leading) { Text("HotkeyMaster").font(.headline); Text("Native Swift edition · configuration schema 2").foregroundStyle(.secondary) }
                        Spacer()
                    }.padding(10)
                }
            }.padding(22)
        }
    }
}

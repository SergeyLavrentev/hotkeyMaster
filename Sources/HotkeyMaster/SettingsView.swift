import SwiftUI

enum SettingsSection: String, CaseIterable, Identifiable {
    case rules, trackpad, general, diagnostics
    var id: String { rawValue }
    var title: String {
        switch self {
        case .rules: return "Правила"
        case .trackpad: return "Трекпад"
        case .general: return "Основные"
        case .diagnostics: return "Диагностика"
        }
    }
    var icon: String {
        switch self {
        case .rules: return "list.bullet.rectangle"
        case .trackpad: return "hand.tap"
        case .general: return "gearshape"
        case .diagnostics: return "waveform.path.ecg"
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var selection: SettingsSection?

    init() {
        let requested = ProcessInfo.processInfo.environment["HOTKEYMASTER_SETTINGS_SECTION"]
        _selection = State(initialValue: requested.flatMap(SettingsSection.init(rawValue:)) ?? .rules)
    }

    var body: some View {
        NavigationSplitView {
            List(SettingsSection.allCases, selection: $selection) { section in
                Label(section.title, systemImage: section.icon).tag(section)
            }
            .navigationSplitViewColumnWidth(min: 170, ideal: 190)
        } detail: {
            Group {
                switch selection ?? .rules {
                case .rules: RulesView()
                case .trackpad: TrackpadSettingsView()
                case .general: GeneralSettingsView()
                case .diagnostics: DiagnosticsView()
                }
            }
            .frame(minWidth: 690, minHeight: 510)
        }
        .frame(width: 940, height: 610)
        .onAppear { model.refreshPermissions() }
    }
}

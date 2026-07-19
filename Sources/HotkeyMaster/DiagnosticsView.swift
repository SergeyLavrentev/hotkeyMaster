import HotkeyMasterKit
import SwiftUI

struct DiagnosticsView: View {
    @EnvironmentObject private var diagnostics: DiagnosticLog

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Диагностика").font(.title2.bold())
                    Text("Распознавание жестов, запуск правил и системные ошибки.").foregroundStyle(.secondary)
                }
                Spacer()
                Button("Очистить") { diagnostics.clear() }
                Button("Экспортировать…") { export() }
            }.padding(20)
            Divider()
            if diagnostics.events.isEmpty {
                VStack(spacing: 10) {
                    Spacer()
                    Image(systemName: "waveform.path.ecg").font(.system(size: 38)).foregroundStyle(.secondary)
                    Text("Событий пока нет").font(.title3.bold())
                    Text("Выполните хоткей или жест.").foregroundStyle(.secondary)
                    Spacer()
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(diagnostics.events) { event in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: icon(event.level)).foregroundStyle(color(event.level)).frame(width: 18)
                        VStack(alignment: .leading, spacing: 3) {
                            HStack { Text(event.category).font(.headline); Text(event.timestamp, style: .time).font(.caption).foregroundStyle(.secondary) }
                            Text(event.message)
                            if let details = event.details { Text(details).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
                        }
                    }.padding(.vertical, 4)
                }.listStyle(.inset)
            }
        }
    }

    private func export() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "HotkeyMaster-diagnostics.json"
        panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do { try diagnostics.export(to: url) }
        catch { diagnostics.append(.error, category: "Диагностика", message: "Экспорт не удался", details: error.localizedDescription) }
    }

    private func icon(_ level: DiagnosticLevel) -> String {
        switch level { case .info: return "info.circle"; case .success: return "checkmark.circle.fill"; case .warning: return "exclamationmark.triangle.fill"; case .error: return "xmark.octagon.fill" }
    }
    private func color(_ level: DiagnosticLevel) -> Color {
        switch level { case .info: return .blue; case .success: return .green; case .warning: return .orange; case .error: return .red }
    }
}

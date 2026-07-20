import HotkeyMasterKit
import SwiftUI

struct TrackpadSettingsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var showAdvanced = false

    private var preferences: Binding<Preferences> {
        Binding(get: { model.configuration.preferences }, set: { model.configuration.preferences = $0; model.preferencesChanged() })
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Трекпад").font(.title2.bold())
                    Text("Проверьте жест в реальном времени и выберите устойчивый профиль.").foregroundStyle(.secondary)
                }
                calibrationCard
                GroupBox("Профиль распознавания") {
                    VStack(alignment: .leading, spacing: 14) {
                        Picker("Профиль", selection: preferences.gesturePreset) {
                            ForEach(GesturePreset.allCases.filter { $0 != .custom }) { Text($0.displayName).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        Text(presetDescription).font(.callout).foregroundStyle(.secondary)
                        DisclosureGroup("Дополнительные параметры", isExpanded: $showAdvanced) {
                            AdvancedThresholdsView(thresholds: preferences.customGestureThresholds)
                                .padding(.top, 10)
                            Button("Использовать эти параметры") {
                                model.configuration.preferences.gesturePreset = .custom
                                model.preferencesChanged()
                            }
                        }
                    }
                    .padding(8)
                }
                GroupBox("Экспериментальные жесты") {
                    VStack(alignment: .leading, spacing: 7) {
                        Toggle("Разрешить тапы одним и двумя пальцами", isOn: preferences.experimentalGestures)
                        Text("Они могут конфликтовать с обычным кликом и системным secondary click. По умолчанию отключены.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(8)
                }
            }
            .padding(22)
        }
        .onAppear { model.setGestureCalibrationActive(true) }
        .onDisappear { model.setGestureCalibrationActive(false) }
    }

    private var calibrationCard: some View {
        GroupBox {
            HStack(spacing: 22) {
                TouchVisualizer(contacts: model.lastFrame.contacts)
                    .frame(width: 270, height: 170)
                VStack(alignment: .leading, spacing: 10) {
                    Label("Проверка жеста", systemImage: "hand.tap").font(.headline)
                    Text("Выполните короткий тап тремя или четырьмя пальцами.").foregroundStyle(.secondary)
                    if let result = model.lastClassification {
                        classificationView(result)
                    } else {
                        Label("Ожидаю жест…", systemImage: "circle.dotted").foregroundStyle(.secondary)
                    }
                    Spacer()
                    HStack(spacing: 14) {
                        calibrationResult("3 пальца", count: model.calibrationThreeFingerSuccesses)
                        calibrationResult("4 пальца", count: model.calibrationFourFingerSuccesses)
                        Spacer()
                        Button("Начать заново") { model.resetGestureCalibration() }
                            .buttonStyle(.link)
                    }
                    Text("Целевых попыток: \(model.calibrationAttempts) · успешно: \(model.calibrationSuccesses)")
                        .font(.caption).monospacedDigit().foregroundStyle(.secondary)
                    Text("Точек касания сейчас: \(model.lastFrame.contacts.filter { $0.state != .lifted }.count)")
                        .font(.caption).monospacedDigit().foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(10)
        }
    }

    private func calibrationResult(_ title: String, count: Int) -> some View {
        Label("\(title): \(count)", systemImage: count > 0 ? "checkmark.circle.fill" : "circle")
            .font(.callout.weight(.medium))
            .foregroundStyle(count > 0 ? .green : .secondary)
            .monospacedDigit()
    }

    @ViewBuilder private func classificationView(_ result: GestureClassification) -> some View {
        switch result {
        case .recognized(let gesture, let metrics):
            Label(gesture.displayName, systemImage: "checkmark.circle.fill").foregroundStyle(.green).font(.headline)
            Text(String(format: "%.0f мс · движение %.3f · центр %.3f", metrics.duration * 1000, metrics.maximumFingerMovement, metrics.centroidMovement))
                .font(.caption).monospacedDigit().foregroundStyle(.secondary)
        case .rejected(let reason, _):
            Label("Жест отклонён", systemImage: "xmark.circle.fill").foregroundStyle(.orange).font(.headline)
            Text(reason.message).font(.callout).foregroundStyle(.secondary)
        }
    }

    private var presetDescription: String {
        switch model.configuration.preferences.gesturePreset {
        case .precise: return "Минимум ложных срабатываний. Требует короткого и аккуратного тапа."
        case .balanced: return "Рекомендуемый баланс между надёжностью и удобством."
        case .responsive: return "Легче распознаёт быстрые и неточные тапы, но требует проверки системных свайпов."
        case .custom: return "Используются ваши расширенные параметры."
        }
    }
}

private struct AdvancedThresholdsView: View {
    @Binding var thresholds: GestureThresholds
    var body: some View {
        VStack(spacing: 9) {
            threshold("Максимальная длительность", value: $thresholds.maximumDuration, range: 0.15...0.5, format: { String(format: "%.0f мс", $0 * 1000) })
            threshold("Движение пальца", value: $thresholds.maximumFingerMovement, range: 0.02...0.18, format: { String(format: "%.3f", $0) })
            threshold("Движение центра", value: $thresholds.maximumCentroidMovement, range: 0.01...0.10, format: { String(format: "%.3f", $0) })
            threshold("Одновременность", value: $thresholds.maximumStartSpread, range: 0.03...0.2, format: { String(format: "%.0f мс", $0 * 1000) })
            threshold("Повтор", value: $thresholds.repeatDelay, range: 0.1...1, format: { String(format: "%.0f мс", $0 * 1000) })
        }
    }

    private func threshold(_ name: String, value: Binding<Double>, range: ClosedRange<Double>, format: @escaping (Double) -> String) -> some View {
        HStack {
            Text(name).frame(width: 190, alignment: .leading)
            Slider(value: value, in: range)
            Text(format(value.wrappedValue)).monospacedDigit().frame(width: 65, alignment: .trailing)
        }
    }
}

private struct TouchVisualizer: View {
    let contacts: [TouchContact]
    var body: some View {
        Canvas { context, size in
            let rect = CGRect(origin: .zero, size: size).insetBy(dx: 4, dy: 4)
            context.fill(Path(roundedRect: rect, cornerRadius: 18), with: .color(.secondary.opacity(0.08)))
            context.stroke(Path(roundedRect: rect, cornerRadius: 18), with: .color(.secondary.opacity(0.28)), lineWidth: 1)
            for contact in contacts where contact.state != .lifted {
                let point = CGPoint(x: rect.minX + contact.x * rect.width, y: rect.maxY - contact.y * rect.height)
                let circle = CGRect(x: point.x - 15, y: point.y - 15, width: 30, height: 30)
                context.fill(Path(ellipseIn: circle), with: .color(.accentColor.opacity(0.7)))
                context.stroke(Path(ellipseIn: circle), with: .color(.accentColor), lineWidth: 2)
            }
        }
    }
}

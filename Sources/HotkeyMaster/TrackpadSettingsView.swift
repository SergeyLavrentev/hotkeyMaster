import HotkeyMasterKit
import SwiftUI

struct TrackpadSettingsView: View {
    @EnvironmentObject private var model: AppModel

    private var preferences: Binding<Preferences> {
        Binding(get: { model.configuration.preferences }, set: { model.configuration.preferences = $0; model.preferencesChanged() })
    }

    private var gesturePreset: Binding<GesturePreset> {
        Binding(
            get: { model.configuration.preferences.gesturePreset },
            set: { model.setGesturePreset($0) }
        )
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
                        Picker("Профиль", selection: gesturePreset) {
                            ForEach(GesturePreset.allCases.filter { $0 != .custom }) { Text($0.displayName).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        Text(presetDescription).font(.callout).foregroundStyle(.secondary)
                        Label("Параметры длительности и движения подбираются автоматически.", systemImage: "slider.horizontal.3")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Label("Системные свайпы между рабочими столами блокируются независимо от профиля.", systemImage: "rectangle.3.group")
                            .font(.caption)
                            .foregroundStyle(.secondary)
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
        case .recognized(let gesture, _):
            Label(gesture.displayName, systemImage: "checkmark.circle.fill").foregroundStyle(.green).font(.headline)
            Text("Профиль уверенно распознал этот тап.")
                .font(.callout).foregroundStyle(.secondary)
        case .rejected(let reason, _):
            Label("Жест отклонён", systemImage: "xmark.circle.fill").foregroundStyle(.orange).font(.headline)
            Text(calibrationExplanation(for: reason)).font(.callout).foregroundStyle(.secondary)
        }
    }

    private func calibrationExplanation(for reason: GestureRejectionReason) -> String {
        switch reason {
        case .tooLong:
            return "Касание получилось слишком долгим для выбранного профиля."
        case .fingersStartedTooFarApart:
            return "Пальцы коснулись трекпада не одновременно."
        case .coherentSwipe:
            return "Распознан свайп. Действие для тапа не будет выполнено."
        case .fingerMovedTooFar, .centroidMovedTooFar:
            return "Это больше похоже на движение. Попробуйте короткий тап или более отзывчивый профиль."
        case .unsupportedFingerCount(let count):
            return "Обнаружено пальцев: \(count). Используйте три или четыре."
        case .experimentalGestureDisabled:
            return "Этот жест отключён в экспериментальных настройках."
        case .incompleteFrameSequence:
            return "Трекпад передал неполные данные. Попробуйте ещё раз."
        }
    }

    private var presetDescription: String {
        switch model.configuration.preferences.gesturePreset {
        case .precise: return "Строже отличает тап от движения и реже срабатывает случайно."
        case .balanced: return "Рекомендуемый режим: уверенно распознаёт обычный тап без лишних срабатываний."
        case .responsive: return "Прощает более долгий и неточный тап, поэтому реагирует легче."
        case .custom: return "Старый пользовательский профиль. Выберите один из готовых режимов."
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

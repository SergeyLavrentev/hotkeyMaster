import AppKit
import SwiftUI

@MainActor
final class OnboardingWindowController: NSObject, NSWindowDelegate {
    static let shared = OnboardingWindowController()

    private var window: NSWindow?
    private var dismissedThisLaunch = false

    func showIfNeeded() {
        AppModel.shared.refreshPermissions()
        let forcePreview = ProcessInfo.processInfo.environment["HOTKEYMASTER_FORCE_ONBOARDING"] == "1"
        guard (forcePreview || !AppModel.shared.accessibilityGranted), !dismissedThisLaunch else { return }
        show()
    }

    func permissionStatusDidChange() {
        guard window != nil else { return }
        AppModel.shared.refreshPermissions()
    }

    func dismissForNow() {
        dismissedThisLaunch = true
        window?.close()
    }

    func finish() {
        window?.close()
    }

    private func show() {
        if let window {
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            return
        }

        let root = OnboardingView()
            .environmentObject(AppModel.shared)
        let controller = NSHostingController(rootView: root)
        let window = NSWindow(contentViewController: controller)
        window.title = "Добро пожаловать в HotkeyMaster"
        window.styleMask = [.titled, .closable]
        window.setContentSize(NSSize(width: 620, height: 520))
        window.center()
        window.isReleasedWhenClosed = false
        window.delegate = self
        self.window = window
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) {
        window = nil
    }
}

private struct OnboardingView: View {
    @EnvironmentObject private var model: AppModel
    private let permissionPoller = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            header
            steps
            permissionStatus
            Spacer(minLength: 0)
            actions
        }
        .padding(32)
        .frame(width: 620, height: 520)
        .onAppear { model.refreshPermissions() }
        .onReceive(permissionPoller) { _ in model.refreshPermissions() }
    }

    private var header: some View {
        HStack(spacing: 18) {
            Image(systemName: "keyboard.badge.ellipsis")
                .font(.system(size: 42, weight: .semibold))
                .foregroundStyle(.tint)
                .frame(width: 68, height: 68)
                .background(.tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
            VStack(alignment: .leading, spacing: 5) {
                Text("Настроим HotkeyMaster")
                    .font(.system(size: 26, weight: .bold))
                Text("Один системный доступ — и глобальные хоткеи готовы.")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var steps: some View {
        VStack(alignment: .leading, spacing: 15) {
            OnboardingStep(number: 1, title: "Разрешите Accessibility", detail: "macOS использует его для перехвата глобальных сочетаний и отправки назначенных клавиш.")
            OnboardingStep(number: 2, title: "Вернитесь в HotkeyMaster", detail: "Статус обновится автоматически — перезапуск не нужен.")
            OnboardingStep(number: 3, title: "Создайте первое правило", detail: "Выберите хоткей или жест и действие для него.")
        }
    }

    private var permissionStatus: some View {
        HStack(spacing: 12) {
            Image(systemName: model.accessibilityGranted ? "checkmark.shield.fill" : "exclamationmark.shield.fill")
                .font(.title2)
                .foregroundStyle(model.accessibilityGranted ? .green : .orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(model.accessibilityGranted ? "Accessibility разрешён" : "Accessibility пока не разрешён")
                    .font(.headline)
                Text(model.accessibilityGranted ? "Глобальные хоткеи активны." : "Нажмите кнопку ниже — откроется нужный раздел macOS.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(14)
        .background(.quaternary.opacity(0.45), in: RoundedRectangle(cornerRadius: 12))
    }

    private var actions: some View {
        HStack {
            if !model.accessibilityGranted {
                Button("Позже") { OnboardingWindowController.shared.dismissForNow() }
            }
            Spacer()
            if model.accessibilityGranted {
                Button("Открыть настройки") {
                    OnboardingWindowController.shared.finish()
                    SettingsWindowController.shared.show()
                }
                .keyboardShortcut(.defaultAction)
            } else {
                Button("Разрешить Accessibility") {
                    PermissionManager.requestAccessibility()
                    PermissionManager.openAccessibilitySettings()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
    }
}

private struct OnboardingStep: View {
    let number: Int
    let title: String
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(number)")
                .font(.caption.bold())
                .foregroundStyle(.white)
                .frame(width: 24, height: 24)
                .background(.tint, in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Text(detail).font(.subheadline).foregroundStyle(.secondary)
            }
        }
    }
}

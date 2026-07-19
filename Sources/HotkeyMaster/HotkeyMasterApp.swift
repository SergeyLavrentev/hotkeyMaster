import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var observers: [NSObjectProtocol] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        AppModel.shared.start()
        let environment = ProcessInfo.processInfo.environment
        if environment["HOTKEYMASTER_SHOW_SETTINGS"] == "1" {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                SettingsWindowController.shared.show()
            }
        } else if environment["HOTKEYMASTER_SKIP_ONBOARDING"] != "1" {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                OnboardingWindowController.shared.showIfNeeded()
            }
        }
        let center = NSWorkspace.shared.notificationCenter
        observers.append(center.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in AppModel.shared.stop() }
        })
        observers.append(center.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { AppModel.shared.start() }
        })
    }

    func applicationWillTerminate(_ notification: Notification) {
        AppModel.shared.stop()
        observers.forEach(NSWorkspace.shared.notificationCenter.removeObserver)
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        AppModel.shared.refreshPermissions()
        OnboardingWindowController.shared.permissionStatusDidChange()
    }
}

@main
struct HotkeyMasterApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var model = AppModel.shared

    var body: some Scene {
        MenuBarExtra("HotkeyMaster", systemImage: "keyboard.badge.ellipsis") {
            StatusMenuView()
                .environmentObject(model)
                .environmentObject(model.diagnostics)
        }
        Settings {
            SettingsView()
                .environmentObject(model)
                .environmentObject(model.diagnostics)
        }
    }
}

private struct StatusMenuView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if #available(macOS 14.0, *) {
                ModernSettingsButton()
            } else {
                Button("Настройки…") {
                    SettingsWindowController.shared.show()
                }
                .keyboardShortcut(",")
            }
        }
        Divider()
        Label(model.accessibilityGranted ? "Хоткеи доступны" : "Нужен Accessibility", systemImage: model.accessibilityGranted ? "checkmark.circle" : "exclamationmark.triangle")
        Label("Правил: \(model.configuration.rules.filter(\.isEnabled).count)", systemImage: "list.bullet.rectangle")
        Divider()
        Button("Завершить HotkeyMaster") { NSApp.terminate(nil) }
            .keyboardShortcut("q")
    }
}

@MainActor
final class SettingsWindowController: NSObject, NSWindowDelegate {
    static let shared = SettingsWindowController()
    private var window: NSWindow?

    func show() {
        if let window {
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            return
        }
        let root = SettingsView()
            .environmentObject(AppModel.shared)
            .environmentObject(AppModel.shared.diagnostics)
        let controller = NSHostingController(rootView: root)
        let window = NSWindow(contentViewController: controller)
        window.title = "HotkeyMaster — Настройки"
        window.styleMask = [.titled, .closable, .miniaturizable, .resizable]
        window.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        window.setContentSize(NSSize(width: 940, height: 610))
        window.center()
        window.delegate = self
        self.window = window
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) { window = nil }
}

@available(macOS 14.0, *)
private struct ModernSettingsButton: View {
    @Environment(\.openSettings) private var openSettings
    var body: some View {
        Button("Настройки…") {
            NSApp.activate(ignoringOtherApps: true)
            openSettings()
        }
        .keyboardShortcut(",")
    }
}

import Foundation
import HotkeyMasterKit

final class DiagnosticLog: ObservableObject {
    @Published private(set) var events: [DiagnosticEvent] = []
    private let maximumEvents = 500

    func append(_ level: DiagnosticLevel, category: String, message: String, details: String? = nil) {
        let event = DiagnosticEvent(level: level, category: category, message: message, details: details)
        if Thread.isMainThread {
            insert(event)
        } else {
            DispatchQueue.main.async { [weak self] in self?.insert(event) }
        }
    }

    func clear() { events.removeAll() }

    func export(to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        try encoder.encode(events).write(to: url, options: .atomic)
    }

    private func insert(_ event: DiagnosticEvent) {
        events.insert(event, at: 0)
        if events.count > maximumEvents { events.removeLast(events.count - maximumEvents) }
    }
}

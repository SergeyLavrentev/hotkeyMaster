import CMultitouchBridge
import Foundation
import HotkeyMasterKit

final class TrackpadMonitor {
    typealias ClassificationHandler = (GestureClassification) -> Void
    typealias FrameHandler = (TouchFrame) -> Void

    private var bridge: OpaquePointer?
    private let classifier: GestureClassifier
    private let lock = NSLock()
    private let diagnostics: DiagnosticLog
    private let classificationHandler: ClassificationHandler
    private let frameHandler: FrameHandler
    private var frameUpdatesEnabled = false
    private var lastFrameUpdateTimestamp: TimeInterval?
    private static let frameUpdateInterval: TimeInterval = 1.0 / 20.0

    init(
        diagnostics: DiagnosticLog,
        thresholds: GestureThresholds,
        experimentalGestures: Bool,
        classificationHandler: @escaping ClassificationHandler,
        frameHandler: @escaping FrameHandler
    ) {
        self.diagnostics = diagnostics
        self.classifier = GestureClassifier(thresholds: thresholds, experimentalGesturesEnabled: experimentalGestures)
        self.classificationHandler = classificationHandler
        self.frameHandler = frameHandler
    }

    func setFrameUpdatesEnabled(_ enabled: Bool) {
        lock.lock(); defer { lock.unlock() }
        frameUpdatesEnabled = enabled
        lastFrameUpdateTimestamp = nil
    }

    func update(thresholds: GestureThresholds, experimentalGestures: Bool) {
        lock.lock(); defer { lock.unlock() }
        classifier.thresholds = thresholds
        classifier.experimentalGesturesEnabled = experimentalGestures
        classifier.cancel()
        diagnostics.append(.info, category: "Трекпад", message: "Параметры распознавания применены")
    }

    func start() {
        guard bridge == nil else { return }
        var error: UnsafeMutablePointer<CChar>?
        let context = Unmanaged.passUnretained(self).toOpaque()
        guard let created = HMTrackpadCreate(trackpadFrameCallback, context, &error) else {
            report(error: error, fallback: "Не удалось инициализировать трекпад")
            return
        }
        bridge = created
        guard HMTrackpadStart(created, &error) else {
            report(error: error, fallback: "Не удалось запустить трекпад")
            HMTrackpadDestroy(created)
            bridge = nil
            return
        }
        diagnostics.append(.success, category: "Трекпад", message: "Трекпад подключён")
    }

    func stop() {
        guard let bridge else { return }
        HMTrackpadStop(bridge)
        HMTrackpadDestroy(bridge)
        self.bridge = nil
    }

    fileprivate func receive(contacts: UnsafePointer<HMTouchContact>?, count: Int32, timestamp: Double) {
        let values: [TouchContact]
        if let contacts, count > 0 {
            values = (0..<Int(count)).compactMap { index in
                let value = contacts[index]
                guard let state = TouchState(rawValue: Int(value.state)) else { return nil }
                return TouchContact(id: value.identifier, state: state, x: value.x, y: value.y)
            }
        } else {
            values = []
        }
        let frame = TouchFrame(timestamp: timestamp, contacts: values)
        lock.lock()
        let result = classifier.process(frame)
        let isSequenceEnding = values.isEmpty || values.allSatisfy { $0.state == .lifted }
        let shouldPublishFrame = frameUpdatesEnabled && (
            isSequenceEnding ||
            lastFrameUpdateTimestamp.map { timestamp - $0 >= Self.frameUpdateInterval } ?? true
        )
        if shouldPublishFrame {
            lastFrameUpdateTimestamp = timestamp
        }
        lock.unlock()
        if shouldPublishFrame { frameHandler(frame) }
        if let result { classificationHandler(result) }
    }

    private func report(error: UnsafeMutablePointer<CChar>?, fallback: String) {
        let details = error.map { String(cString: $0) }
        if let error { HMTrackpadFreeError(error) }
        diagnostics.append(.error, category: "Трекпад", message: fallback, details: details)
    }
}

private let trackpadFrameCallback: HMTouchFrameCallback = { contacts, count, timestamp, context in
    guard let context else { return }
    let monitor = Unmanaged<TrackpadMonitor>.fromOpaque(context).takeUnretainedValue()
    monitor.receive(contacts: contacts, count: count, timestamp: timestamp)
}

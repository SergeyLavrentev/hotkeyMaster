import Foundation

public enum TouchState: Int, Codable, Sendable {
    case touching = 1
    case moving = 2
    case lifted = 4
}

public struct TouchContact: Codable, Equatable, Sendable, Identifiable {
    public var id: Int32
    public var state: TouchState
    public var x: Double
    public var y: Double

    public init(id: Int32, state: TouchState, x: Double, y: Double) {
        self.id = id
        self.state = state
        self.x = x
        self.y = y
    }
}

public struct TouchFrame: Codable, Equatable, Sendable {
    public var timestamp: TimeInterval
    public var contacts: [TouchContact]

    public init(timestamp: TimeInterval, contacts: [TouchContact]) {
        self.timestamp = timestamp
        self.contacts = contacts
    }
}

public enum GestureRejectionReason: Equatable, Sendable {
    case unsupportedFingerCount(Int)
    case experimentalGestureDisabled(Int)
    case tooLong(actual: TimeInterval, maximum: TimeInterval)
    case fingersStartedTooFarApart(actual: TimeInterval, maximum: TimeInterval)
    case fingerMovedTooFar(actual: Double, maximum: Double)
    case centroidMovedTooFar(actual: Double, maximum: Double)
    case coherentSwipe(distance: Double, coherence: Double)
    case incompleteFrameSequence

    public var message: String {
        switch self {
        case .unsupportedFingerCount(let count): return "Неподдерживаемое количество пальцев: \(count)."
        case .experimentalGestureDisabled(let count): return "Жест \(count) пальцами отключён как экспериментальный."
        case .tooLong(let actual, let maximum): return String(format: "Слишком долго: %.0f мс, допустимо %.0f мс.", actual * 1000, maximum * 1000)
        case .fingersStartedTooFarApart(let actual, let maximum): return String(format: "Пальцы поставлены не одновременно: %.0f мс, допустимо %.0f мс.", actual * 1000, maximum * 1000)
        case .fingerMovedTooFar(let actual, let maximum): return String(format: "Палец сместился на %.3f, допустимо %.3f.", actual, maximum)
        case .centroidMovedTooFar(let actual, let maximum): return String(format: "Общее движение %.3f, допустимо %.3f — похоже на свайп.", actual, maximum)
        case .coherentSwipe(let distance, let coherence): return String(format: "Согласованное движение %.3f (%.0f%%) — распознано как свайп.", distance, coherence * 100)
        case .incompleteFrameSequence: return "Недостаточно данных о касании."
        }
    }
}

public struct GestureMetrics: Equatable, Sendable {
    public var fingerCount: Int
    public var duration: TimeInterval
    public var maximumFingerMovement: Double
    public var centroidMovement: Double
    public var coherentMovement: Double
    public var directionalCoherence: Double
    public var startSpread: TimeInterval
}

public enum GestureClassification: Equatable, Sendable {
    case recognized(GestureKind, GestureMetrics)
    case rejected(GestureRejectionReason, GestureMetrics?)
}

public final class GestureClassifier {
    private static let coherentSwipeMinimumMovement = 0.035
    private static let coherentSwipeMinimumCoherence = 0.72

    private struct FingerTrace {
        var startTimestamp: TimeInterval
        var startX: Double
        var startY: Double
        var lastX: Double
        var lastY: Double
        var maximumMovement: Double
    }

    public var thresholds: GestureThresholds
    public var experimentalGesturesEnabled: Bool
    private var traces: [Int32: FingerTrace] = [:]
    private var activeIDs: Set<Int32> = []
    private var gestureStart: TimeInterval?
    private var lastTimestamp: TimeInterval?
    private var centroidStart: (x: Double, y: Double)?
    private var maximumCentroidMovement = 0.0
    private var peakActiveFingerCount = 0
    private var sawActiveFrame = false

    public init(thresholds: GestureThresholds = .balanced, experimentalGesturesEnabled: Bool = false) {
        self.thresholds = thresholds
        self.experimentalGesturesEnabled = experimentalGesturesEnabled
    }

    public func process(_ frame: TouchFrame) -> GestureClassification? {
        lastTimestamp = frame.timestamp
        let activeContacts = frame.contacts.filter { $0.state != .lifted }
        let reportedIDs = Set(frame.contacts.map(\.id))
        let disappearedIDs = activeIDs.subtracting(reportedIDs)
        activeIDs.subtract(disappearedIDs)

        for contact in frame.contacts {
            if contact.state == .lifted {
                if var trace = traces[contact.id] {
                    updateTrace(&trace, contact: contact)
                    traces[contact.id] = trace
                }
                activeIDs.remove(contact.id)
                continue
            }
            sawActiveFrame = true
            if gestureStart == nil { gestureStart = frame.timestamp }
            if var trace = traces[contact.id] {
                updateTrace(&trace, contact: contact)
                traces[contact.id] = trace
            } else {
                traces[contact.id] = FingerTrace(
                    startTimestamp: frame.timestamp,
                    startX: contact.x, startY: contact.y,
                    lastX: contact.x, lastY: contact.y,
                    maximumMovement: 0
                )
            }
            activeIDs.insert(contact.id)
        }

        if !activeContacts.isEmpty {
            let centroid = (
                x: activeContacts.map(\.x).reduce(0, +) / Double(activeContacts.count),
                y: activeContacts.map(\.y).reduce(0, +) / Double(activeContacts.count)
            )
            if activeContacts.count > peakActiveFingerCount {
                // Fingers normally arrive and leave a few milliseconds apart. Measure
                // movement only while the full, peak-sized contact group is present;
                // otherwise adding/removing an outer finger looks like a large swipe.
                peakActiveFingerCount = activeContacts.count
                centroidStart = activeContacts.count >= 3 || experimentalGesturesEnabled ? centroid : nil
                maximumCentroidMovement = 0
            } else if activeContacts.count == peakActiveFingerCount, let start = centroidStart {
                maximumCentroidMovement = max(maximumCentroidMovement, hypot(centroid.x - start.x, centroid.y - start.y))
            }
        }

        let allLifted = sawActiveFrame && activeIDs.isEmpty && frame.contacts.allSatisfy { $0.state == .lifted }
        let disappeared = sawActiveFrame && activeIDs.isEmpty && frame.contacts.isEmpty
        guard allLifted || disappeared else { return nil }
        return finish(at: frame.timestamp)
    }

    public func cancel() {
        reset()
    }

    private func updateTrace(_ trace: inout FingerTrace, contact: TouchContact) {
        trace.lastX = contact.x
        trace.lastY = contact.y
        trace.maximumMovement = max(trace.maximumMovement, hypot(contact.x - trace.startX, contact.y - trace.startY))
    }

    private func finish(at timestamp: TimeInterval) -> GestureClassification {
        defer { reset() }
        guard let start = gestureStart, !traces.isEmpty else {
            return .rejected(.incompleteFrameSequence, nil)
        }
        let count = traces.count
        let duration = max(0, timestamp - start)
        let movements = traces.values.map(\.maximumMovement)
        let displacements = traces.values.map { (dx: $0.lastX - $0.startX, dy: $0.lastY - $0.startY) }
        let meanDX = displacements.map(\.dx).reduce(0, +) / Double(displacements.count)
        let meanDY = displacements.map(\.dy).reduce(0, +) / Double(displacements.count)
        let coherentMovement = hypot(meanDX, meanDY)
        let meanIndividualMovement = displacements.map { hypot($0.dx, $0.dy) }.reduce(0, +) / Double(displacements.count)
        let directionalCoherence = meanIndividualMovement > 0.000_001
            ? min(1, coherentMovement / meanIndividualMovement)
            : 0
        let starts = traces.values.map(\.startTimestamp)
        let spread = (starts.max() ?? start) - (starts.min() ?? start)
        let metrics = GestureMetrics(
            fingerCount: count,
            duration: duration,
            maximumFingerMovement: movements.max() ?? 0,
            centroidMovement: maximumCentroidMovement,
            coherentMovement: coherentMovement,
            directionalCoherence: directionalCoherence,
            startSpread: spread
        )
        guard let kind = GestureKind(rawValue: count) else {
            return .rejected(.unsupportedFingerCount(count), metrics)
        }
        if kind.isExperimental && !experimentalGesturesEnabled {
            return .rejected(.experimentalGestureDisabled(count), metrics)
        }
        if duration > thresholds.maximumDuration {
            return .rejected(.tooLong(actual: duration, maximum: thresholds.maximumDuration), metrics)
        }
        if spread > thresholds.maximumStartSpread {
            return .rejected(.fingersStartedTooFarApart(actual: spread, maximum: thresholds.maximumStartSpread), metrics)
        }
        if coherentMovement >= Self.coherentSwipeMinimumMovement,
           directionalCoherence >= Self.coherentSwipeMinimumCoherence {
            return .rejected(.coherentSwipe(distance: coherentMovement, coherence: directionalCoherence), metrics)
        }
        if metrics.maximumFingerMovement > thresholds.maximumFingerMovement {
            return .rejected(.fingerMovedTooFar(actual: metrics.maximumFingerMovement, maximum: thresholds.maximumFingerMovement), metrics)
        }
        if metrics.centroidMovement > thresholds.maximumCentroidMovement {
            return .rejected(.centroidMovedTooFar(actual: metrics.centroidMovement, maximum: thresholds.maximumCentroidMovement), metrics)
        }
        return .recognized(kind, metrics)
    }

    private func reset() {
        traces.removeAll(keepingCapacity: true)
        activeIDs.removeAll(keepingCapacity: true)
        gestureStart = nil
        lastTimestamp = nil
        centroidStart = nil
        maximumCentroidMovement = 0
        peakActiveFingerCount = 0
        sawActiveFrame = false
    }
}

import Foundation

public struct GestureReplay: Codable, Sendable {
    public var name: String
    public var frames: [TouchFrame]

    public init(name: String, frames: [TouchFrame]) {
        self.name = name
        self.frames = frames
    }

    public func classify(using classifier: GestureClassifier) -> GestureClassification? {
        classifier.cancel()
        var result: GestureClassification?
        for frame in frames {
            if let classification = classifier.process(frame) { result = classification }
        }
        return result
    }

    public func write(to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(self).write(to: url, options: .atomic)
    }
}

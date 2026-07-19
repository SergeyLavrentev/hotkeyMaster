import Foundation

public final class ConfigurationStore {
    public let configurationURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(configurationURL: URL? = nil) {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("HotkeyMaster", isDirectory: true)
        self.configurationURL = configurationURL ?? base.appendingPathComponent("configuration-v2.json")
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        self.encoder.dateEncodingStrategy = .iso8601
        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601
    }

    public var exists: Bool { FileManager.default.fileExists(atPath: configurationURL.path) }

    public func load() throws -> Configuration {
        let data = try Data(contentsOf: configurationURL)
        return try decoder.decode(Configuration.self, from: data)
    }

    public func save(_ configuration: Configuration) throws {
        let directory = configurationURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try encoder.encode(configuration)
        let temporary = directory.appendingPathComponent(".\(configurationURL.lastPathComponent).\(UUID().uuidString).tmp")
        try data.write(to: temporary, options: .atomic)
        if FileManager.default.fileExists(atPath: configurationURL.path) {
            _ = try FileManager.default.replaceItemAt(configurationURL, withItemAt: temporary)
        } else {
            try FileManager.default.moveItem(at: temporary, to: configurationURL)
        }
    }
}

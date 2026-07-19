import AppKit
import HotkeyMasterKit

enum ApplicationCatalog {
    static func applications() -> [ApplicationReference] {
        var roots: [URL] = []
        let domains: FileManager.SearchPathDomainMask = [.localDomainMask, .systemDomainMask, .userDomainMask]
        roots.append(contentsOf: FileManager.default.urls(for: .applicationDirectory, in: domains))
        roots.append(contentsOf: FileManager.default.urls(for: .allApplicationsDirectory, in: domains))

        var result: [String: ApplicationReference] = [:]
        let keys: Set<URLResourceKey> = [.isApplicationKey, .isDirectoryKey, .nameKey]
        for root in Set(roots) {
            guard let enumerator = FileManager.default.enumerator(
                at: root,
                includingPropertiesForKeys: Array(keys),
                options: [.skipsHiddenFiles, .skipsPackageDescendants]
            ) else { continue }
            for case let url as URL in enumerator {
                guard url.pathExtension == "app", let bundle = Bundle(url: url),
                      let identifier = bundle.bundleIdentifier else { continue }
                let displayName = (bundle.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String)
                    ?? (bundle.object(forInfoDictionaryKey: "CFBundleName") as? String)
                    ?? url.deletingPathExtension().lastPathComponent
                result[identifier] = ApplicationReference(
                    bundleIdentifier: identifier,
                    displayName: displayName,
                    path: url.path
                )
            }
        }
        return result.values.sorted {
            $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending
        }
    }

    static func resolveLegacyName(_ name: String) -> ApplicationReference? {
        applications().first {
            $0.displayName.caseInsensitiveCompare(name.replacingOccurrences(of: ".app", with: "")) == .orderedSame
        }
    }
}

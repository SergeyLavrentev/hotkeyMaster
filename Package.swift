// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "HotkeyMaster",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "HotkeyMasterKit", targets: ["HotkeyMasterKit"]),
        .executable(name: "HotkeyMaster", targets: ["HotkeyMaster"]),
        .executable(name: "HotkeyMasterChecks", targets: ["HotkeyMasterChecks"]),
    ],
    targets: [
        .target(
            name: "CMultitouchBridge",
            publicHeadersPath: "include",
            linkerSettings: [
                .linkedFramework("CoreFoundation"),
            ]
        ),
        .target(name: "HotkeyMasterKit"),
        .executableTarget(
            name: "HotkeyMaster",
            dependencies: ["HotkeyMasterKit", "CMultitouchBridge"],
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("ApplicationServices"),
                .linkedFramework("CoreGraphics"),
                .linkedFramework("ServiceManagement"),
                .linkedLibrary("dl"),
            ]
        ),
        .executableTarget(
            name: "HotkeyMasterChecks",
            dependencies: ["HotkeyMasterKit"],
            path: "Tests/HotkeyMasterKitTests"
        ),
    ],
    swiftLanguageModes: [.v5]
)

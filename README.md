# HotkeyMaster 2

HotkeyMaster is a native macOS menu-bar application for global keyboard
shortcuts and three-/four-finger trackpad taps. Version 2 is a greenfield Swift
rewrite; the Python/PyQt implementation in the repository is legacy code and is
not used by the native application.

## Features

- Native SwiftUI settings and `MenuBarExtra` UI.
- Typed rules: trigger → action → exact application scope.
- Global keyboard monitoring through a CoreGraphics event tap.
- Three- and four-finger taps with deterministic swipe/long-press filtering.
- Live touch visualization and a clear rejection reason for every tested gesture.
- Precise, Balanced, Responsive, and Custom gesture profiles applied immediately.
- Actions for URLs, applications, commands, key presses, and display brightness.
- Exact bundle-identifier application matching.
- Conflict validation before a rule can be saved.
- Native Accessibility onboarding and `SMAppService` login item management.
- Diagnostics screen with JSON export.
- Automatic one-time import of the legacy Python configuration.

## Requirements

- macOS 13 or later.
- Swift 6 toolchain or Xcode with the macOS SDK.
- Accessibility permission for global keyboard shortcuts and generated keys.

Raw trackpad contact data uses Apple's private
`MultitouchSupport.framework`. Keyboard rules keep working if that framework or
a physical trackpad is unavailable.

## Build and test

```sh
make swift-build       # debug executable
make check             # deterministic native checks
make app               # release dist/HotkeyMaster.app, ad-hoc signed
make install           # install the native app into /Applications
```

The local Command Line Tools image does not ship `XCTest`/`Testing`, so the
same deterministic checks are packaged as the `HotkeyMasterChecks` executable.
A successful run prints `HotkeyMasterChecks: 10 checks passed`.

## Configuration migration

The native configuration is stored at:

```text
~/Library/Application Support/HotkeyMaster/configuration-v2.json
```

On first launch, HotkeyMaster looks for the legacy `hotkeys.json` and
`settings.json`, converts string actions and lowercase modifiers to typed data,
resolves application names to bundle identifiers when possible, and writes the
new configuration atomically. Legacy files are not deleted.

## Architecture

- `Sources/HotkeyMasterKit` — models, persistence, legacy importer, conflicts,
  gesture classifier, replay format.
- `Sources/HotkeyMaster` — SwiftUI UI and macOS services.
- `Sources/CMultitouchBridge` — isolated private-framework C bridge.
- `Tests/HotkeyMasterKitTests` — executable integration/replay checks.
- `docs/swift-architecture.md` — boundaries and runtime invariants.

## Legacy Python edition

The root Python files are retained temporarily for behavioral reference and
rollback only. They are intentionally not modified by the Swift rewrite. To run
their existing checks while the migration is being validated:

```sh
make legacy-test
```

## License

MIT

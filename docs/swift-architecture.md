# HotkeyMaster 2 architecture

HotkeyMaster 2 is a native macOS 13+ menu-bar application. The Python/PyQt
implementation remains in the repository only as a legacy reference and as an
input format for first-launch migration.

## Boundaries

- `HotkeyMasterKit` contains typed rules, configuration, migration, conflict
  detection, gesture frames, replay support, and the pure gesture classifier.
- `HotkeyMaster` contains SwiftUI screens and macOS integrations: AppKit,
  CoreGraphics event taps, Accessibility, ServiceManagement, and actions.
- `CMultitouchBridge` is the only module that calls the private
  `MultitouchSupport.framework`. It converts framework-specific frames to a
  small stable C structure consumed by Swift.
- The bridge ignores hover/range phases and maps the physical touch lifecycle
  (`MakeTouch`/`Touching`/`BreakTouch`, raw states 3/4/5) to the stable Swift
  lifecycle (`touching`/`moving`/`lifted`, values 1/2/4).
- `HotkeyMasterChecks` runs deterministic classifier, persistence, migration,
  and conflict checks without a physical trackpad.

## Runtime flow

1. `AppModel` imports legacy `hotkeys.json` when `configuration-v2.json` does
   not exist, then persists schema version 2 atomically.
2. Keyboard and trackpad monitors publish typed triggers.
3. `AppModel` filters disabled rules and compares application scopes by exact
   bundle identifier.
4. `ActionExecutor` runs the typed action and records the outcome in the
   in-memory diagnostic log.
5. Gesture preference changes update the live classifier immediately.

## Permission onboarding

- Startup never opens System Settings without an explicit click from the user.
- If Accessibility is missing, a native onboarding window explains the reason,
  offers a non-blocking “Later” path, and polls the trusted-process status while
  it is visible.
- Returning to the app refreshes permissions and retries creation of the global
  keyboard event tap. The onboarding completes only after the current process
  reports that Accessibility is trusted.
- Dismissing onboarding suppresses it only for the current run; a later launch
  asks again until the required permission is actually granted.
- Onboarding and settings move to the active Space and are full-screen
  auxiliaries, so opening them from the menu bar cannot strand the window on a
  different desktop behind a full-screen application.

## Gesture invariants

- Three- and four-finger taps are supported by default.
- One- and two-finger taps require the explicit experimental preference.
- Duration, per-finger displacement, centroid displacement, and finger start
  spread are evaluated independently and produce a user-facing rejection
  reason.
- Classifier state is reset after every completed or cancelled sequence.
- The frame callback never runs actions directly; UI/rule evaluation is sent
  to the main actor.
- Every connected multitouch device is registered; the classifier receives a
  single normalized stream regardless of built-in or external trackpad.
- Opening Trackpad settings enters calibration mode: classifications and
  metrics are recorded, but matching production actions are suppressed.
- Calibration ignores ordinary one- and two-finger contacts, reports three-
  and four-finger successes separately, and therefore cannot claim readiness
  after repeatedly recognizing only one of the two primary gestures.

`MultitouchSupport.framework` is private and can change between macOS releases.
Keeping it behind the C bridge makes failure visible and allows the rest of the
application to continue providing keyboard automation.

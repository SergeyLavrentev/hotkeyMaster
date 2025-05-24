# HotkeyMaster

> **Note:** HotkeyMaster is an open source, free, and simpler alternative to BetterTouchTool for macOS. It provides essential hotkey and gesture automation features without the complexity or cost.

HotkeyMaster is a native macOS application for creating global hotkeys and trackpad gestures to control apps and automate actions. It features a modern tray UI, flexible configuration, and deep system integration.

## Features
- Global hotkeys for any application
- Trackpad gesture support (1–4 fingers, tap and swipe)
- Actions: launch apps, open URLs, emulate keypresses, run scripts
- Flexible configuration via graphical interface (PyQt5)
- Tray icon in the system menu bar (no Dock or Cmd+Tab presence)
- Automatic hotkey re-registration on settings change
- Autostart on login (via LaunchAgents)
- Phantom tap filtering for reliable gesture detection
- Settings stored in `hotkeys.json`
- Native support for both Intel and Apple Silicon (macOS 12+)

<img width="891" alt="image" src="https://github.com/user-attachments/assets/c6ecbec3-0f54-42c7-8e70-a78ef9acebf7" />


## Architecture
- **main.py** — Application entry point, hotkey/gesture logic, tray integration
- **ui.py** — PyQt5-based settings window for hotkeys and gestures
- **trackpad_engine.py** — Multitouch gesture detection (via private MultitouchSupport.framework)
- **hotkey_engine.py** — Global hotkey registration and action execution (Quartz, CoreDisplay)
- **autolaunch.py** — Autostart management via LaunchAgents (plist in ~/Library/LaunchAgents)
- **hotkeys.json** — User hotkey/gesture configuration
- **icons/** — App icons and Info.plist for macOS bundle
- **coredisplay_helper.c** — Helper for display brightness control (optional)

## Requirements
- macOS 12 or later (Ventura/Sonoma recommended)
- Python 3.12
- Xcode Command Line Tools (for PyInstaller build)

## Quick Start
1. Create a virtual environment and install dependencies:
   ```sh
   make venv312
   source venv312/bin/activate
   ```
2. Build the application:
   ```sh
   make build
   ```
3. Install to /Applications:
   ```sh
   make install
   ```

## Running
- After installation, launch HotkeyMaster from Spotlight or the Applications folder.
- The icon will appear in the system menu bar (tray).

## Accessibility Permissions
Global hotkeys require "Accessibility" permissions:
1. Open: System Settings → Privacy & Security → Accessibility
2. Add HotkeyMaster and check the box

## Development
- To run in development mode:
  ```sh
  source venv312/bin/activate
  make run
  ```
- All hotkey/gesture changes are saved in `hotkeys.json`

## Extending & Customization
- Add new gestures (e.g., 5-finger tap) by editing `trackpad_engine.py`
- Actions can be customized: app launch, URL open, key emulation, scripts
- Tray menu and UI can be extended via `ui.py`

## Troubleshooting & Limitations
- Requires Accessibility permission for global hotkeys
- Trackpad gestures use private APIs (may break in future macOS versions)
- App is hidden from Dock and Cmd+Tab by default
- For autostart, LaunchAgents plist is used (see `autolaunch.py`)
- Known issue: Some system gestures may interfere with custom gestures (phantom tap filter reduces false positives)

## Dependencies
- PyQt5, pyobjc, pynput, pystray, pillow

## License
MIT

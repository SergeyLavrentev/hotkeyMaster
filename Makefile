.PHONY: build clean run rebuild install codesign full-install full-rebuild venv312

APP_NAME=HotkeyMaster
DISPLAY_NAME="HotkeyMaster"
SPEC_FILE=hotkeymaster.spec
DIST_DIR=dist
BUILD_DIR=build
APP_BUNDLE=$(DIST_DIR)/$(APP_NAME).app
INSTALL_PATH=/Applications/
PYTHON=python3.12

SIGN_IDENTITY="Developer ID Application: Rocker (TEAMID)"  # Замени на свой identity

build:
	clang -F /System/Library/PrivateFrameworks \
    -I /System/Library/PrivateFrameworks/CoreDisplay.framework/Headers \
    -framework CoreDisplay -framework CoreGraphics \
    coredisplay_helper.c -o coredisplay_helper  # Компилируем C-хелпер
	$(PYTHON) -m PyInstaller --clean --noconfirm $(SPEC_FILE)

clean:
	rm -rf $(BUILD_DIR)/
	rm -rf $(DIST_DIR)/
	rm -fr __pycache__/

run:
	$(PYTHON) main.py

rebuild: clean build

install:
	@echo "Installing $(DISPLAY_NAME) to /Applications/"
	cp -a $(APP_BUNDLE) $(INSTALL_PATH)
	codesign --force --deep --sign - $(INSTALL_PATH)/$(APP_NAME).app
	@echo "Installed $(DISPLAY_NAME) to /Applications/"

codesign:
	@echo "Signing $(DISPLAY_NAME) with identity: $(SIGN_IDENTITY)"
	codesign --deep --force --verify --verbose --sign "$(SIGN_IDENTITY)" "$(INSTALL_PATH)/$(APP_NAME).app"
	@echo "Successfully signed $(DISPLAY_NAME)."

full-install: build install codesign
	@echo "Built, installed, and signed $(DISPLAY_NAME) successfully."

full-rebuild: clean build install codesign
	@echo "Cleaned, built, installed, and signed $(DISPLAY_NAME) successfully."

venv312:
	python3.12 -m venv venv312
	. venv312/bin/activate && pip install -r requirements.txt && pip install pyinstaller

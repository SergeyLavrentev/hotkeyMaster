.PHONY: build swift-build check app run install clean test legacy-test legacy-run legacy-build venv312

APP_NAME=HotkeyMaster
APP_BUNDLE=dist/$(APP_NAME).app
INSTALL_PATH=/Applications
PYTHON=python3.12

build: app

swift-build:
	swift build --product HotkeyMaster

check:
	swift run HotkeyMasterChecks

app: check
	bash scripts/build-app.sh

run: swift-build
	.build/debug/HotkeyMaster

install: app
	bash scripts/install-app.sh

clean:
	swift package clean
	rm -rf dist/

test: check legacy-test

legacy-build:
	clang coredisplay_helper.c -framework CoreGraphics -o coredisplay_helper
	$(PYTHON) -m PyInstaller --clean --noconfirm hotkeymaster.spec

legacy-run:
	HOTKEYMASTER_DEV=1 $(PYTHON) main.py

legacy-test:
	@if [ -x venv312/bin/python ]; then \
		venv312/bin/python -m pytest -q; \
	else \
		$(PYTHON) -m pytest -q; \
	fi

venv312:
	python3.12 -m venv venv312
	venv312/bin/pip install -r requirements.txt pyinstaller pytest

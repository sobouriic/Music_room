.DEFAULT_GOAL := help

API_URL ?= http://localhost:8001
IOS_PORT ?= 8082
ANDROID_PORT ?= 8083
PHONE_PORT ?= 8084
PHONE_IP ?= $(shell ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $$1}')
PHONE_API_URL ?= http://$(PHONE_IP):8001
ANDROID_SERIAL ?=
ANDROID_AVD ?=
ANDROID_HOME ?= $(if $(ANDROID_SDK_ROOT),$(ANDROID_SDK_ROOT),$(if $(filter Darwin,$(shell uname -s)),$(HOME)/Library/Android/sdk,$(HOME)/Android/Sdk))
ANDROID_ADB ?= $(ANDROID_HOME)/platform-tools/adb
# Gradle cannot run with Java 27. macOS builds use the installed JDK 21 by default.
ANDROID_JAVA_HOME ?= $(shell /usr/libexec/java_home -v 21 2>/dev/null)
EXPO_ENV = NODE_OPTIONS=--dns-result-order=ipv4first EXPO_PUBLIC_API_URL="$(API_URL)" EXPO_PUBLIC_USE_MOCK=false REACT_NATIVE_PACKAGER_HOSTNAME=127.0.0.1
ANDROID_ENV = ANDROID_HOME="$(ANDROID_HOME)" ANDROID_SDK_ROOT="$(ANDROID_HOME)"
LOAD_USERS ?= 5 10 20
LOAD_SECONDS ?= 30

define check_metro_port
	@python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(1); busy=s.connect_ex(("127.0.0.1",int(sys.argv[1])))==0; s.close(); sys.exit("Metro port "+sys.argv[1]+" is busy. Stop its terminal with Ctrl+C before starting this command." if busy else 0)' "$(1)"
endef

.PHONY: help install backend web frontend dev mobile phone phone-dev ios android ios-dev android-dev ios-go android-go ios-build android-build android-forward typecheck test-backend test-mobile test-load stop clean fclean

help:
	@echo "Music Room — choose one command per terminal"
	@echo ""
	@echo "First setup:       make install"
	@echo "Terminal 1:        make backend       API + email worker"
	@echo "Terminal 2:        make android       development app; starts a saved emulator if needed"
	@echo "                   make ios           installed iOS development app (fast)"
	@echo "                   make web           browser frontend only"
	@echo "                   make phone         Expo Go QR code for a real phone on the same Wi-Fi"
	@echo "                   make phone-dev     QR code for a development app already installed on a phone"
	@echo ""
	@echo "Build/install once, or after native dependencies/config change (slower):"
	@echo "                   make android-build (requires JDK 21 + Android SDK)"
	@echo "                   make ios-build     (requires Xcode + CocoaPods)"
	@echo "Expo Go:           make android-go / make ios-go (Google login unavailable)"
	@echo "Browser + API:     make dev           explicitly starts both"
	@echo "Tests:             make test-backend / test-mobile / typecheck / test-load"
	@echo "Stop / cleanup:    make stop / make clean (keeps DB) / make fclean (DELETES DB)"
	@echo "Do not run a start command and a build command for the same platform together."

# Setup only; does not start Metro.
install:
	cd backend && sh start.sh --setup-only
	cd mobile && npm ci

# API / web. Use separate terminals, or explicitly opt into `make dev`.
backend:
	cd backend && CORS_ORIGINS='["http://localhost:8081","http://127.0.0.1:8081"]' sh start.sh --skip-install --host 0.0.0.0 --port 8001
web frontend:
	cd mobile && EXPO_PUBLIC_API_URL="$(API_URL)" EXPO_PUBLIC_USE_MOCK=false npm run web -- --port 8081
dev:
	python3 scripts/dev.py
mobile:
	@echo "Choose make phone, make android, make ios, or make web. See make help."

# Real phones need a LAN address: localhost would refer to the phone itself.
phone phone-dev:
	@test -n "$(PHONE_IP)" || { echo "Wi-Fi IP not found. Run make $@ PHONE_IP=YOUR_COMPUTER_LAN_IP"; exit 1; }
	$(call check_metro_port,$(PHONE_PORT))
	@echo "Connect phone and computer to the same Wi-Fi, then scan the QR code."
	@echo "Phone API address: $(PHONE_API_URL) — use this in Connection settings if an older address is saved."
	@echo "Keep make backend running in another terminal. Google login needs phone-dev and an installed development app."
	cd mobile && NODE_OPTIONS=--dns-result-order=ipv4first EXPO_PUBLIC_API_URL="$(PHONE_API_URL)" EXPO_PUBLIC_USE_MOCK=false REACT_NATIVE_PACKAGER_HOSTNAME="$(PHONE_IP)" npx expo start $(if $(filter phone-dev,$@),--dev-client,--go) --lan --port $(PHONE_PORT)

# Daily native development: reuse the installed Music Room app; no compilation.
ios ios-dev:
	$(call check_metro_port,$(IOS_PORT))
	cd mobile && $(EXPO_ENV) npx expo start --dev-client --localhost --port $(IOS_PORT) --ios
android android-dev: android-forward
	$(call check_metro_port,$(ANDROID_PORT))
	cd mobile && $(ANDROID_ENV) $(EXPO_ENV) npx expo start --dev-client --localhost --port $(ANDROID_PORT) --android
android-forward:
	python3 scripts/android.py --adb "$(ANDROID_ADB)" --metro-port $(ANDROID_PORT) $(if $(ANDROID_SERIAL),--serial "$(ANDROID_SERIAL)") $(if $(ANDROID_AVD),--avd "$(ANDROID_AVD)")

# Expo Go is only for screens that do not need the app's custom callback/native modules.
ios-go:
	$(call check_metro_port,$(IOS_PORT))
	cd mobile && $(EXPO_ENV) npx expo start --go --localhost --port $(IOS_PORT) --ios
android-go: android-forward
	$(call check_metro_port,$(ANDROID_PORT))
	cd mobile && $(ANDROID_ENV) $(EXPO_ENV) npx expo start --go --localhost --port $(ANDROID_PORT) --android

# Rebuild when native libraries/configuration change. Cached native builds are reused.
ios-build:
	$(call check_metro_port,$(IOS_PORT))
	cd mobile && npx expo prebuild --platform ios --no-install
	cd mobile && $(EXPO_ENV) npx expo run:ios --port $(IOS_PORT)
android-build: android-forward
	$(call check_metro_port,$(ANDROID_PORT))
	@test -d "$(ANDROID_HOME)/platforms" || { echo "Android SDK not found. Set ANDROID_HOME to its SDK directory."; exit 1; }
	@test -n "$(ANDROID_JAVA_HOME)" || { echo "Install JDK 21, or set ANDROID_JAVA_HOME to its directory."; exit 1; }
	@"$(ANDROID_JAVA_HOME)/bin/java" -version
	cd mobile && $(ANDROID_ENV) npx expo prebuild --platform android --no-install
	cd mobile && JAVA_HOME="$(ANDROID_JAVA_HOME)" PATH="$(ANDROID_JAVA_HOME)/bin:$$PATH" $(ANDROID_ENV) $(EXPO_ENV) npx expo run:android --port $(ANDROID_PORT)

# Local checks. Load tests and backend tests share an isolated DB: run separately.
typecheck:
	cd mobile && npm run typecheck
test-backend:
	cd backend && sh test-api.sh
test-mobile:
	cd mobile && npm test -- --runInBand --testPathIgnorePatterns=integration.test
test-load:
	@test -x backend/.venv/bin/python || { echo "Run make install first."; exit 1; }
	cd backend && docker compose --profile test up -d --wait test-db
	mkdir -p backend/.test-results
	cd backend && .venv/bin/python -m scripts.capacity_test --users $(LOAD_USERS) --seconds $(LOAD_SECONDS) --output .test-results/load-test.json

# Stop and remove generated caches, retaining installed dependencies and credentials.
stop:
	python3 backend/scripts/stop_dev.py
clean: stop
	find backend -type d \( -name '.venv*' -o -name .git \) -prune -o -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	rm -rf mobile/.expo .ruff_cache backend/.test-results

# Destructive reset: only use when you intend to delete all local database data.
fclean: clean
	cd backend && docker compose --profile app --profile test down --volumes --remove-orphans
	rm -rf backend/.dev-mail
	@echo "Full cleanup complete. Database data deleted; source, dependencies, and .env preserved."

# Use the same commands from mobile/ or the repository root.
.DEFAULT_GOAL := help
.PHONY: help install start phone phone-dev android ios android-dev ios-dev android-build ios-build android-go ios-go web backend typecheck test
help install phone phone-dev android ios android-dev ios-dev android-build ios-build android-go ios-go web backend typecheck:
	$(MAKE) -C .. $@
start:
	$(MAKE) -C .. help
test:
	$(MAKE) -C .. test-mobile

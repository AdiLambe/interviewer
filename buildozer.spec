[app]
title = Mock Interview
package.name = mockinterview
package.domain = org.interviewer
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,atlas,txt
source.exclude_dirs = .github,bin,.buildozer,__pycache__
version = 2.0.1
requirements = python3,kivy==2.3.0,plyer
orientation = portrait
fullscreen = 0

# Modern Android target
android.api = 35
android.minapi = 24
android.ndk = 27b
android.ndk_api = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = False
android.debug_artifact = apk

# Updated python-for-android branch
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1

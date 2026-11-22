[app]
title = Mock Interview
package.name = mockinterview
package.domain = org.interviewer
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,txt
source.exclude_dirs = .github,bin,.buildozer
version = 2.0.0
requirements = python3,kivy==2.3.0,plyer,pyjnius
orientation = portrait
fullscreen = 0
android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1

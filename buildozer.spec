
[app]
title = Mock Interview
package.name = mockinterview
package.domain = org.interviewer
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,txt
source.exclude_dirs = .github,bin,.buildozer
version = 2.0.0

requirements = python3==3.12.9,hostpython3==3.12.9,kivy==2.3.0,plyer,pyjnius

orientation = portrait
fullscreen = 0

android.api = 35
android.minapi = 26
android.ndk = 25b
android.ndk_api = 26
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True
android.debug_artifact = apk

p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1


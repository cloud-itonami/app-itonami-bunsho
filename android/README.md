# Android package

This repository owns the Tauri package `network.itonami.bunsho` and its releases.
Build the browser candidate from this app with its existing
[Amu browser build](../scripts/build-browser.py). Use a checkout of
[app-itonami-office](https://github.com/network-awai/app-itonami-office) with
the exact revision in [office-host.rev](office-host.rev). The helper reads
that revision from Git, so changes in the helper's working tree have no effect.

```sh
scripts/prepare-android.sh OFFICE_REPO BROWSER_BUILD KOTOBA_REPO .agent-output/android
cd .agent-output/android
npm ci
npm run tauri -- android init --ci
mkdir -p src-tauri/gen/android/app/src/main/java/network/awai/office
cp OfficeBackupPlugin.kt src-tauri/gen/android/app/src/main/java/network/awai/office/
mkdir -p src-tauri/icons
cp src-tauri/gen/android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png src-tauri/icons/icon.png
npm run tauri -- android build --apk --target aarch64 --debug
```

Use `x86_64` for x86 Android. Keep the application ID and release signing
identity when upgrading an installed app. Awai OS integration consumes the
signed APK via its app distribution process.

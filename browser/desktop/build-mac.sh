#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then echo 'Usage: build-mac.sh payload.zip output-directory' >&2; exit 2; fi
payload="$1"
output="$2"
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$output"
app="$output/Kronos WebGPU.app"
if [ -e "$app" ]; then echo 'App output exists; preserve it and use a fresh output directory' >&2; exit 1; fi
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/content"
clang -fobjc-arc -fblocks -arch arm64 -arch x86_64 -mmacosx-version-min=12.0 -framework Cocoa "$source_dir/MacLauncher.m" -o "$app/Contents/MacOS/Kronos"
temporary="$output/payload-extracted"
mkdir "$temporary"
unzip -q "$payload" -d "$temporary"
# The controlled payload contains exactly one root directory.
count=$(find "$temporary" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
if [ "$count" != 1 ]; then echo 'Expected one payload root directory' >&2; exit 1; fi
payload_root=$(find "$temporary" -mindepth 1 -maxdepth 1 -type d)
cp -R "$payload_root/." "$app/Contents/Resources/content/"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>Kronos</string>
<key>CFBundleIdentifier</key><string>org.jawlesseel.kronos.webgpu</string>
<key>CFBundleName</key><string>Kronos WebGPU</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$app"
codesign --verify --deep --strict "$app"
image="$output/dmg-content"
mkdir "$image"
cp -R "$app" "$image/"
ln -s /Applications "$image/Applications"
cat > "$image/READ-ME.txt" <<'HELP'
Drag Kronos WebGPU.app into Applications, then open the installed app.
For a per-user install, copy it into your user's Applications folder instead.
Keep its launcher window open while using Chrome; closing it stops the server.
No Python, terminal, Xcode, or administrator service is needed at runtime.
Chrome must be installed and support WebGPU. Models are included.
This prototype is ad-hoc signed, not Apple-notarized. Gatekeeper may require
your manual approval. No security protections are changed by this package.
TradingView extension: click Show Chrome extension folder in the launcher,
then select that extension folder in Chrome's Load unpacked dialog.
HELP
hdiutil create -quiet -volname 'Kronos WebGPU' -srcfolder "$image" -format UDZO "$output/Kronos-WebGPU-Mac-1.0.0.dmg"
echo 'Created universal arm64/x86_64 app and DMG. Gatekeeper notarization is not provided.'

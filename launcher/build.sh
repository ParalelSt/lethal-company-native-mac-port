#!/bin/zsh
# Maintainer: compile the native launcher. Needs Xcode Command Line Tools.
#   build.sh           dev build: "Lethal Company Port.app" in the repo, runs the kit next to it
#   build.sh --embed   download build: dist/Lethal Company Port.app with the kit (files in launcher/kit-files) in
#                      Contents/Resources/kit, so the app works from anywhere
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/.." && pwd)"; DEV="$ROOT/Lethal Company Port.app"
EMBED=0; [ "$1" = "--embed" ] && EMBED=1
APP="$DEV"; [ $EMBED = 1 ] && APP="$ROOT/dist/Lethal Company Port.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
xcrun swiftc -O -target arm64-apple-macos12.0 -framework AppKit -framework WebKit -o "$APP/Contents/MacOS/Lethal Company Port" "$HERE/Launcher.swift"
if [ $EMBED = 1 ]; then
  VER="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/lcport/__init__.py")"
  cp "$DEV/Contents/Info.plist" "$APP/Contents/Info.plist"
  plutil -replace CFBundleShortVersionString -string "$VER" "$APP/Contents/Info.plist"
  mkdir -p "$APP/Contents/Resources/kit"
  (cd "$ROOT" && rsync -a --delete --exclude __pycache__ --exclude .DS_Store $(cat "$HERE/kit-files") "$APP/Contents/Resources/kit/")
fi
codesign --force --deep --sign - "$APP"
echo "built $APP"

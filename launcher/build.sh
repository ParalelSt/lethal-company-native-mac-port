#!/bin/zsh
# Maintainer: compile the native launcher into "Lethal Company Port.app". Needs Xcode Command Line Tools.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; APP="$HERE/../Lethal Company Port.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
xcrun swiftc -O -target arm64-apple-macos12.0 -framework AppKit -o "$APP/Contents/MacOS/Lethal Company Port" "$HERE/Launcher.swift"
codesign --force --deep --sign - "$APP"
echo "built $APP"

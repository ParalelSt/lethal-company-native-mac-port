#!/bin/zsh
# Maintainer: build the launcher downloads and publish a GitHub release whose notes are the matching CHANGELOG section.
# Usage: scripts/release.sh [--dry-run] 0.2.0   (requires: gh auth login; clean git tree; CHANGELOG has a "## [0.2.0]" section)
# Assets: Lethal-Company-Port-<ver>.dmg (app + Applications link), -app.zip (the app; also what self-update downloads),
# -source.zip (git archive of the tree).
# --dry-run (first argument): build all three only; no release commit, tag, push or gh release, and an uncommitted tree
# is allowed (the source zip is then HEAD). Prints the assets and their sizes.
set -e
DRY=0; [ "$1" = "--dry-run" ] && { DRY=1; shift; }
VER="${1:?version, e.g. 0.2.0}"; KIT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KIT"
if [ -n "$(git status --porcelain)" ]; then
  [ $DRY = 1 ] && echo "note: uncommitted changes (dry run); the source zip is HEAD" || { echo "commit or stash changes first"; exit 1; }
fi
grep -q "^## \[$VER\]" CHANGELOG.md || { echo "CHANGELOG.md has no section for $VER"; exit 1; }
sed -i '' "s/^__version__ = .*/__version__ = \"$VER\"/" lcport/__init__.py
bash launcher/build.sh --embed || { echo "launcher build failed"; exit 1; }
[ $DRY = 1 ] || { git add lcport/__init__.py; git commit -qm "Release $VER" || true; }
NOTES="$(awk -v v="$VER" '/^## \[/{p=($0 ~ "\\["v"\\]")} p' CHANGELOG.md | tail -n +2)"
NAME="Lethal-Company-Port-$VER"; TMP="$(mktemp -d)"; APP="$KIT/dist/Lethal Company Port.app"
DMG="$TMP/$NAME.dmg"; APPZIP="$TMP/$NAME-app.zip"; SRCZIP="$TMP/$NAME-source.zip"
mkdir -p "$TMP/dmg" "$TMP/$NAME"
ditto "$APP" "$TMP/dmg/Lethal Company Port.app"; ln -s /Applications "$TMP/dmg/Applications"
hdiutil create -quiet -volname "Lethal Company Port" -srcfolder "$TMP/dmg" -ov -format UDZO "$DMG"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$APPZIP"
git archive HEAD -- . ":(exclude)Lethal Company Port.app" | tar -x -C "$TMP/$NAME"  # no app: a 0.1.0 updater would replace its app with the bare folder
(cd "$TMP" && zip -qry "$SRCZIP" "$NAME")
if [ $DRY = 1 ]; then
  ls -lh "$DMG" "$APPZIP" "$SRCZIP" | awk '{print $5, $NF}'
  echo "dry run, assets in $TMP"; exit 0
fi
git tag -f "v$VER"; git push -q origin HEAD --tags
# source zip first, app zip last and on its own: 0.1.0 launchers update from the first .zip asset and expect the source layout
gh release create "v$VER" "$SRCZIP" "$DMG" --title "Launcher $VER" --notes "$NOTES"
gh release upload "v$VER" "$APPZIP"
echo "released v$VER"

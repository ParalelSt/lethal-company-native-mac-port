#!/bin/zsh
# Maintainer: package the kit and publish a GitHub release whose notes are the matching CHANGELOG section.
# Usage: scripts/release.sh [--dry-run] 0.2.0   (requires: gh auth login; clean git tree; CHANGELOG has a "## [0.2.0]" section)
# --dry-run (first argument): build and zip only; no release commit, tag, push or gh release. Prints the zip path and its listing.
set -e
DRY=0; [ "$1" = "--dry-run" ] && { DRY=1; shift; }
VER="${1:?version, e.g. 0.2.0}"; KIT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KIT"
[ -z "$(git status --porcelain)" ] || { echo "commit or stash changes first"; exit 1; }
grep -q "^## \[$VER\]" CHANGELOG.md || { echo "CHANGELOG.md has no section for $VER"; exit 1; }
sed -i '' "s/^__version__ = .*/__version__ = \"$VER\"/" lcport/__init__.py
bash launcher/build.sh || { echo "launcher build failed"; exit 1; }
[ $DRY = 1 ] || { git add lcport/__init__.py; git commit -qm "Release $VER" || true; }
NOTES="$(awk -v v="$VER" '/^## \[/{p=($0 ~ "\\["v"\\]")} p' CHANGELOG.md | tail -n +2)"
NAME="Lethal-Company-Port-$VER"; TMP="$(mktemp -d)"; mkdir -p "$TMP/$NAME"
git archive HEAD | tar -x -C "$TMP/$NAME"
ditto "Lethal Company Port.app" "$TMP/$NAME/Lethal Company Port.app"
(cd "$TMP" && zip -qr "$NAME.zip" "$NAME")
[ $DRY = 1 ] && { unzip -l "$TMP/$NAME.zip"; echo "dry run, zip at $TMP/$NAME.zip"; exit 0; }
git tag -f "v$VER"; git push -q origin HEAD --tags
gh release create "v$VER" "$TMP/$NAME.zip" --title "Launcher $VER" --notes "$NOTES"
echo "released v$VER"

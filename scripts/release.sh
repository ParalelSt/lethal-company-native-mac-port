#!/bin/zsh
# Maintainer: package the kit and publish a GitHub release whose notes are the matching CHANGELOG section.
# Usage: scripts/release.sh 0.2.0      (requires: gh auth login; clean git tree; CHANGELOG has a "## [0.2.0]" section)
set -e
VER="${1:?version, e.g. 0.2.0}"; KIT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$KIT"
[ -z "$(git status --porcelain)" ] || { echo "commit or stash changes first"; exit 1; }
grep -q "^## \[$VER\]" CHANGELOG.md || { echo "CHANGELOG.md has no section for $VER"; exit 1; }
sed -i '' "s/^__version__ = .*/__version__ = \"$VER\"/" lcport/__init__.py
git add lcport/__init__.py; git commit -qm "Release $VER" || true
NOTES="$(awk -v v="$VER" '/^## \[/{p=($0 ~ "\\["v"\\]")} p' CHANGELOG.md | tail -n +2)"
NAME="Lethal-Company-Port-$VER"; TMP="$(mktemp -d)"; mkdir -p "$TMP/$NAME"
git archive HEAD | tar -x -C "$TMP/$NAME"
(cd "$TMP" && zip -qr "$NAME.zip" "$NAME")
git tag -f "v$VER"; git push -q origin HEAD --tags
gh release create "v$VER" "$TMP/$NAME.zip" --title "Launcher $VER" --notes "$NOTES"
echo "released v$VER"

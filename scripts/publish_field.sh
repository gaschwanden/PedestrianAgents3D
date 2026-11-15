#!/usr/bin/env bash
# Publish web/ (field page, scene pack, browser runtime) to the gh-pages branch.
#
# The pack is build output and about 110 MB, so it is not kept in the source
# history: each publish is one fresh commit that replaces the branch.
# Build the pack first:  (cd python && python -m pedsim pack)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Argument: a remote name (default origin) or a full URL. On a network that
# blocks SSH port 22, GitHub also answers on 443:
#   scripts/publish_field.sh ssh://git@ssh.github.com:443/<owner>/<repo>.git
REMOTE="${1:-origin}"
case "$REMOTE" in
  *://*|*@*:*) URL="$REMOTE" ;;
  *) URL="$(git -C "$ROOT" remote get-url "$REMOTE")" ;;
esac
[ -f "$ROOT/web/packs/goebekli/index.json" ] || { echo "no pack in web/: run python -m pedsim pack" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -R "$ROOT/web/." "$WORK/"
touch "$WORK/.nojekyll"
find "$WORK" -name .DS_Store -delete
cd "$WORK"
git init -q -b gh-pages
git add -A
git -c user.name="$(git -C "$ROOT" config user.name)" \
    -c user.email="$(git -C "$ROOT" config user.email)" \
    commit -q -m "Field page $(date -u +%Y-%m-%dT%H:%MZ) from $(git -C "$ROOT" rev-parse --short HEAD)"
git push -f "$URL" gh-pages
echo "pushed gh-pages to $URL"

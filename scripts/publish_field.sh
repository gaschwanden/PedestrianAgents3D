#!/usr/bin/env bash
# Publish web/ (field page, scene pack, browser runtime) to the gh-pages branch.
#
# The pack is build output and about 230 MB, so it is not kept in the source
# history. Each publish adds one commit on top of the published branch, and
# only files that changed are uploaded: the published branch is fetched without
# its file contents (a "blobless" fetch, a few hundred kB), so git knows which
# files the server already has.
#
# Argument: a remote name (default origin) or a full URL. On a network that
# blocks SSH port 22, GitHub also answers on 443:
#   scripts/publish_field.sh ssh://git@ssh.github.com:443/<owner>/<repo>.git
# Build the pack first:  (cd python && python -m pedsim pack)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${1:-origin}"
case "$REMOTE" in
  *://*|*@*:*) URL="$REMOTE" ;;
  *) URL="$(git -C "$ROOT" remote get-url "$REMOTE")" ;;
esac
[ -f "$ROOT/web/packs/goebekli/index.json" ] || { echo "no pack in web/: run python -m pedsim pack" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
git init -q -b gh-pages
git config user.name "$(git -C "$ROOT" config user.name)"
git config user.email "$(git -C "$ROOT" config user.email)"
# a filtered fetch needs a named remote that is marked as the source of the
# file contents left out
git remote add published "$URL"
git config remote.published.promisor true
git config remote.published.partialclonefilter blob:none
PARENT=""
if git fetch -q --filter=blob:none --depth=1 published gh-pages; then
  PARENT="$(git rev-parse refs/remotes/published/gh-pages)"
  git update-ref refs/heads/gh-pages "$PARENT"
else
  echo "no published branch yet (or fetch failed): this publish uploads everything" >&2
fi
# the working tree is web/ as built now; the index starts empty, so files that
# were removed from web/ are removed from the published branch too
cp -R "$ROOT/web/." "$WORK/"
touch "$WORK/.nojekyll"
find "$WORK" -name .DS_Store -delete
git add -A
git commit -q -m "Field page $(date -u +%Y-%m-%dT%H:%MZ) from $(git -C "$ROOT" rev-parse --short HEAD)"
if [ -n "$PARENT" ]; then
  echo "changed since the last publish:"
  git diff --no-renames --name-only --no-ext-diff "$PARENT" HEAD -- 2>/dev/null | sed 's/^/  /' | head -40 || true
fi
git push --no-verify published gh-pages
echo "pushed gh-pages to $URL"

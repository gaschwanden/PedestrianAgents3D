#!/usr/bin/env bash
# Download the browser Python runtime the field page needs into web/vendor/pyodide.
# It is about 17 MB and not kept in the source history.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="0.27.7"
BASE="https://cdn.jsdelivr.net/pyodide/v${VERSION}/full"
DEST="$ROOT/web/vendor/pyodide"
mkdir -p "$DEST"
for f in pyodide.js pyodide.asm.js pyodide.asm.wasm python_stdlib.zip pyodide-lock.json \
         numpy-2.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl \
         pyyaml-6.0.2-cp312-cp312-pyodide_2024_0_wasm32.whl; do
  [ -s "$DEST/$f" ] || curl -fL --retry 3 "$BASE/$f" -o "$DEST/$f"
done
echo "Pyodide ${VERSION} in $DEST"

#!/usr/bin/env bash
# Compile the PedestrianAgents3D Java sources into bin/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CP="library/core.jar:library/jogl-all.jar:library/gluegen-rt.jar:library/TUIO.jar:library/libTUIO.jar"

rm -rf bin
mkdir -p bin
# shellcheck disable=SC2046
javac -encoding UTF-8 -cp "$CP" -d bin $(find src -name '*.java')

echo "Build complete -> $ROOT/bin"

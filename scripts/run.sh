#!/usr/bin/env bash
# Launch the PedestrianAgents3D application.
#
# NOTE: the sketch derives its data folder from the process working
# directory (it strips the trailing "bin/text" -> project root), so the
# JVM must be started from the project's bin/ directory. This script
# handles that automatically.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DISPLAY="${DISPLAY:-:99}"

if [ ! -f "$ROOT/bin/Agents.class" ]; then
  echo "Compiled classes not found; building first..." >&2
  bash "$ROOT/scripts/build.sh"
fi

# Base (cross-platform) libraries.
LIBS=(
  "bin"
  "library/core.jar"
  "library/jogl-all.jar"
  "library/gluegen-rt.jar"
  "library/TUIO.jar"
  "library/libTUIO.jar"
)

# Platform-specific JOGL/GlueGen native libraries.
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64|Linux-amd64)
    LIBS+=("library/jogl-all-natives-linux-amd64.jar" "library/gluegen-rt-natives-linux-amd64.jar")
    ;;
  Darwin-*)
    LIBS+=("library/jogl-all-natives-macosx-universal.jar" "library/gluegen-rt-natives-macosx-universal.jar")
    ;;
esac

# Build an absolute classpath (the JVM is launched from bin/).
CP=""
for entry in "${LIBS[@]}"; do
  CP="${CP:+$CP:}$ROOT/$entry"
done

cd "$ROOT/bin"
exec java -cp "$CP" Agents "$@"

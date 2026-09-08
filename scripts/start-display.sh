#!/usr/bin/env bash
# Start a virtual X display (Xvfb) with software OpenGL so the OpenGL
# sketch can run on a headless machine. Idempotent: safe to run repeatedly.
set -euo pipefail

DISPLAY_NUM="${DISPLAY_NUM:-99}"
SCREEN_GEOMETRY="${SCREEN_GEOMETRY:-1920x1080x24}"

if [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; then
  echo "Xvfb already running on :${DISPLAY_NUM}"
  exit 0
fi

setsid Xvfb ":${DISPLAY_NUM}" -screen 0 "${SCREEN_GEOMETRY}" \
  +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &

for _ in $(seq 1 50); do
  if [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; then
    echo "Xvfb ready on :${DISPLAY_NUM} (${SCREEN_GEOMETRY})"
    exit 0
  fi
  sleep 0.2
done

echo "Xvfb failed to start on :${DISPLAY_NUM}" >&2
cat /tmp/xvfb.log >&2 || true
exit 1

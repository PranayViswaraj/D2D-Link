#!/usr/bin/env bash
# Run a command inside the d2d-eda container with the repo mounted at /work.
# Usage: scripts/dk.sh "<command>"   (on Linux CI the tools are native; call the command directly)
set -euo pipefail
cd "$(dirname "$0")/.."
if command -v cygpath >/dev/null 2>&1; then HOSTDIR="$(pwd -W)"; else HOSTDIR="$(pwd)"; fi
MSYS_NO_PATHCONV=1 exec docker run --rm -v "${HOSTDIR}:/work" -w /work d2d-eda bash -c "$*"

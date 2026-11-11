#!/bin/sh
# Resolve paths relative to this file, even when invoked from another directory.
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for candidate in python3 python python3.15 python3.14 python3.13 python3.12; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    exec "$candidate" "$PROJECT_DIR/scripts/dev.py" "$@"
  fi
done
echo "Python 3.12 or newer is required. Install Python, then run this script again." >&2
exit 1

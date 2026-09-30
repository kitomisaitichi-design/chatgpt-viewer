#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ -x .semantic-env/bin/python ]; then
  exec .semantic-env/bin/python viewer.py "$@"
fi
exec python3 viewer.py "$@"

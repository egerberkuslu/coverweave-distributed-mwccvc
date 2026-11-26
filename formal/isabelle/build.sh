#!/bin/sh
# Memory-capped build: one build at a time, 10G cap, no swap, 4 threads; ML heap capped at 8G via ML_OPTIONS in isabelle-user/Isabelle2026/etc/settings.
# usage: ./build.sh SESSION [extra isabelle build options]
cd "$(dirname "$0")"
S="$1"; shift
exec systemd-run --user --scope -q -p MemoryMax=10G -p MemorySwapMax=0 \
  Isabelle2026/bin/isabelle build -d . -o threads=4 "$@" "$S"

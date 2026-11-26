#!/usr/bin/env bash
# Run every unfinished job of STAGE/jobs.jsonl with ccvc.bb.r1_run, WORKERS at a time.
#
#   SNAP=<snapshot root> R1_FROZEN_FINGERPRINT=<fp> WORKERS=12 run_pool.sh STAGE
#
# Modelled on results/bb/full_v3/densecomplete/run_pool.sh. Each job writes its
# own CSV and log, so a killed pool costs only the runs in flight, and starting
# it again resumes. R1_FROZEN_FINGERPRINT is required: r1_run then refuses a
# snapshot whose code_fingerprint differs, so no row is measured on other code.
set -u
STAGE=$(realpath "${1:?usage: run_pool.sh STAGE}")
: "${SNAP:?set SNAP to the snapshot root that holds ccvc/}"
: "${R1_FROZEN_FINGERPRINT:?set R1_FROZEN_FINGERPRINT to the snapshot fingerprint}"
SNAP=$(realpath "$SNAP")
export BB_SNAPSHOT="$SNAP" PYTHONPATH="$SNAP" R1_FROZEN_FINGERPRINT
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKERS=${WORKERS:-12}

mkdir -p "$STAGE/logs"
echo "POOL START $(date -Is) workers=$WORKERS snapshot=$SNAP fp=$R1_FROZEN_FINGERPRINT load=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$STAGE/pool.log"

python3 - "$STAGE/jobs.jsonl" <<'PY' |
import json, os, sys
for line in open(sys.argv[1]):
    j = json.loads(line)
    if not os.path.exists(j["out"] + ".done"):
        print(j["id"])
PY
# cd into the snapshot so `python3 -m ccvc.bb.r1_run` resolves there, not in the live tree
(cd "$SNAP" && xargs -P "$WORKERS" -I{} bash -c '
  id="$1"; start=$(date +%s)
  python3 -m ccvc.bb.r1_run --jobs "'"$STAGE"'/jobs.jsonl" --id "$id" >> "'"$STAGE"'/logs/$id.log" 2>&1
  rc=$?
  echo "$(date -Is) $id rc=$rc $(( $(date +%s) - start ))s load=$(cut -d" " -f1 /proc/loadavg)" >> "'"$STAGE"'/pool.log"
' _ {})

echo "POOL DONE $(date -Is)" >> "$STAGE/pool.log"

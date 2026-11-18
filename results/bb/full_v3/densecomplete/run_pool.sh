#!/usr/bin/env bash
# densecomplete worker pool.
#
# Runs every job in jobs.jsonl against the frozen snapshot, WORKERS at a time.
# Each job writes its own CSV and its own log, so killing the pool or losing
# the machine costs the runs in flight and nothing else; re-running this script
# picks up exactly where it stopped.
set -u
ROOT=/home/ege/Desktop/MDS_SKYFABRIC
SNAP=$ROOT/results/bb/full_v3/_snapshot_densecomplete
STAGE=$ROOT/results/bb/full_v3/densecomplete
export BB_SNAPSHOT="$SNAP"
export PYTHONPATH="$SNAP"
export MWCCVC_DATASET="$ROOT/data/DagdevirenDataset"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKERS=${WORKERS:-13}

mkdir -p "$STAGE/logs" "$STAGE/parts"
echo "POOL START $(date -Is) workers=$WORKERS snapshot=$SNAP" >> "$STAGE/pool.log"

python3 - "$STAGE/jobs.jsonl" <<'PY' |
import json, sys
for line in open(sys.argv[1]):
    j = json.loads(line)
    if not __import__("os").path.exists(j["out"] + ".done"):
        print(j["id"])
PY
xargs -P "$WORKERS" -I{} bash -c '
  id="$1"
  start=$(date +%s)
  python3 "'"$STAGE"'/run_job.py" --jobs "'"$STAGE"'/jobs.jsonl" --id "$id" \
      >> "'"$STAGE"'/logs/$id.log" 2>&1
  rc=$?
  echo "$(date -Is) $id rc=$rc $(( $(date +%s) - start ))s" >> "'"$STAGE"'/pool.log"
' _ {}

echo "POOL DONE $(date -Is)" >> "$STAGE/pool.log"

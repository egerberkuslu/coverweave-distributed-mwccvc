#!/usr/bin/env bash
# Block M7 of the R1 pre-registration on Mininet-WiFi, one run at a time.
#
#   bash ccvc/bb/mnwifi/run_m7.sh --w-set DIR [--release DIR] [--dataset DIR] [--out DIR]
#
# DIR of --w-set is the held-out set W written by `heldout --set W` after the
# freeze. The script refuses to start unless the release repository holds the
# annotated tag coverweave-r1-frozen; it then runs every step from a snapshot
# of that tag (git archive), so rows record the frozen code, not the live tree.
#
# The sudo password is read once from stdin (not echoed on a terminal), kept
# in one unexported shell variable and piped to `sudo -S` by the printf
# builtin, so it never reaches a file, a command line or a child environment.
#
# Before every run the host must be idle (no wmediumd, no Mininet node shell,
# low load); otherwise the batch stops and keeps the rows it has. Failed,
# truncated and unresolved runs keep their rows and costs and are never re-run.
set +x
set -euo pipefail
trap 'echo "interrupted; finished rows are kept" >&2; exit 130' INT TERM

TAG=coverweave-r1-frozen
LIVE=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
RELEASE=$HOME/Desktop/bbcvc-release
DATASET=$LIVE/data/DagdevirenDataset
OUT=$LIVE/results/bb/r1_m7
W_SET=""

die() { echo "ABORT: $*" >&2; exit 2; }

while [[ $# -gt 0 ]]; do
  case $1 in
    --w-set) W_SET=$2; shift 2 ;;
    --release) RELEASE=$2; shift 2 ;;
    --dataset) DATASET=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    *) die "unknown argument $1" ;;
  esac
done

# 1. The frozen tag, before a password is read or a file is written.
git -C "$RELEASE" rev-parse -q --verify "refs/tags/$TAG^{tag}" >/dev/null 2>&1 \
  || die "annotated tag $TAG not found in $RELEASE; M7 runs only at the frozen tag"
[[ -n $W_SET ]] || die "--w-set is required"
[[ -f $W_SET/manifest.json ]] || die "$W_SET/manifest.json not found"

# 2. Snapshot of the tagged tree, reused only if it is the same commit.
COMMIT=$(git -C "$RELEASE" rev-parse "$TAG^{commit}")
SNAP=$OUT/_snapshot
mkdir -p "$OUT"
if [[ -e $SNAP ]]; then
  [[ $(cat "$SNAP/.m7_commit" 2>/dev/null) == "$COMMIT" ]] \
    || die "$SNAP holds another tree than $TAG ($COMMIT); move it away"
else
  rm -rf "$SNAP.partial" && mkdir "$SNAP.partial"
  git -C "$RELEASE" archive "$TAG" | tar -x -C "$SNAP.partial"
  echo "$COMMIT" > "$SNAP.partial/.m7_commit"
  mv "$SNAP.partial" "$SNAP"
fi
cd "$SNAP"
export BB_SNAPSHOT=$SNAP PYTHONPATH=$SNAP
M7=(python3 -m ccvc.bb.mnwifi.m7)
FP=$(python3 -c 'from ccvc.bb import sweep; print(sweep.code_fingerprint())')
if [[ -n ${R1_FROZEN_FINGERPRINT:-} && $FP != "$R1_FROZEN_FINGERPRINT" ]]; then
  die "snapshot fingerprint $FP differs from R1_FROZEN_FINGERPRINT=$R1_FROZEN_FINGERPRINT"
fi
echo "M7 at $TAG ($COMMIT), code fingerprint $FP, output $OUT" >&2

# 3. Jobs (refuses a W set that is not the registered one), then the host.
JOBS=$("${M7[@]}" jobs --dataset "$DATASET" --w-set "$W_SET" --out "$OUT")
"${M7[@]}" idle || die "host is not idle; nothing was run"

# 4. The password, checked once. `-k` makes every sudo read it from the pipe,
# so the printf never writes into a pipe its reader has already left.
if [[ -t 0 ]]; then
  read -rsp "sudo password: " PW; echo >&2
else
  IFS= read -r PW || true
fi
printf '%s\n' "$PW" | sudo -S -k -p '' true 2>/dev/null || die "sudo rejected the password"

# 5. Serial runs.
TODO=$("${M7[@]}" todo --jobs "$JOBS")
echo "$(wc -w <<<"$TODO") runs to go" >&2
for ID in $TODO; do
  # The load of the previous run's evaluation decays within minutes; wait up to 5.
  for _ in 1 2 3 4 5 6 7 8 9 10; do "${M7[@]}" idle 2>/dev/null && break; sleep 30; done
  "${M7[@]}" idle || { echo "STOP before $ID: host is not idle; finished rows are kept" >&2; exit 3; }
  PLAN=$("${M7[@]}" plan --jobs "$JOBS" --id "$ID")
  RUN_DIR=${PLAN% *}
  LIMIT_S=${PLAN##* }
  echo "$(date '+%F %T') $ID (limit ${LIMIT_S}s)" >&2
  set +e
  # SIGINT lets run.py tear its network down in `finally`; the kill is a fallback.
  printf '%s\n' "$PW" | sudo -S -k -p '' -E timeout --signal=INT --kill-after=120 "$LIMIT_S" \
    env PYTHONPATH="$SNAP" python3 "$SNAP/ccvc/bb/mnwifi/run.py" run --resume "$RUN_DIR" \
    > "$RUN_DIR/harness.log" 2>&1
  RC=${PIPESTATUS[1]}
  set -e
  printf '%s\n' "$PW" | sudo -S -k -p '' chown -R "$(id -u):$(id -g)" "$RUN_DIR"
  "${M7[@]}" row --jobs "$JOBS" --id "$ID" --rc "$RC"
done
echo "M7 done: rows in $OUT/m7_rows.csv" >&2

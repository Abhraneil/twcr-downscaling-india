#!/usr/bin/env bash
# Step 12 of the multi-event pipeline: progress of every case (multievent/lib/cases.py status).
#
#   bash multievent/12_status.sh                  the cases that have started
#   bash multievent/12_status.sh --all            also those not started, or not created yet
#   bash multievent/12_status.sh --physics P0     any selection: --events, --drivers, --physics, --cases
#   watch -n 600 bash multievent/12_status.sh
#
# States: running (its lock is held: lib/run_case.sh), queued (a PBS/SLURM job waits), queue?
# (the scheduler did not answer), done (timing.txt), failed (failed.txt, with the reason; step 11
# continues it), stopped (started, not running, not finished), new (created, not started).
set -uo pipefail
source "$(dirname "$0")/00_env.sh"
$ME_CASES status "$@"

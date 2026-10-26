#!/usr/bin/env bash
# Step 6 of the multi-event pipeline: choose the 20 events by the rule fixed in
# docs/multievent/design.md (scripts/events/select_events.py), and write multievent/events.yaml.
#
#   bash multievent/06_select_events.sh
#
# Outputs (in the repository, to be committed): results/multievent/{candidates.csv,
# selected.csv, SELECTED.md, map_selected.png} and multievent/events.yaml. Before any case is
# created: document every event in docs/multievent/events.md (design.md, step 6), apply the
# single-cell rule if it is triggered, and commit, so the event list is fixed before the runs.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"
cd "$ME_REPO"
"$ME_PYTHON" scripts/events/select_events.py --obs "$TWCR_DATA/obs" --out results/multievent | tee "$ME_LOGS/06_select.log"
"$ME_PYTHON" - <<'PY'
import pandas as pd, yaml
s = pd.read_csv("results/multievent/selected.csv")
ev = {r.event: dict(first_label=str(r.first_label), last_label=str(r.last_label), lat=float(r.lat), lon=float(r.lon),
                    region=r.region, era=r.era, box_mm=round(float(r.box_mm), 1),
                    wettest_cell_share=round(float(r.wettest_cell_share), 2)) for r in s.itertuples()}
head = ("# The events of the multi-event study, written by multievent/06_select_events.sh from\n"
        "# results/multievent/selected.csv (scripts/events/select_events.py). Do not edit by hand: a\n"
        "# replacement under the single-cell rule (docs/multievent/design.md) is made in selected.csv\n"
        "# and recorded in docs/multievent/events.md.\n")
open("multievent/events.yaml", "w").write(head + yaml.safe_dump(ev, sort_keys=False))
flag = [k for k, v in ev.items() if v["wettest_cell_share"] > 0.5]
print(f"multievent/events.yaml: {len(ev)} events" + (f"; check against documents (one cell carries over half): {flag}" if flag else ""))
PY
me_log "step 6 done. Document the events (docs/multievent/events.md), commit, then: bash multievent/07_download_20crv3.sh"

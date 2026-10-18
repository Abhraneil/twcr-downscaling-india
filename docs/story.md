# The results as a story (figure order, captions, numbers)

Backbone for the write-up (`docs/writeup_outline.md`) and the README results section. Every
number is from `results/SCORECARD.md`, `results/HYPOTHESES.md` (scoring of 19 October 2026,
IMD labels 'backward') or read off the figures named next to it; "about" marks values read
from a plot. Figure files are in `results/figures/story/`.

## The story in three sentences

1. Over the Western Ghats in July 1924, both regional models turned 20CRv3's weak, smeared
   rain (bias -80%, pattern r 0.51) into an orographic rain band in about the right place
   (r 0.80-0.83 at 12 km, bias -39%), with clear added value in all four runs, but the
   modelled rain is still building two to three days after the observed peak and reaches only
   0.5-0.6 of the observed maximum.
2. No model, resolution or driver produced the Mumbai cloudburst of 26 July 2005. Near
   Santacruz the largest 24 h total of any run within 50 km is 163 mm, against 944 mm
   observed. ERA5-driven runs put their heavy rain in a narrow band on the Ghats rather than
   on the coastal plain, and 20CRv3-driven runs barely rain at all.
3. 3 km was not consistently better than 12 km. WRF at 3 km rained less than WRF at 12 km in
   every case; RegCM5 at 3 km raised the peaks but lost pattern correlation.

The contrast between 1 and 2 is the finding: rain that the terrain locks in place comes
through a pressure-only reanalysis and a regional model; rain from an organised convective
system over the coastal plain did not, even with a modern driver.

## Pre-registered criteria (docs/metrics.md), as they came out

| | Question | Result |
|---|---|---|
| H1 | Can the models produce the event when the driver is good? (E2, ERA5, 3 km) | **FAIL**: best is WRF 3 km, FSS 0.55 against a useful level of 0.60, bias -39% (limit 30%) |
| H2 | Does the historical driver cost little? (E2, 20CRv3 vs ERA5) | **FAIL** for all four: FSS lower by 0.31-0.55, bias -58% to -84% |
| H3 | Does downscaling add value over the driver? (FSS at 64.5 mm) | **PASS** for all E1 runs (+0.58 to +0.71) and E2 20CRv3 runs (+0.01 to +0.29); **FAIL** for all E2 ERA5 runs (-0.02 to -0.09) |
| H4 | Does 3 km beat 12 km on extremes? | **4 PASS, 2 FAIL**: fails for WRF driven by 20CRv3 in both events |
| H5 | Is the pre-1950 event reproduced? (E1, 3 km) | **PASS, narrowly**: RegCM5 3 km, FSS 0.70 against 0.68, bias -39% (limit 40%); WRF 3 km fails (0.57, -53%) |

Two points on H3. With ERA5 the driver itself already scores FSS 0.70 at 64.5 mm (better than
any downscaled run), so there is little to add at that threshold; at 115.6 mm the ERA5 driver
scores 0.06 and the downscaled runs 0.34-0.55, an added value of +0.28 to +0.49. With 20CRv3
in E2 the passes are real but small for three of the four runs (+0.01 to +0.05).

## Act 1: a flood rebuilt from surface pressure (E1, Kerala, July 1924)

**Fig. 1** `fig1_domains.png`. The shared 12 km domain (WRF d01 = RegCM5 12 km grid) over
terrain, the two 3 km domains of each model, and the two scoring boxes.

**Fig. 2** `fig2_E1_kerala1924_synoptic.png`. 20CRv3 on the wettest observed day (03 UTC 16 to
03 UTC 17 July 1924): a moist column over the Arabian Sea and the west coast, strong
850 hPa westerlies onto the Kerala coast and a monsoon low near the head of the Bay of Bengal. The large-scale
ingredients of an active monsoon spell are in the reanalysis, although it assimilates only
surface pressure. Caption note: sea-level pressure is not contoured over ground above 1000 m;
the black coastline is 20CRv3's own 1° land mask, which is why it is coarse.

**Fig. 3** `fig3_E1_kerala1924_totals.png`. Rain 13-20 July 1924 on the IMD grid. 20CRv3's
own rain is a smooth field with no Ghats maximum (bias -80%, r 0.51, FSS 0 at 115.6 mm).
Every downscaled run puts a band of heavy rain along the Ghats: WRF 12 km r 0.83, bias -39%,
heaviest cell 27 km from the observed one; RegCM5 12 km r 0.80, bias -39%. Nothing reaches
204.5 mm/day in the right place (FSS 0 at that threshold in every run).

**Fig. 4** `fig5_E1_kerala1924_daily.png`. Day by day over the box. The observed box mean
rises to about 104 mm on IMD day 17 July (24 h to 08:30 IST, matching the documented flood
peak at Aluva on 16-17 July) and falls after. Every run, and 20CRv3's own rain, is still
rising on 19-20 July. The late build-up is common to the driver and both models, which points
to the timing of the monsoon surge in 20CRv3 rather than to either regional model; the
20CRv3 ensemble members (below) are the way to test that.

## Act 2: the cloudburst nobody caught (E2, Mumbai, 26 July 2005)

**Fig. 5** `fig2_E2_mumbai2005_synoptic.png`. Both drivers on 26 July: a monsoon low over
central and eastern India with strong westerlies onto the Konkan coast. The two drivers agree
on the setting, so the large-scale conditions for heavy rain were there in both.

**Fig. 6** `fig3_E2_mumbai2005_totals.png`. Rain 25-29 July 2005. The observed heavy rain
covers the coastal plain and the Ghats from 17.5 to 19.5° N, Mumbai included. ERA5-driven runs
concentrate theirs in a narrow north-south band on the Ghats crest (WRF 12 km bias -17%,
WRF 3 km FSS 0.55 at 115.6 mm, the best scores of the experiment for this event) and leave the
coast with a fraction of the observed rain. 20CRv3-driven runs are 58-84% too dry everywhere.

**Fig. 7** `fig5_E2_mumbai2005_daily.png`. On IMD day 26 July (the day before) the ERA5-driven
runs come close to the observations (WRF 3 km box maximum about 400 mm against about 415 mm).
On IMD day 27 July, the cloudburst day, observed rain jumps to a box mean of about 137 mm and
a box maximum of 732.5 mm; every ERA5-driven run goes down instead, and the 20CRv3-driven runs
stay flat at a fraction of it.

**Fig. 8** `fig7_santacruz.png`. At the grid point nearest Santacruz no run passes 100 mm in
the 24 h in which 944 mm was measured. The largest 24 h total of any run within 50 km is
163 mm (RegCM5 3 km driven by 20CRv3); with ERA5 the largest is 91 mm (WRF 3 km).

Context for the discussion: Kumar et al. (2008, QJRMS) ran WRF 2.1 from the same start time
(00 UTC 24 July 2005), driven by 1° NCEP FNL, on 33/11/3.6 km domains (the 3.6 km one-way
nest started at 12 UTC 25 July), with WSM6 microphysics, Grell-Devenyi cumulus at 33 and
11 km and none at 3.6 km, RRTM/Dudhia radiation and the 5-layer thermal-diffusion land
surface. They report that this run "successfully captured" the Santacruz rainfall (the text
gives no simulated 24 h total; a run without the Ghats, at about 517 mm, is described as
about half of the control), and that Kain-Fritsch or Betts-Miller-Janjic underestimated the
rain by more than 50%. The event is known to be sensitive to the cumulus scheme, and our
configuration (Thompson + Grell-Freitas in WRF) is one that misses it. Whether the physics
alone explains the miss was not tested here (no further runs); it is the first item of
future work.

## Act 3: does 3 km help?

**Fig. 9** `fig6_scores.png`. All scores as a heatmap (darker = closer to perfect).

- WRF at 3 km (no cumulus scheme) is drier than WRF at 12 km (Grell-Freitas) in every case:
  E1 -39% to -53%, E2 20CRv3 -77% to -84%, E2 ERA5 -17% to -39%. With ERA5 it still
  sharpens the extremes (peak ratio 0.46 to 0.54, FSS 0.47 to 0.55); with 20CRv3 in 1924 it
  loses them (FSS 0.38 to 0.14).
- RegCM5 at 3 km is as wet or wetter than at 12 km and raises the peak ratio in all three
  cases (E1 0.52 to 0.62, E2 ERA5 0.23 to 0.41), but its pattern correlation drops (E1 0.80
  to 0.49, E2 ERA5 0.53 to 0.25) and its heaviest cell lands 110-315 km from the observed one.

Supplementary: **Fig. S1, S2** `fig4_<event>_native.png`, the event totals on the 3 km grids
with terrain contours. Caption notes: the east-west streaks over the sea lie along the
low-level westerlies; the pale frame around the RegCM5 domain is its lateral relaxation zone;
neither affects the scores, which use IMD land points only.

## Why the numbers can be trusted (a box in the write-up)

- **A WRF bug found and fixed, not worked around.** All three WRF runs first crashed with
  segmentation faults (E1 at 117.6 h, E2 at 74 h and 8.3 h). The cause was an out-of-bounds
  read in the Thompson rain-graupel lookup of WRF 4.5 (still present in 4.7.1), identified
  from the faulting instruction, reproduced in a stand-alone column test and patched
  (`patches/wrf45_thompson_fix.py`, `docs/validation.md` item 21). The patched runs finished
  without a single stop.
- **A 24 h shift caught before it was published.** The first scoring compared each model day
  with the next observed day. The date-label check found it from the data; the scorer now
  refuses to run when the check fails (`docs/validation.md` item 23).
- **Criteria fixed before the results.** H1-H5 and their thresholds were committed in
  `docs/metrics.md` on 15 October (260f8c9), before any run finished, have not been changed
  since, and are reported in full, failures included.

## Limitations to state

Two events, one deterministic run each (the 20CRv3 ensemble mean); H5 passes by 0.02 in FSS
and 0.6 percentage points of bias; the 1924 IMD grid rests on fewer gauges than the 2005 one;
present-day land use in 1924; different soil initialisation in the two models; the 944 mm is
a station total, compared with grid-point and 50 km values.

## What it points to

- **20CRv3 members instead of the ensemble mean.** Both the late 1924 build-up and the 2005
  miss are questions of timing and of chance in convection; downscaling a set of members gives
  a spread of rain, so an observed extreme can be judged against a distribution instead of one
  run.
- **Physics as part of the ensemble.** Kumar et al. (2008) show how much the cumulus choice
  matters for this coastal convective extreme; a physics ensemble (starting with WSM6 +
  Grell-Devenyi in our setup) would separate physics from driver and chance.
- **Bias correction of the downscaled 1924 rain** (-39% in three of four runs), checked against
  the IMD grid of other pre-1950 monsoon spells.

# Twenty Indian extreme-rainfall events downscaled from 20CRv3 (design)

Status: **draft, 26 October 2026.** The event-selection rule (section 2) is fixed by this commit,
before the ranking has been run on the IMD data. The physics set (section 4) and the criteria
(section 6) are proposals; they are fixed in a later commit, before the first model run, and not
changed after it. The two-event experiment (`docs/metrics.md`, H1-H5) is a separate study.

## 1. Question

The two-event experiment had one success and one failure with the same driver. WRF at 12 km rebuilt
the July 1924 Kerala rain band from 20CRv3, a rain band held in place by the Western Ghats
(pattern r 0.83; FSS 0.71 at 64.5 mm/day against a useful level of 0.68). No run reproduced the
26 July 2005 Mumbai cloudburst over the coastal plain (FSS at most 0.03 at 115.6 mm/day with
20CRv3). Two events cannot show which one is typical. This study asks:

**For which kinds of Indian extreme-rainfall events does WRF downscaling of 20CRv3 reproduce the
observed rain, and does the answer change before 1940, with the driver, or with the model physics?**

## 2. Events: chosen by a rule, not by hand

`scripts/events/select_events.py`, on IMD 0.25 deg daily rainfall (Pai et al. 2014), 1901-2015.
1901 is the first IMD year and 2015 the last 20CRv3 year.

1. **Severity:** the rain of 3 consecutive IMD days, averaged over a 5 x 5-cell box (1.25 deg,
   about 130 km side) around each cell, over the cells with data on all three days. At least 13
   of the 25 cells must have data, so coastal boxes count. This scale fits a 12 km model scored on
   the IMD grid. A single-station cloudburst is not what this measures.
2. **Regions** (by box centre, checked in this order):
   - Northeast: lon >= 89.5.
   - North and northwest: lat >= 23.5 and lon < 82.
   - East: lat >= 18 and lon >= 82.
   - West coast and Ghats: lat < 21.5 and less than 0.85 deg of longitude east of the coast.
     The coast is interpolated between ten coastal towns from Thiruvananthapuram to Valsad.
   - Central and south: the rest. This includes Saurashtra, the Deccan and the east coast south
     of 18N.
3. **Eras:** 1901-1939 (20CRv3 only) and 1940-2015 (ERA5 exists too). The era is set by the
   first day of the window.
4. **Independent events:** windows within 7 days and 500 km of a larger one are the same storm.
5. **Choice:** the 2 largest independent events in each region and era: 5 x 2 x 2 = **20 events**.
   The last usable window ends on 27 December 2015.
6. **Documents, as a check and not a filter.** Each selected event is looked up in contemporary
   reports and the literature (`docs/multievent/events.md`). One case leads to replacement: an
   event whose box total comes over half from one cell (`wettest_cell_share > 0.5`) and that no
   document supports. It is then treated as a probable gauge error and replaced by the next event
   in its stratum, and the replacement is reported.
7. **Anchors.** Kerala 1924 and Mumbai 2005 are run in this configuration as well and reported
   next to the 20 (as anchors, unless the rule selects them anyway). This connects the two studies.

The rule favours large, multi-day events, because they are the floods that matter regionally and
the scale a reanalysis-driven model can be judged on. Ranking by rain relative to the local
climate is reported (`box_over_mean_annual_max`) but not used: it would favour storms in the dry
northwest over the great floods of the wet regions.

## 3. Model set-up

- **WRF 4.5 with the Thompson fix** (`patches/wrf45_thompson_fix.py`; the unpatched model crashes
  or reads wrong table values, `docs/validation.md` item 21). The same build is used on both HPCs.
- **Domains: 36 km and 12 km, one-way, ratio 3.**
  - d01 (36 km): the whole monsoon region, about 40-120E, 15S-45N, the same for every event.
    The driver is about 1 deg, so the step from driver to d01 is about 3.
  - d02 (12 km): about 150 x 150 points (1,800 km), centred on the event box.
  - 50 levels, top 50 hPa, Mercator, as in the two-event experiment.
  - A 12 km domain the size of only the site would be driven almost entirely by its boundaries
    (domain-size studies, e.g. Leduc and Laprise 2009, Climate Dynamics). The 12 km domain
    that scored best in the two-event experiment was about 3,200 x 2,900 km.
- **Drivers:** the 20CRv3 ensemble mean for every event, and ERA5 for the 10 events from 1940.
- **Dates:**
  - Simulation: from 00 UTC 27 h before the first scored window to 00 UTC after the last.
  - Scored: the 3 IMD days of the event plus one day before and one day after (5 days), so a
    1-day timing error is seen and not hidden.
  - IMD date labels are converted to UTC windows with `observations.imd_label` (checked from the
    data, `docs/validation.md` item 23).

## 4. Physics set (fixed before the runs; each variant changes one thing)

| ID | Change from P0 | Why |
|---|---|---|
| P0 | Thompson, Grell-Freitas (both domains), YSU, revised MM5 surface layer, Noah, RRTMG, one-way | the set-up of the two-event experiment |
| P1 | Kain-Fritsch cumulus | the most common alternative; Litta et al. (2007) found the cumulus choice decisive |
| P2 | Tiedtke cumulus | the cumulus scheme of our RegCM5 runs; RegCM5 12 km had the best pattern r with ERA5 in Mumbai (0.53) |
| P3 | no cumulus scheme at 12 km (Grell-Freitas at 36 km only) | grey-zone test; the explicit 3 km runs were drier than 12 km |
| P4 | WSM6 microphysics | Kumar et al. (2008) report capturing Mumbai 2005 with WSM6 + Grell-Devenyi |
| P5 | MYNN 2.5 boundary layer and MYNN surface layer | boundary-layer moisture supply to convection |
| P6 | two-way nesting (feedback = 1) | Litta et al. (2007) nested two-way |

That gives 7 set-ups x 30 event-driver pairs = **210 runs**, plus the anchors.

## 5. Scoring

Same code and metrics as the two-event experiment (`docs/metrics.md`): IMD grid, conservative
remap, land cells inside the event box plus 1 deg, bias, pattern r, peak ratio, SAL, FSS at 64.5,
115.6 and 204.5 mm/day over 1-9 points, and added value over the driver's own rain.
- **Primary score:** FSS at 64.5 mm/day, 5 points.
- **Event scale** (used in M2): the number of IMD cells whose 3-day event total is at least
  3 x 64.5 mm. It is computed from the observations only.

## 6. Criteria (draft; fixed before the first run)

With 20 events these are tests, not single cases.

| ID | Statement | Test (P0 unless stated) |
|---|---|---|
| M1 | Downscaling adds value over 20CRv3 | `AV_FSS_64.5mm_5pt` > 0 in at least 15 of 20 events (one-sided sign test, p = 0.021) |
| M2 | Skill grows with event scale | Spearman correlation of event scale with FSS (20CRv3) > 0, p < 0.05 |
| M3 | After 1940 the historical driver costs little | FSS(ERA5) - FSS(20CRv3) <= 0.15 in at least 7 of 10 events |
| M4 | 20CRv3 events before 1940 are harder | FSS (20CRv3) lower in 1901-1939 than in 1940-2015, one-sided Mann-Whitney p < 0.05 |
| M5 | Choosing physics by region helps on unseen events | Leave-one-event-out: the set-up best on the other events of the region beats P0 on the held-out event in at least 15 of 20 (p = 0.021) |
| M6 | The events are reproduced | FSS at 64.5 mm, 9 points, at or above the useful level and abs(bias) <= 40% (the H5 rule) in at least 10 of 20 events |

**M5 is how the sensitivity study avoids tuning on the answer.** No set-up is ever judged on an
event that helped choose it. Physics spread (P0-P6) is reported for every event as an uncertainty
range.

## 7. Compute

- **Measured:**
  - 12 km + 3 km cost 25 core-hours per simulated day when the node was quiet (post-hoc run:
    18,711 s on 24 ranks for 5 days).
  - It cost about 60 core-hours per simulated day under heavy load (`docs/validation.md`).
- **Estimate:**
  - 36 + 12 km is about 54 million column-steps per simulated day, against about 430 million for
    12 + 3 km. That is 3-8 core-hours per simulated day.
  - 210 runs x 7 simulated days x 3-8 core-hours = **4,400-11,800 core-hours**.
- **Capacity:** the second HPC has 8 nodes x 16 cores = 128 cores, so about **1.5-4 days** with
  8 runs of 16 ranks at a time. WRF stays on one node per run, so nothing depends on the
  interconnect. The first HPC adds capacity.

## 8. To build (after 30 October)

1. Run the selection on IMD 1901-2015 (`get_imd.py` for 115 years: about 3 GB of raw files and the same
   again as netCDF), then write
   `docs/multievent/events.md` (documents for each event).
2. Config for the study: events from `results/multievent/selected.csv`, the 36/12 km geometry,
   physics P0-P6. `generate_namelists.py` writes one namelist per event x driver x set-up.
3. Driver subsets: 20CRv3 (OPeNDAP) for 20 events; ERA5 (CDS, queue) for 10, on the 36 km domain.
4. WRF build with the Thompson fix on the second HPC; scheduler scripts (PBS or SLURM), one run
   per node.
5. Scoring with 5-day event windows; statistics M1-M6.
6. Fix the physics set and M1-M6 in a commit **before the first run**.

## References

- Pai et al. 2014, MAUSAM 65:1-18 (IMD 0.25 deg rainfall)
- Slivinski et al. 2019, QJRMS 145:2876-2908 (20CRv3)
- Hersbach et al. 2020, QJRMS 146:1999-2049 (ERA5)
- Litta et al. 2007, Meteorol. Appl. 14:291-295
- Kumar et al. 2008, QJRMS 134:1897-1910
- Leduc and Laprise 2009, Regional climate model sensitivity to domain size, Climate Dynamics (volume and pages to be checked)
- Roberts and Lean 2008, Mon. Wea. Rev. 136:78-97

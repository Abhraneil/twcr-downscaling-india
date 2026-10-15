# Experiment design

## Question

Can regional models driven by the **20th Century Reanalysis v3 (20CRv3)** reproduce
extreme west-coast monsoon rainfall over India, and does that skill hold for an event
before 1950, when 20CRv3 is the only three-dimensional reanalysis available?

20CRv3 assimilates only surface pressure, with prescribed SST, sea ice and radiative
forcing (Slivinski et al. 2019, 2021). Its circulation is constrained by observations;
its moisture and rainfall come from the GFS model physics. Dynamical downscaling of
20CR has been demonstrated for historical heavy precipitation in the Alps (Stucki et
al. 2020) and for 1816 in Europe, but not over India and not with two regional models
side by side. This experiment does both, on two events, with pre-registered scores.

## Events

| | E1 | E2 |
|---|---|---|
| Event | Great Flood of 1924 ("flood of 99"), Kerala | 26 July 2005 Mumbai extreme rainfall |
| Era | pre-1950 | 1981-2015 |
| Regime | SW monsoon, orographic rain on the Western Ghats | SW monsoon, west coast and Ghats, 944 mm at Santacruz |
| Simulation | 1924-07-12 00 UTC to 07-20 06 UTC (198 h) | 2005-07-24 00 UTC to 07-29 06 UTC (126 h) |
| Spin-up | 27 h before the first scored window | 27 h |
| Scored | 7 days, 13-20 July (03-03 UTC) | 4 days, 25-29 July (03-03 UTC) |
| Drivers | 20CRv3 (ERA5 starts in 1940) | 20CRv3 and ERA5 |
| Scoring box | 8.0-12.5 N, 74.5-77.5 E | 17.5-20.5 N, 72.5-74.5 E |

**Why two rainfall events and not a humid heatwave.** The experiment has to be scored
against gridded observations in both eras. IMD's 0.25 deg rainfall grid starts in 1901
(Pai et al. 2014); IMD's gridded temperature starts in 1951 and there is no gridded
humidity for the 1920s, so a pre-1950 humid heatwave cannot be verified on a grid.
Both events are in the same regime (west-coast monsoon rain), so the only thing that
changes between them is the era and the density of observations behind 20CRv3.
A humid-heatwave extension (station-based wet-bulb verification) is listed under
follow-ups.

**Why E2 is the control.** For 2005 we can drive the same models with ERA5. The
difference between the ERA5-driven and 20CRv3-driven runs isolates the cost of the
historical driver, which is exactly what E1 cannot tell us on its own.

## Drivers

| | 20CRv3 | ERA5 |
|---|---|---|
| Product | ensemble mean of 80 members, 3-hourly analysis | deterministic reanalysis |
| Grid used | 1 deg regular (as served by NOAA PSL), 28 pressure levels | 0.25 deg, 37 pressure levels |
| Boundary interval | 3 h | 3 h (subsampled from hourly, to match) |
| Soil | Noah 4 layers (0-10-40-100-200 cm) | 4 layers (0-7-28-100-289 cm) |
| SST | prescribed HadISST2 (skin temperature over ocean) | ERA5 SST, skin temperature over land |

The ensemble mean is used, as in Stucki et al. (2020) and the 1816 study: it is the
minimum-error estimate and costs one run instead of 80. Individual members are a
follow-up (they come as whole-globe yearly tarballs at NERSC and cannot be subset in
time for the 24 October deadline).

## Resolutions

| Level | Grid | Why |
|---|---|---|
| Intermediate | **12 km** (0.11 deg class) | CORDEX-CORE resolution; ratio about 9 to the 1 deg driver, within the range used for single-step reanalysis downscaling; convection parameterised |
| High | **3 km** | convection-permitting; ratio 4 to the 12 km grid; the scale at which Kumar et al. (2008) reproduced the Mumbai record (3.6 km) |

The 12 km grid is one shared domain for both events and both models
(271 x 241 points, Mercator true at 15 N, 1.8-27.5 N, 60.9-91.1 E). Each event has its
own 3 km domain of 241 x 241 points (720 km), centred on the scoring box.
Exact corners and nest indices are in `namelists/GEOMETRY.md`.

## Models

Each model runs in its own reference configuration, as in CORDEX, so the comparison
is between model systems rather than between single parameterisations.

| | WRF-ARW 4.5 | RegCM5 (MOLOCH core) |
|---|---|---|
| Nesting | one run, d01 12 km + d02 3 km, one-way (`feedback = 0`) | 12 km run from the reanalysis, then 3 km run nested on its output (`FNEST`) |
| Dynamics | non-hydrostatic, 50 levels, top 50 hPa | non-hydrostatic MOLOCH, 30 levels (12 km) / 50 levels (3 km) |
| Time step | 60 s / 15 s | 90 s / 30 s |
| Microphysics | Thompson | Nogherotto-Tompkins (`ipptls = 2`) |
| Convection | Grell-Freitas at 12 km, none at 3 km | Tiedtke at 12 km, none at 3 km |
| PBL / surface layer | YSU / revised MM5 | Holtslag / Zeng ocean fluxes |
| Land surface | Noah, initialised from the driver soil | BATS, initialised from RegCM defaults |
| Radiation | RRTMG, no aerosol | CCSM, no aerosol (`iclimaaer = 0`) |
| Greenhouse gases | CMIP6 historical (by year) | CMIP6 historical (by year, `SSP245` table) |
| Interior nudging | none | none (spectral relaxation of the model top only, MOLOCH default) |
| Lateral boundary | 5-point specified/relaxation zone | exponential relaxation, 20 points (12 km), 31 points (3 km) |

RegCM5 physics follow the CORDEX namelists shipped with the model
(`Testing/CORDEX/EUR-12_RegCM5_ERA5.namelist`, `EUR-03_RegCM5_ERA5.namelist`).
RegCM5 has no 20CRv3 reader, so 20CRv3 and ERA5 are both written in the layout of the
RegCM5 ERA5 reader (`scripts/preprocess/to_regcm.py`). WRF reads both drivers from
WPS intermediate files written by the same Python code (`scripts/preprocess/to_wps.py`),
so ungrib is not involved and both drivers follow one code path in each model.

**COSMO-CLM** is not included: its source is restricted to CLM-Community members and
cannot be redistributed in a public repository. See `docs/model_availability.md`.

## Run matrix

| | WRF 12+3 km | RegCM5 12 km | RegCM5 3 km | Driver alone |
|---|---|---|---|---|
| E1 1924, 20CRv3 | run 1 | run 2 | run 3 | baseline |
| E2 2005, 20CRv3 | run 4 | run 5 | run 6 | baseline |
| E2 2005, ERA5 | run 7 | run 8 | run 9 | baseline |

Nine model runs, 12 scored products (WRF gives both resolutions), plus the drivers'
own rainfall as the no-downscaling baseline. Compute and storage: `docs/budget.md`.

## Known limitations, stated up front

- Two events are case studies. No statistical significance is claimed; the
  pre-registered criteria in `docs/metrics.md` are pass/fail statements per case.
- Present-day land use (MODIS in WRF, GLCC in RegCM) is used for 1924.
- IMD's 1924 grid rests on fewer gauges than 2005; observation uncertainty is larger for E1.
- The two models start their soil moisture differently (driver vs model default).
- 20CRv3 precipitation (the baseline) is a 3-hourly forecast field; its window
  convention is documented in `docs/metrics.md`.

## References

- Slivinski et al. 2019, QJRMS, doi:10.1002/qj.3598 (20CRv3 system)
- Slivinski et al. 2021, J. Climate 34:1417-1438 (20CRv3 evaluation)
- Stucki et al. 2020, NHESS 20:35 (WRF downscaling of 20CR, 1876/1910/2005 floods)
- Pai et al. 2014, MAUSAM 65:1-18 (IMD 0.25 deg rainfall)
- Kumar et al. 2008, QJRMS 134:1897-1910 (WRF simulation of 26 July 2005, Mumbai)
- Coppola, Giorgi, Giuliani et al. 2024, "The Fifth Generation Regional Climate Modeling System, RegCM5", ESS Open Archive, doi:10.22541/essoar.170542078.80092084/v1
- Skamarock et al. 2019, NCAR/TN-556+STR (WRF version 4)
- Pham et al. 2021, GMD 14:985-1005 (ICON-CLM)

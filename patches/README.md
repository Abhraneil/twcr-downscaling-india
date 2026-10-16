# Patches to model source

## `regcm5_fnest_z0.patch` (RegCM5 commit 06a50b5)

**Bug.** When a MOLOCH (`idynamic = 3`) domain is nested in MOLOCH output (`dattyp = 'FNEST'`),
`init_nest` in `PreProc/ICBC/mod_nest.F90` reverses the model-level heights `z0` to
bottom-to-top order for the vertical interpolation and never restores them. The ICBC
writer (`writef` in `mod_write.F90`) then builds the Exner function and surface pressure
(`pai_compute`, `extrapolate_surface_pressure`) on reversed heights, placing the model top
at the surface.

**Symptom.** 3 km ICBC surface pressure is about 1.5 times the true value and the lowest-level
Exner function is about 0.4 instead of about 1; the model runs but collapses to a surface
pressure near 50 hPa.

**Fix.** Reverse `z0` only around the interpolation in `get_nest` and leave it in model
order otherwise (3 lines).

**Verification** (`docs/validation.md`): after the patch, the nested surface pressure equals an
independent hypsometric reduction of the 12 km output to the 3 km terrain within 0.02%, and
the Exner profile matches the 12 km ICBC (0.95-1.00 at the surface, 0.28 at the top).

`scripts/setup/hpc_setup.sh` applies it automatically after checking out the pinned commit.
It should be reported to github.com/ICTP/RegCM.

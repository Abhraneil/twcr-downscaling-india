# RegCM5 static data for this experiment, downloaded on a Windows machine and copied to the HPC.
# Use this when the HPC node gets "403 Forbidden" from clima-dods.ictp.it (it did on ours:
# the site refuses some institutional addresses but serves ordinary connections).
# Same 11 files as get_regcm_static.sh (about 2.6 GB).
#   powershell -ExecutionPolicy Bypass -File get_regcm_static_windows.ps1 user@hpc-address
param([Parameter(Mandatory=$true)][string]$Dest)
$S = "http://clima-dods.ictp.it/regcm4"
$files = @(
  "SURFACE/GMTED_DEM_30s.nc",
  "SURFACE/GLCC_BATS_30s.nc",
  "SURFACE/GLZB_SOIL_30s.nc",
  "CMIP6/GHG/mole-fraction-of-carbon-dioxide-in-air_input4MIPs_GHGConcentrations_CMIP_UoM-CMIP-1-2-0_gr-0p5x360deg_000001-201412.nc",
  "CMIP6/GHG/mole-fraction-of-methane-in-air_input4MIPs_GHGConcentrations_CMIP_UoM-CMIP-1-2-0_gr-0p5x360deg_000001-201412.nc",
  "CMIP6/GHG/mole-fraction-of-nitrous-oxide-in-air_input4MIPs_GHGConcentrations_CMIP_UoM-CMIP-1-2-0_gr-0p5x360deg_000001-201412.nc",
  "CMIP6/GHG/mole-fraction-of-cfc11-in-air_input4MIPs_GHGConcentrations_CMIP_UoM-CMIP-1-2-0_gr-0p5x360deg_000001-201412.nc",
  "CMIP6/GHG/mole-fraction-of-cfc12-in-air_input4MIPs_GHGConcentrations_CMIP_UoM-CMIP-1-2-0_gr-0p5x360deg_000001-201412.nc",
  "CMIP6/O3/vmro3_input4MIPs_ozone_CMIP_UReading-CCMI-1-0_gn_190001-194912.nc",
  "CMIP6/O3/vmro3_input4MIPs_ozone_CMIP_UReading-CCMI-1-0_gn_200001-201412.nc",
  "CMIP6/SOLAR/solarforcing-ref-mon_input4MIPs_solar_CMIP_SOLARIS-HEPPA-3-2_gn_185001-229912.nc"
)
foreach ($f in $files) {
  New-Item -ItemType Directory -Force (Split-Path "RCMDATA/$f") | Out-Null
  curl.exe -fL -C - -o "RCMDATA/$f" "$S/$f"
  if ($LASTEXITCODE -ne 0) { Write-Error "failed: $f"; exit 1 }
}
scp -r RCMDATA\SURFACE RCMDATA\CMIP6 "${Dest}:~/TWCR/RCMDATA/"

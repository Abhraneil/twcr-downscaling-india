# Sourced by every numbered script in multievent/. Not run on its own.
#   source multievent/00_env.sh
# Reads multievent/site.env (copy site.env.example), loads the toolchain, and defines the
# directory layout:
#   $ME_ROOT/prefix     libraries built by 01 (zlib, HDF5, netCDF, MPICH if needed)
#   $ME_ROOT/build      WRF and WPS built by 02
#   $ME_ROOT/venv       Python environment made by 03
#   $ME_ROOT/data       obs/ (IMD), drivers/ (20CRv3, ERA5), daily/ (rain on the IMD grid)
#   $ME_ROOT/runs       wps/<event>/ and cases/<case>/
#   $ME_ROOT/logs       one log per step
export ME_REPO=${ME_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
ME_SITE=${ME_SITE:-$ME_REPO/multievent/site.env}
if [ -f "$ME_SITE" ]; then
  source "$ME_SITE"
else
  echo "note: no $ME_SITE (copy multievent/site.env.example); using defaults" >&2
fi
export ME_ROOT=${ME_ROOT:-$HOME/multievent}
export ME_PREFIX=$ME_ROOT/prefix ME_BUILD=$ME_ROOT/build ME_RUNS=$ME_ROOT/runs ME_LOGS=$ME_ROOT/logs
export ME_SRC=$ME_ROOT/src ME_THOMPSON_TABLES=$ME_ROOT/thompson_tables
mkdir -p "$ME_LOGS" 2>/dev/null || true

# toolchain: modules, a site env script, then anything 01 built. Site scripts are sourced with
# errexit/nounset off (vendor scripts such as Intel's setvars.sh are not written for them).
_me_flags=$-            # (not $(set +o): a command substitution does not see errexit)
set +eu
if [ -n "${ME_MODULES:-}" ]; then
  if ! type module > /dev/null 2>&1; then    # non-interactive shells (batch jobs) may lack it
    for f in /etc/profile.d/modules.sh /etc/profile.d/lmod.sh /usr/share/lmod/lmod/init/bash; do
      [ -f "$f" ] && source "$f" && break
    done
  fi
  if type module > /dev/null 2>&1; then
    module load $ME_MODULES > /dev/null 2>&1 || echo "WARNING: module load $ME_MODULES failed" >&2
  else
    echo "WARNING: ME_MODULES is set but the module command is not available in this shell" >&2
  fi
fi
if [ -n "${ME_ENV_SCRIPT:-}" ] && [ -f "$ME_ENV_SCRIPT" ] && [ -z "${ME_ENV_LOADED:-}" ]; then
  source "$ME_ENV_SCRIPT"; export ME_ENV_LOADED=1
fi
case $_me_flags in *e*) set -e ;; esac
case $_me_flags in *u*) set -u ;; esac
unset _me_flags
if [ -d "$ME_PREFIX/bin" ]; then
  case ":$PATH:" in *":$ME_PREFIX/bin:"*) ;; *) export PATH=$ME_PREFIX/bin:$PATH ;; esac
  export LD_LIBRARY_PATH=$ME_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
fi
# netCDF prefix for WRF/WPS: $ME_PREFIX/netcdf (01 makes it: built libraries, or links to the system's)
[ -d "$ME_PREFIX/netcdf" ] && export NETCDF=$ME_PREFIX/netcdf

export ME_WRF_DIR=${ME_WRF_DIR:-$ME_BUILD/WRF-4.5}
export ME_WPS_DIR=${ME_WPS_DIR:-$ME_BUILD/WPS-4.5}
export ME_WPS_GEOG=${ME_WPS_GEOG:-$HOME/WRFCHEM/WPS_GEOG}
export ME_PYTHON=${ME_PYTHON:-$ME_ROOT/venv/bin/python}
[ -x "$ME_PYTHON" ] || ME_PYTHON=$(command -v python3)
export ME_SCHEDULER=${ME_SCHEDULER:-local} ME_NPROCS=${ME_NPROCS:-16} ME_LANES=${ME_LANES:-4}
export ME_WALLTIME=${ME_WALLTIME:-24:00:00} ME_MPIRUN=${ME_MPIRUN:-mpirun}
export ME_PBS_RESOURCES=${ME_PBS_RESOURCES:-select=1:ncpus=$ME_NPROCS:mpiprocs=$ME_NPROCS}
export ME_SCHED_EXTRA=${ME_SCHED_EXTRA:-}
# The repository's Python code (downloads, scoring) reads and writes data here
export TWCR_DATA=$ME_ROOT/data
export OMP_NUM_THREADS=1
# cases.py is the single source of case names, dates and namelists
ME_CASES="$ME_PYTHON $ME_REPO/multievent/lib/cases.py"

me_log() { echo "[$(date '+%a %d %b %H:%M')] $*"; }
me_die() { echo "ERROR: $*" >&2; exit 1; }

# Lock directories (a case's run, a lane, an event's geogrid). mkdir is atomic, also on shared
# file systems. The owner writes "host pid" to <lock>/info and touches it every 5 min
# (me_heartbeat). A lock is live while that is younger than ME_LOCK_STALE_MIN minutes and, on the
# same host, the pid exists; a dead owner's lock is taken over. lib/cases.py (lock_live) reads
# them the same way.
export ME_LOCK_STALE_MIN=${ME_LOCK_STALE_MIN:-30}
me_lock_live() {   # lock dir
  local info=$1/info h p
  if [ ! -f "$info" ]; then   # being created this instant, or left by a crash
    [ -d "$1" ] && [ -n "$(find "$1" -maxdepth 0 -mmin -1 2>/dev/null)" ]; return
  fi
  [ -z "$(find "$info" -mmin +"$ME_LOCK_STALE_MIN" 2>/dev/null)" ] || return 1
  read -r h p < "$info" 2>/dev/null || return 1
  if [ "$h" = "$(hostname)" ]; then kill -0 "$p" 2>/dev/null || return 1; fi
  return 0
}
me_lock() {        # lock dir; returns 1 if a live owner holds it
  local L=$1 me
  me="$(hostname) $BASHPID"
  if ! mkdir "$L" 2>/dev/null; then
    me_lock_live "$L" && return 1
    echo "taking over the stale lock $L ($(cat "$L/info" 2>/dev/null || echo 'no owner'))" >&2
    rm -rf "$L"
    mkdir "$L" 2>/dev/null || return 1
    echo "$me" > "$L/info"
    sleep 2       # two takers of the same stale lock: the later rm removed the earlier one's info
    [ "$(cat "$L/info" 2>/dev/null)" = "$me" ] || return 1
    return 0
  fi
  echo "$me" > "$L/info"
}
me_unlock() {      # lock dir; only if this process owns it
  [ "$(cat "$1/info" 2>/dev/null)" = "$(hostname) $BASHPID" ] && rm -rf "$1"
  return 0
}
me_heartbeat() {   # lock dir: touch its info every 5 min in the background; sets ME_HEARTBEAT_PID
  local L=$1
  ( trap - EXIT; while sleep 300; do [ -f "$L/info" ] || exit 0; touch "$L/info"; done ) > /dev/null 2>&1 &
  ME_HEARTBEAT_PID=$!
}

Stand-ins for the WRF and WPS executables, used by tests/test_multievent.py to run the multi-event
pipeline (multievent/09-14) end to end in seconds. They read the same namelists and write files
with the same names, dimensions and variables the pipeline uses; they do no meteorology.
  geogrid.exe, metgrid.exe, util/rd_intermediate.exe   (WPS_DIR layout)
  main/real.exe, main/wrf.exe, run/                     (WRF_DIR layout)
  mpirun                                                drops "-np N"
wrf.exe stops early once at the model time in $FAKE_WRF_CRASH_AT (to test restarts), unless the
file $FAKE_WRF_CRASH_AT.done exists.

! Minimal stand-ins for the WRF framework pieces module_mp_thompson.F uses (no MPI, no namelist).
module module_wrf_error
  implicit none
  character(len=256) :: wrf_err_message
contains
  subroutine wrf_message(s)
    character(*), intent(in) :: s
    print '(a)', trim(s)
  end subroutine
  subroutine wrf_debug(l, s)
    integer, intent(in) :: l
    character(*), intent(in) :: s
  end subroutine
  subroutine wrf_error_fatal(s)
    character(*), intent(in) :: s
    print '(2a)', 'FATAL: ', trim(s)
    stop 1
  end subroutine
end module
module module_model_constants
  real, parameter :: RE_QC_BG = 2.49E-6, RE_QI_BG = 4.99E-6, RE_QS_BG = 9.99E-6
end module
module module_timing
contains
  subroutine start_timing
  end subroutine
  subroutine end_timing(s)
    character(*), intent(in) :: s
  end subroutine
end module
logical function wrf_dm_on_monitor()
  wrf_dm_on_monitor = .true.
end function
subroutine nl_get_force_read_thompson(id, v)
  integer, intent(in) :: id
  logical, intent(out) :: v
  v = .false.
end subroutine
subroutine nl_get_write_thompson_tables(id, v)
  integer, intent(in) :: id
  logical, intent(out) :: v
  v = .true.
end subroutine
subroutine nl_get_write_thompson_mp38table(id, v)
  integer, intent(in) :: id
  logical, intent(out) :: v
  v = .false.
end subroutine
module module_domain
end module
module module_dm
end module

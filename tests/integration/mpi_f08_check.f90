! RegCM5 needs a working mpi_f08. This repeats, on its own, the MPI pattern RegCM5 uses to
! hand out its initial fields (Main/mpplib/mod_mppparam.F90: glosplitw + do_distribute):
! gather each rank's 4-integer window into a pointer array, then MPI_Scatterv.
!   mpif90 -O2 mpi_f08_check.f90 -o f08check && mpirun -np 32 ./f08check   -> "MPI f08 OK"
! MPICH 4.0.3 + gfortran 11.4 (our HPC) fails it on every rank. scripts/setup/build_openmpi.sh
! runs it against the new Open MPI before rebuilding RegCM5 and stops if it fails.
program f08test
  use mpi_f08
  use iso_fortran_env, only: int32, real64
  implicit none
  type(MPI_Comm) :: comm
  integer(int32), dimension(4) :: window
  integer(int32), dimension(1), target :: ifake
  integer(int32), pointer, contiguous, dimension(:) :: windows, wincount, windispl
  real(real64), allocatable :: sendv(:), recvv(:)
  integer :: nproc, me, icpu, bad, badsum, n, nloc, k, slen
  character(len=MPI_MAX_LIBRARY_VERSION_STRING) :: lib
  call MPI_Init()
  call MPI_Comm_dup(MPI_COMM_WORLD, comm)
  call MPI_Comm_size(comm, nproc)
  call MPI_Comm_rank(comm, me)
  if (me == 0) then
    call MPI_Get_library_version(lib, slen)
    print '(a)', 'MPI library: '//trim(lib(1:min(slen,90)))
  end if
  window = [1 + me, 61 + me, 1, 34]               ! i1 i2 j1 j2: a 61 x 34 block like RegCM's
  if (me == 0) then
    allocate(windows(nproc*4))
  else
    windows => ifake
  end if
  allocate(wincount(nproc*4), windispl(nproc*4))
  call MPI_Gather(window, 4, MPI_INTEGER4, windows, 4, MPI_INTEGER4, 0, comm)
  nloc = 61*34
  if (me == 0) then
    bad = 0
    do icpu = 0, nproc-1
      if (any(windows(icpu*4+1:icpu*4+4) /= [1+icpu, 61+icpu, 1, 34])) bad = bad + 1
      wincount(icpu+1) = (windows(icpu*4+2)-windows(icpu*4+1)+1)*(windows(icpu*4+4)-windows(icpu*4+3)+1)
      windispl(icpu+1) = sum(wincount(1:icpu))
    end do
    print '(a,i0,a,i0,a,i0)', 'gather: wrong windows from ', bad, ' of ', nproc, ' ranks; min count ', minval(wincount(1:nproc))
    n = sum(wincount(1:nproc))
    allocate(sendv(n)); sendv = [(real(k, real64), k = 1, n)]
  else
    allocate(sendv(1))
  end if
  allocate(recvv(nloc))
  call MPI_Scatterv(sendv, wincount, windispl, MPI_REAL8, recvv, nloc, MPI_REAL8, 0, comm)
  bad = 0
  if (nint(recvv(1)) /= me*nloc + 1 .or. nint(recvv(nloc)) /= (me+1)*nloc) bad = 1
  call MPI_Reduce(bad, badsum, 1, MPI_INTEGER, MPI_SUM, 0, comm)
  if (me == 0) print '(a,i0,a,i0,a)', 'scatterv: wrong data on ', badsum, ' of ', nproc, ' ranks'
  if (me == 0 .and. badsum == 0) print '(a)', 'MPI f08 OK'
  call MPI_Finalize()
end program f08test

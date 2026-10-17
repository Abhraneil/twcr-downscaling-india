! One column through WRF 4.5 Thompson (mp_physics = 8, as WRF's microphysics_driver calls it)
! with rain and graupel present above and below the melting level.
program column
  use module_mp_thompson, only: thompson_init, mp_gt_driver
  implicit none
  integer, parameter :: nk = 40
  real, dimension(3,nk,3) :: qv, qc, qr, qi, qs, qg, ni, nr, th, pii, p, w, dz, hgt, refl, rec, rei, res
  real, dimension(3,3) :: rainnc, rainncv, snownc, snowncv, grnc, grncv, sr
  real :: t, z
  integer :: k
  do k = 1, nk
    z = 250. * (k - 0.5)
    hgt(:,k,:) = z; dz(:,k,:) = 250.
    p(:,k,:) = 100000. * exp(-z / 8000.)
    t = 300. - 0.0065 * z                       ! freezing level near 4 km
    pii(:,k,:) = (p(1,k,1) / 1.e5)**0.2857
    th(:,k,:) = t / pii(1,k,1)
    qv(:,k,:) = 0.9 * 0.622 * 611.2 * exp(17.67 * (t - 273.15) / (t - 29.65)) / p(1,k,1)
  end do
  qc = 1.e-3; qi = 0.; qs = 0.; ni = 0.
  qr = 8.e-3                                    ! heavy rain (8 g/kg)
  nr = 1.e5                                     ! rain number per kg
  qg = 4.e-3                                    ! graupel through the column
  w = 5.
  rainnc = 0.; rainncv = 0.; snownc = 0.; snowncv = 0.; grnc = 0.; grncv = 0.; sr = 0.
  call thompson_init(hgt=hgt, ids=1, ide=4, jds=1, jde=4, kds=1, kde=nk+1, &
                     ims=1, ime=3, jms=1, jme=3, kms=1, kme=nk, its=2, ite=2, jts=2, jte=2, kts=1, kte=nk)
  print '(a)', 'thompson_init done; one microphysics step:'
  call mp_gt_driver(qv=qv, qc=qc, qr=qr, qi=qi, qs=qs, qg=qg, ni=ni, nr=nr, th=th, pii=pii, p=p, &
                    w=w, dz=dz, dt_in=15., itimestep=1, rainnc=rainnc, rainncv=rainncv, &
                    snownc=snownc, snowncv=snowncv, graupelnc=grnc, graupelncv=grncv, sr=sr, &
                    refl_10cm=refl, diagflag=.false., ke_diag=nk, do_radar_ref=0, &
                    re_cloud=rec, re_ice=rei, re_snow=res, has_reqc=0, has_reqi=0, has_reqs=0, &
                    ids=1, ide=4, jds=1, jde=4, kds=1, kde=nk+1, ims=1, ime=3, jms=1, jme=3, &
                    kms=1, kme=nk, its=2, ite=2, jts=2, jte=2, kts=1, kte=nk)
  print '(a,f8.3,a)', 'step done: surface rain ', rainncv(2,2), ' mm'
end program

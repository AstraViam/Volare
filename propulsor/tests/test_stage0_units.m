function T = test_stage0_units()
%TEST_STAGE0_UNITS  Gate for DESIGN.md stage 0.
    T = [];
    U = units();

    T = chk(T, 'units() returns a struct', isstruct(U));

    % Exact-by-definition conversions. These are not approximations, so they
    % are checked to floating-point equality, not to a tolerance.
    T = chk(T, 'inch is exactly 0.0254 m', U.in2m == 0.0254);
    T = chk(T, 'nautical mile is exactly 1852 m', U.nm2m == 1852);
    T = chk(T, 'knot is 1852/3600 m/s', U.kn2ms == 1852/3600);
    T = chk(T, 'standard gravity is 9.80665', U.g == 9.80665);
    T = chk(T, 'foot is exactly 0.3048 m', U.ft2m == 0.3048);

    % Round trips must be exact to within one ulp of 1.
    pairs = {'in2m','m2in'; 'kn2ms','ms2kn'; 'deg2rad','rad2deg'; ...
             'rpm2rps','rps2rpm'; 'rpm2rads','rads2rpm'; 'nm2m','m2nm'};
    worst = 0;
    for k = 1:size(pairs, 1)
        worst = max(worst, abs(U.(pairs{k,1}) * U.(pairs{k,2}) - 1));
    end
    T = chk(T, 'every conversion round-trips to unity', worst < 1e-15, ...
            'worst round-trip error %.3e', worst);

    % The values the existing config.m depends on.
    T = chk(T, '21 in is 0.5334 m (max propeller diameter)', ...
            abs(21*U.in2m - 0.5334) < 1e-12);
    T = chk(T, '20 kn is 10.28889 m/s (design speed)', ...
            abs(20*U.kn2ms - 10.288888888888888) < 1e-12);
    T = chk(T, '2500 rpm is 261.7994 rad/s', ...
            abs(2500*U.rpm2rads - 261.79938779914943) < 1e-9);

    % config() must actually run. Before units.m existed it could not.
    err = '';
    try
        p = config();
        good = isstruct(p) && isfield(p, 'motor') && isfield(p, 'resistance');
    catch e
        good = false; err = e.message;
    end
    T = chk(T, 'config() runs and returns the expected sections', good, '%s', err);
end

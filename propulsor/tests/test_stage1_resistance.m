function T = test_stage1_resistance()
%TEST_STAGE1_RESISTANCE  Gate for DESIGN.md stage 1.
    T = [];
    U = units();
    p = config();

    Vd_kn = p.resistance.speed_kn(:);
    Rd_N  = p.resistance.R_total_N(:);

    % 1. The supplied points are data. Interpolation must return them exactly,
    %    not approximately, or the curve is a fit pretending to be data.
    r = resistance_model(Vd_kn * U.kn2ms, p);
    worst = max(abs(r.R_N(:) - Rd_N));
    T = chk(T, 'reproduces every supplied point exactly', worst == 0, ...
            'worst error %.3e N', worst);
    T = chk(T, 'supplied points are tagged "supplied"', ...
            all(strcmp(r.provenance(:), 'supplied')));

    % 2. The design point.
    d = resistance_model(20 * U.kn2ms, p);
    T = chk(T, 'R_T at 20 kn is 624 N', d.R_N == 624, 'got %.4f N', d.R_N);
    T = chk(T, 'P_E at 20 kn is 6.42 kW', abs(d.P_E_W/1e3 - 6.4203) < 1e-3, ...
            'got %.4f kW', d.P_E_W/1e3);

    % 3. pchip must not overshoot. A spline through these points would dip or
    %    bulge between them, and a resistance curve that is not monotonic in
    %    this speed range is not physical.
    s = resistance_model(linspace(0, 20, 601) * U.kn2ms, p);
    T = chk(T, 'monotonic non-decreasing over 0 to 20 kn', ...
            all(diff(s.R_N) >= -1e-12), ...
            'largest decrease %.3e N', min(diff(s.R_N)));
    T = chk(T, 'never overshoots the supplied maximum', ...
            max(s.R_N) <= max(Rd_N) + 1e-12, ...
            'peak %.4f N vs supplied max %.1f N', max(s.R_N), max(Rd_N));
    T = chk(T, 'resistance is never negative', all(s.R_N >= 0));

    % 3b. The interpolant must actually be pchip, not linear. Both reproduce
    %     the supplied points and both are monotonic here, so the checks above
    %     cannot tell them apart. What separates them is smoothness: linear
    %     interpolation puts a kink at every knot, and a resistance curve with
    %     a discontinuous slope will inject false gradients into any optimiser
    %     that differentiates through it.
    h = 1e-4;
    knots_kn = Vd_kn(2:end-1);          % interior knots only
    maxJump = 0;
    for k = 1:numel(knots_kn)
        v = knots_kn(k);
        f = @(x) getfield(resistance_model(x * U.kn2ms, p), 'R_N'); %#ok<GFLD>
        slopeL = (f(v - h)     - f(v - 2*h)) / h;
        slopeR = (f(v + 2*h)   - f(v + h))   / h;
        maxJump = max(maxJump, abs(slopeR - slopeL));
    end
    % pchip leaves about 1e-3 N/kn of numerical noise here; linear leaves ~15.
    T = chk(T, 'slope is continuous at every knot (pchip, not linear)', ...
            maxJump < 0.5, ...
            'largest slope jump %.4f N/kn; linear interpolation gives about 15', ...
            maxJump);

    % 3c. A direct value discriminator at a midpoint, as a second guard.
    mid125 = resistance_model(12.5 * U.kn2ms, p);
    linear125 = interp1(Vd_kn, Rd_N, 12.5, 'linear');
    T = chk(T, 'midpoint value is the pchip value, not the linear one', ...
            abs(mid125.R_N - 289.378) < 0.05 && abs(mid125.R_N - linear125) > 1, ...
            'got %.3f N; pchip is 289.378, linear is %.3f', mid125.R_N, linear125);

    % 4. Provenance must distinguish the three cases, every time.
    mid = resistance_model(12.5 * U.kn2ms, p);
    T = chk(T, 'a between-points query is tagged "interpolated"', ...
            strcmp(mid.provenance{1}, 'interpolated'));
    p2 = p; p2.resistance.allowExtrap = true;
    out = resistance_model(25 * U.kn2ms, p2);
    T = chk(T, 'beyond-range is tagged "extrapolated" and flagged', ...
            strcmp(out.provenance{1}, 'extrapolated') && out.anyExtrapolated);

    % 5. Extrapolation is blocked by default, so it cannot happen by accident.
    blocked = false;
    try
        resistance_model(25 * U.kn2ms, p);
    catch
        blocked = true;
    end
    T = chk(T, 'extrapolation is refused unless explicitly allowed', blocked);

    % 6. The 300 kg case must refuse rather than scale the 250 kg curve.
    refused = false; msg = '';
    try
        resistance_model(20 * U.kn2ms, p, 'worst');
    catch e
        refused = true; msg = e.message;
    end
    T = chk(T, '300 kg case refuses to fabricate data', ...
            refused && ~isempty(strfind(msg, 'unavailable')), '%s', msg);

    % 7. Bad input is rejected rather than silently producing a number.
    rejected = 0;
    try, resistance_model(-1, p); catch, rejected = rejected + 1; end
    try, resistance_model(NaN, p); catch, rejected = rejected + 1; end
    T = chk(T, 'negative and NaN speeds are rejected', rejected == 2);
end

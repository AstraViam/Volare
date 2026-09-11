function T = test_stage3_geometry()
%TEST_STAGE3_GEOMETRY  Gate for the blade geometry generator.
    T = [];
    p = config();
    C = p.propeller.common;
    d = struct('D_m', 0.50, 'Z', 3, 'P07_m', 26.5*0.0254);
    g = propeller_geometry(d, p);

    % --- the interface bem_rotor.m and crp_interaction.m consume ---------
    need = {'D','R','Z','c','dr','foc','r','r_hub','theta','toc','x'};
    missing = need(~cellfun(@(f) isfield(g, f), need));
    T = chk(T, 'supplies every field bem_rotor.m reads', isempty(missing), ...
            'missing: %s', strjoin(missing, ', '));
    sameLen = cellfun(@(f) numel(g.(f)), {'r','x','dr','c','theta','toc','foc'});
    T = chk(T, 'every per-station array has the same length', ...
            all(sameLen == sameLen(1)));

    % --- cell-centred stations, the property bem_rotor depends on --------
    T = chk(T, 'no station sits at the tip', all(g.x < 1), ...
            'outermost station at r/R = %.6f', max(g.x));
    T = chk(T, 'no station sits at the hub', all(g.r > g.r_hub), ...
            'innermost station at r/R = %.6f', min(g.x));
    T = chk(T, 'annulus widths sum to the blade span', ...
            abs(sum(g.dr) - (g.R - g.r_hub)) < 1e-12);
    T = chk(T, 'stations are the annulus centres', ...
            max(abs(g.r - 0.5*(g.edges(1:end-1) + g.edges(2:end)))) < 1e-15);
    T = chk(T, 'stations increase monotonically', all(diff(g.r) > 0));

    % --- expanded area ratio is hit exactly ------------------------------
    T = chk(T, 'achieved EAR equals the requested EAR', ...
            abs(g.EAR - C.EAR_ref) < 1e-12, ...
            'requested %.6f, achieved %.6f', C.EAR_ref, g.EAR);
    g2 = propeller_geometry(setfield(d, 'EAR', 0.95), p); %#ok<SFLD>
    T = chk(T, 'a different EAR is also hit exactly', abs(g2.EAR - 0.95) < 1e-12);
    T = chk(T, 'changing EAR scales chord without changing its shape', ...
            max(abs(g2.c/g2.chordScale - g.c/g.chordScale)) < 1e-12);

    % --- physical sanity --------------------------------------------------
    T = chk(T, 'chord is positive at every station', all(g.c > 0));
    T = chk(T, 'thickness respects the manufacturable floor', ...
            all(g.toc >= C.toc_min - 1e-15));
    T = chk(T, 'thickness falls from root to tip', all(diff(g.toc) < 0));
    T = chk(T, 'camber stays manufacturable', all(abs(g.foc) < 0.15));

    % For a near-constant pitch the geometric pitch angle must fall with
    % radius, because theta = atan(P / (2*pi*r)) and r is growing.
    T = chk(T, 'pitch angle decreases with radius', all(diff(g.theta) < 0), ...
            'theta went from %.2f to %.2f deg', rad2deg(g.theta(1)), rad2deg(g.theta(end)));
    T = chk(T, 'pitch angle is recovered from pitch and radius', ...
            max(abs(g.theta - atan2(g.P, 2*pi*g.r))) < 1e-15);
    T = chk(T, 'pitch at 0.7R matches what was asked for', ...
            abs(interp1(g.x, g.P, 0.70, 'pchip') - d.P07_m) < 5e-3, ...
            'got %.4f m, asked %.4f m', interp1(g.x, g.P, 0.70, 'pchip'), d.P07_m);

    % --- pchip must not overshoot ----------------------------------------
    % A cubic spline through the same control points can dip below the
    % smallest control value, which at the tip would mean negative chord.
    shp = C.shape;
    T = chk(T, 'chord never overshoots the control-point range', ...
            min(g.c/g.chordScale) >= min(shp.chord_val) - 1e-12 && ...
            max(g.c/g.chordScale) <= max(shp.chord_val) + 1e-12);

    % --- smoothness, the manufacturability constraint --------------------
    T = chk(T, 'chord gradient stays inside the smoothness limit', ...
            g.smoothOK, 'max |d(c/D)/d(r/R)| = %.3f against a %.1f limit', ...
            g.maxdcdx, C.dcdx_max);
    dTheta = diff(g.theta);
    T = chk(T, 'pitch angle has no abrupt step', ...
            max(abs(diff(dTheta))) < 0.02, ...
            'largest second difference %.4f rad', max(abs(diff(dTheta))));

    % --- refinement convergence ------------------------------------------
    % Doubling the station count must not move the integrated blade area,
    % or the discretisation is too coarse to trust.
    gA = propeller_geometry(setfield(d, 'nRadial', 24), p); %#ok<SFLD>
    gB = propeller_geometry(setfield(d, 'nRadial', 96), p); %#ok<SFLD>
    T = chk(T, 'blade area is insensitive to station count', ...
            abs(gA.A_expanded - gB.A_expanded)/gB.A_expanded < 1e-3, ...
            '24 stations %.6f m2, 96 stations %.6f m2', ...
            gA.A_expanded, gB.A_expanded);

    % --- skew and rake ----------------------------------------------------
    T = chk(T, 'skew and rake start from zero at the hub', ...
            g.skew_deg(1) < 1.0 && abs(g.rake_m(1)) < 2e-3);
    T = chk(T, 'skew grows monotonically toward the tip', all(diff(g.skew_deg) > 0));

    % --- invalid designs are refused -------------------------------------
    T = chk(T, 'a diameter over the 21 inch limit is refused', ...
            rejects(@() propeller_geometry(setfield(d,'D_m',0.60), p))); %#ok<SFLD>
    T = chk(T, 'a hub larger than the disc is refused', ...
            rejects(@() propeller_geometry(setfield(d,'hubRatio',1.2), p))); %#ok<SFLD>
    T = chk(T, 'a non-integer blade count is refused', ...
            rejects(@() propeller_geometry(setfield(d,'Z',3.5), p))); %#ok<SFLD>
    T = chk(T, 'negative pitch is refused', ...
            rejects(@() propeller_geometry(setfield(d,'P07_m',-1), p))); %#ok<SFLD>
    T = chk(T, 'a missing required variable is refused', ...
            rejects(@() propeller_geometry(struct('D_m',0.5,'Z',3), p)));

    % --- geometry feeds the polar without complaint ----------------------
    ok = true; msg = '';
    try
        [Cl, Cd] = hydrofoil_polar(deg2rad(4)*ones(size(g.r)), 2e6*ones(size(g.r)), ...
                                   g.toc, g.foc, zeros(size(g.r)), p);
        ok = all(isfinite(Cl)) && all(isfinite(Cd)) && all(Cd > 0);
    catch e
        ok = false; msg = e.message;
    end
    T = chk(T, 'the generated section shape feeds hydrofoil_polar cleanly', ok, '%s', msg);
end

% =========================================================================
function tf = rejects(fn)
    tf = false;
    try, fn(); catch, tf = true; end
end

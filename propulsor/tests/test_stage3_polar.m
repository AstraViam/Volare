function T = test_stage3_polar()
%TEST_STAGE3_POLAR  Gate for the section polar model.
%
%   The polar feeds every blade element on every solver iteration, so an
%   error here contaminates everything downstream. These checks pin the
%   analytical identities the model claims, the smoothness the BEM solver
%   depends on, and the interface bem_rotor.m actually calls.
    T = [];
    p   = config();
    toc_ = 0.08;
    foc  = 0.02;
    Re   = 3e6;

    % --- the interface bem_rotor.m uses ----------------------------------
    [Cl, Cd] = hydrofoil_polar(0, Re, toc_, foc, 0, p);
    T = chk(T, 'returns [Cl, Cd] from a six-argument call', ...
            isscalar(Cl) && isscalar(Cd) && isfinite(Cl) && isfinite(Cd));

    [~, ~, q] = hydrofoil_polar(0, Re, toc_, foc, 0, p);

    % --- analytical identities the docstring claims ----------------------
    T = chk(T, 'zero-lift angle is -2*(f/c), thin-aerofoil theory', ...
            abs(q.alpha0_rad - (-2*foc)) < 1e-14, ...
            'got %.6f, expected %.6f', q.alpha0_rad, -2*foc);
    T = chk(T, 'lift slope carries the (1 + 0.77 t/c) thickness correction', ...
            abs(q.Cl_alpha - 2*pi*(1 + 0.77*toc_)) < 1e-12);

    Cl0 = hydrofoil_polar(q.alpha0_rad, Re, toc_, foc, 0, p);
    T = chk(T, 'lift is exactly zero at the zero-lift angle', ...
            abs(Cl0) < 1e-12, 'got Cl = %.3e', Cl0);

    % --- symmetry: an uncambered section must be odd in alpha ------------
    a = deg2rad(linspace(-9, 9, 41));
    [Clp, Cdp, ip] = hydrofoil_polar( a, Re, toc_, 0, 0, p);
    [Clm, Cdm]     = hydrofoil_polar(-a, Re, toc_, 0, 0, p);
    T = chk(T, 'uncambered section: Cl is odd in alpha', ...
            max(abs(Clp + Clm)) < 1e-12, ...
            'worst |Cl(a) + Cl(-a)| = %.3e', max(abs(Clp + Clm)));

    % This check caught a real modelling error. With the drag bucket centred
    % on a single global Cl_design the minimum drag sat at a positive angle
    % even with zero camber, contradicting symmetry. It is now centred on the
    % section's own camber-derived design lift.
    T = chk(T, 'uncambered section: Cd is even in alpha', ...
            max(abs(Cdp - Cdm)) < 1e-12, ...
            'worst |Cd(a) - Cd(-a)| = %.3e', max(abs(Cdp - Cdm)));
    T = chk(T, 'uncambered section: drag minimum sits at zero incidence', ...
            max(abs(ip.Cl_bucket)) < 1e-14);
    T = chk(T, 'cambered section: drag bucket follows the camber', ...
            q.Cl_bucket > 0.2 && q.Cl_bucket < 0.35, ...
            'bucket centre Cl = %.4f', q.Cl_bucket);

    % --- drag sanity ------------------------------------------------------
    aw = deg2rad(-30:0.25:30);
    [~, Cdw, iw] = hydrofoil_polar(aw, Re, toc_, foc, 0, p);
    T = chk(T, 'drag is positive everywhere', all(Cdw > 0));
    T = chk(T, 'drag never falls below the friction floor', ...
            all(Cdw >= iw.Cd0 - 1e-15));

    [~, CdLo] = hydrofoil_polar(deg2rad(4), 1e5, toc_, foc, 0, p);
    [~, CdHi] = hydrofoil_polar(deg2rad(4), 1e7, toc_, foc, 0, p);
    T = chk(T, 'drag falls as Reynolds number rises', CdLo > CdHi, ...
            'Cd(1e5) = %.5f, Cd(1e7) = %.5f', CdLo, CdHi);

    % --- smoothness, by convergence not by threshold ---------------------
    % For a C1 curve max|second difference / da^2| tends to a finite limit as
    % the step shrinks. For a kinked curve it grows like 1/da, so a four-fold
    % refinement would roughly quadruple it. An absolute bound would only
    % measure how much curvature the blend has, which is a design choice.
    c1 = local_max_curvature(deg2rad(0.10),  Re, toc_, foc, p);
    c2 = local_max_curvature(deg2rad(0.025), Re, toc_, foc, p);
    ratio = c2 / max(c1, eps);
    T = chk(T, 'Cl curvature converges under refinement (C1, no kink)', ...
            ratio < 1.5, ...
            ['max|d2Cl| went %.1f -> %.1f on a 4x finer grid, ratio %.2f; ' ...
             'a kink would give about 4'], c1, c2, ratio);
    T = chk(T, 'Cl and Cd are finite over the whole swept range', ...
            all(isfinite(Cdw)) && all(isfinite(iw.Cl)));

    % --- the linear region really is linear ------------------------------
    Cl3 = hydrofoil_polar(deg2rad([-4 0 4]), Re, toc_, foc, 0, p);
    s1 = (Cl3(2) - Cl3(1)) / deg2rad(4);
    s2 = (Cl3(3) - Cl3(2)) / deg2rad(4);
    T = chk(T, 'lift is linear below stall', ...
            abs(s1 - s2) < 1e-10 && abs(s1 - q.Cl_alpha) < 1e-10);

    % --- ventilated branch ------------------------------------------------
    aV = deg2rad([0 4 8]);
    [ClV, CdV, iV] = hydrofoil_polar(aV, Re, toc_, foc, 1, p);
    slopeV = (ClV(3) - ClV(1)) / deg2rad(8);
    T = chk(T, 'fully ventilated lift slope is k_sc * pi/2 per radian', ...
            abs(slopeV - p.surfacePiercing.k_sc*pi/2) < 1e-12, ...
            'got %.6f, expected %.6f', slopeV, p.surfacePiercing.k_sc*pi/2);
    T = chk(T, 'ventilation costs roughly four times the lift slope', ...
            (q.Cl_alpha / slopeV) > 3.5 && (q.Cl_alpha / slopeV) < 4.6, ...
            'ratio %.2f', q.Cl_alpha / slopeV);
    T = chk(T, 'a ventilated section makes no lift at zero incidence', ...
            abs(ClV(1)) < 1e-14);
    T = chk(T, 'ventilated drag never falls below the cavity base drag', ...
            all(CdV >= p.surfacePiercing.Cd_base - 1e-15));
    T = chk(T, 'ventilation raises drag at a working incidence', ...
            CdV(3) > iV.Cd_wet(3), 'vent %.5f vs wetted %.5f', CdV(3), iV.Cd_wet(3));

    % Partial ventilation must sit between the two branches, since that is
    % physically what a part-wetted chord is.
    [ClH, CdH] = hydrofoil_polar(deg2rad(6), Re, toc_, foc, 0.5, p);
    [ClW, CdW] = hydrofoil_polar(deg2rad(6), Re, toc_, foc, 0.0, p);
    [ClF, CdF] = hydrofoil_polar(deg2rad(6), Re, toc_, foc, 1.0, p);
    T = chk(T, 'half-ventilated lift lies between wetted and ventilated', ...
            ClH < ClW && ClH > ClF);
    T = chk(T, 'half-ventilated drag lies between wetted and ventilated', ...
            CdH > CdW && CdH < CdF);
    T = chk(T, 'a ventilated fraction outside [0,1] is rejected', ...
            local_rejects(@() hydrofoil_polar(0, Re, toc_, foc, 1.5, p)));

    % --- per-station arrays, as bem_rotor passes them --------------------
    nSt = 5;
    aa   = deg2rad(linspace(2, 8, nSt));
    tocv = linspace(0.12, 0.05, nSt);
    focv = linspace(0.03, 0.01, nSt);
    ventv = linspace(0, 1, nSt);
    Rev  = linspace(1e6, 4e6, nSt);
    [Clv, Cdv] = hydrofoil_polar(aa, Rev, tocv, focv, ventv, p);
    T = chk(T, 'accepts per-station arrays for every argument', ...
            numel(Clv) == nSt && numel(Cdv) == nSt && all(isfinite(Clv)));
    [Cl1, Cd1] = hydrofoil_polar(aa(3), Rev(3), tocv(3), focv(3), ventv(3), p);
    T = chk(T, 'per-station result matches the equivalent scalar call', ...
            abs(Clv(3) - Cl1) < 1e-14 && abs(Cdv(3) - Cd1) < 1e-14);
    T = chk(T, 'a mismatched array length is rejected', ...
            local_rejects(@() hydrofoil_polar(aa, Re, [0.1 0.2], focv, 0, p)));

    % --- stall flag, Reynolds clamp, provenance --------------------------
    [~, ~, iB] = hydrofoil_polar(q.alpha0_rad + p.polar.alpha_stall_rad*0.5, ...
                                 Re, toc_, foc, 0, p);
    [~, ~, iA] = hydrofoil_polar(q.alpha0_rad + p.polar.alpha_stall_rad*2.0, ...
                                 Re, toc_, foc, 0, p);
    T = chk(T, 'stall flag is clear below the stall angle', ~iB.stalled);
    T = chk(T, 'stall flag is set well past the stall angle', iA.stalled);

    [~, ~, iR] = hydrofoil_polar(deg2rad(4), p.polar.Re_min/10, toc_, foc, 0, p);
    T = chk(T, 'a Reynolds number below the correlation range is flagged', ...
            iR.ReClamped && iR.Re_used == p.polar.Re_min);
    T = chk(T, 'the model declares itself provisional', ...
            ~isempty(strfind(upper(q.source), 'PROVISIONAL')));

    % --- external path and bad geometry ----------------------------------
    p2 = p; p2.polar.useExternal = true; p2.polar.external = [];
    T = chk(T, 'external mode refuses to run with no data supplied', ...
            local_rejects(@() hydrofoil_polar(0, Re, toc_, foc, 0, p2)));
    T = chk(T, 'zero thickness is rejected', ...
            local_rejects(@() hydrofoil_polar(0, Re, 0, foc, 0, p)));
    T = chk(T, 'unmanufacturable camber is rejected', ...
            local_rejects(@() hydrofoil_polar(0, Re, toc_, 0.9, 0, p)));
end

% =========================================================================
function c = local_max_curvature(da, Re, toc_, foc, p)
    aa = deg2rad(-25):da:deg2rad(25);
    Cl = hydrofoil_polar(aa, Re, toc_, foc, 0, p);
    c = max(abs(diff(Cl, 2) / da^2));
end

% =========================================================================
function tf = local_rejects(fn)
%LOCAL_REJECTS  True if the call raises, which is what it should do.
    tf = false;
    try
        fn();
    catch
        tf = true;
    end
end

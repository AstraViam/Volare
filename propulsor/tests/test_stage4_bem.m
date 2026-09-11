function T = test_stage4_bem()
%TEST_STAGE4_BEM  Gate for the single-rotor blade element momentum solver.
%
%   This is the honesty checkpoint of DESIGN.md. If the single-rotor BEM does
%   not behave, nothing downstream means anything, and the optimiser will
%   converge happily on a number that is confidently wrong.
    T = [];
    p = config(); U = units();
    rho = p.water.rho;
    g = propeller_geometry(struct('D_m',0.50,'Z',3,'P07_m',26.5*U.in2m), p);
    Va = 20*U.kn2ms * (1 - p.hull.w);
    ns = numel(g.r);
    flow = struct('Va', Va*ones(1,ns), 'Vt', zeros(1,ns), ...
                  'duty', ones(1,ns), 'vent', zeros(1,ns));

    nList = [14 18 22 26 30 34 38];
    J = zeros(size(nList)); KT = J; KQ = J; eta = J; Tn = J; conv = false(size(nList));
    for k = 1:numel(nList)
        r = bem_rotor(g, flow, struct('n', nList(k)), p);
        J(k)  = Va / (nList(k) * g.D);
        KT(k) = r.T / (rho * nList(k)^2 * g.D^4);
        KQ(k) = r.Q / (rho * nList(k)^2 * g.D^5);
        eta(k) = J(k)*KT(k) / (2*pi*KQ(k));
        Tn(k) = r.T;
        conv(k) = r.converged;
    end

    T = chk(T, 'the solver converges at every advance ratio', all(conv));
    T = chk(T, 'thrust and torque are finite everywhere', ...
            all(isfinite(KT)) && all(isfinite(KQ)));

    % --- the trends any propeller must show ------------------------------
    % The sweep runs over increasing rotation rate, and J = Va/(nD), so the
    % arrays are ordered by DECREASING J. Sort into ascending J before
    % asserting the trend, or the assertion reads backwards.
    [Jsorted, ix] = sort(J);
    T = chk(T, 'KT falls as advance ratio rises', all(diff(KT(ix)) < 0), ...
            'J = %s gives KT = %s', sprintf('%.3f ', Jsorted), sprintf('%.4f ', KT(ix)));
    T = chk(T, 'KQ falls as advance ratio rises', all(diff(KQ(ix)) < 0), ...
            'KQ = %s', sprintf('%.5f ', KQ(ix)));
    T = chk(T, 'thrust rises with rotation rate', all(diff(Tn) > 0));
    T = chk(T, 'efficiency stays in (0, 1)', all(eta > 0 & eta < 1), ...
            'eta = %s', sprintf('%.4f ', eta));

    % --- the momentum-theory bound, the strongest check available --------
    % No rotor can beat the actuator-disc ideal at its own thrust loading.
    % A BEM result above this line means the induction is wrong, not that a
    % remarkable propeller has been found.
    A = pi * g.R^2;
    beaten = false(size(nList));
    for k = 1:numel(nList)
        CT_load = Tn(k) / (0.5 * rho * A * Va^2);
        eta_ideal = 2 / (1 + sqrt(1 + CT_load));
        beaten(k) = eta(k) > eta_ideal + 1e-9;
    end
    T = chk(T, 'efficiency never exceeds the actuator-disc ideal', ~any(beaten), ...
            '%d of %d points beat momentum theory', sum(beaten), numel(nList));

    % --- efficiency must respond correctly to pitch ----------------------
    % At this very light thrust loading a higher-pitch rotor turns slower and
    % works at a better advance ratio, so efficiency must improve with pitch.
    T_req = 624 / (1 - p.hull.t);
    etaPD = zeros(1,4); PDs = [1.0 1.4 1.8 2.2];
    for k = 1:numel(PDs)
        gk = propeller_geometry(struct('D_m',0.50,'Z',3,'P07_m',PDs(k)*0.50), p);
        nk = local_match_thrust(gk, flow, T_req, p);
        rk = bem_rotor(gk, flow, struct('n', nk), p);
        Jk = Va/(nk*gk.D);
        etaPD(k) = Jk*(rk.T/(rho*nk^2*gk.D^4)) / (2*pi*(rk.Q/(rho*nk^2*gk.D^5)));
    end
    T = chk(T, 'efficiency improves with pitch at this light loading', ...
            all(diff(etaPD) > 0), 'eta = %s for P/D = %s', ...
            sprintf('%.4f ', etaPD), sprintf('%.1f ', PDs));

    % --- a zero-thrust advance ratio exists ------------------------------
    rHi = bem_rotor(g, flow, struct('n', 11), p);
    T = chk(T, 'thrust falls toward zero at high advance ratio', ...
            rHi.T < Tn(1), 'T = %.1f N at n = 11 rev/s', rHi.T);

    % --- refinement --------------------------------------------------------
    g96 = propeller_geometry(struct('D_m',0.50,'Z',3,'P07_m',26.5*U.in2m, ...
                                    'nRadial',96), p);
    f96 = struct('Va',Va*ones(1,96),'Vt',zeros(1,96),'duty',ones(1,96),'vent',zeros(1,96));
    r24 = bem_rotor(g,   flow, struct('n',22), p);
    r96 = bem_rotor(g96, f96,  struct('n',22), p);
    T = chk(T, 'thrust is insensitive to radial station count', ...
            abs(r24.T - r96.T)/r96.T < 0.03, ...
            '24 stations %.1f N, 96 stations %.1f N, %.2f%% apart', ...
            r24.T, r96.T, 100*abs(r24.T-r96.T)/r96.T);

    % --- Prandtl loss behaves ---------------------------------------------
    phi = atan2(Va, 2*pi*g.r*22);
    F = prandtl_loss(g.r, g.R, g.r_hub, phi, g.Z);
    T = chk(T, 'tip/hub loss lies in (0, 1]', all(F > 0) && all(F <= 1));
    T = chk(T, 'tip loss bites hardest at the tip', F(end) < F(round(ns/2)), ...
            'F_tip = %.4f, F_mid = %.4f', F(end), F(round(ns/2)));
    T = chk(T, 'loss relaxes toward 1 mid-span', F(round(ns/2)) > 0.8);
    T = chk(T, 'more blades means less tip loss', ...
            prandtl_loss(g.r(end), g.R, g.r_hub, phi(end), 6) > F(end));
    T = chk(T, 'an invalid hub radius is refused', ...
            rejects(@() prandtl_loss(g.r, g.R, g.R*2, phi, g.Z)));

    % --- ventilation costs thrust, as it must ----------------------------
    fv = flow; fv.vent = ones(1,ns);
    rw = bem_rotor(g, flow, struct('n',26), p);
    rv = bem_rotor(g, fv,   struct('n',26), p);
    T = chk(T, 'a fully ventilated rotor makes less thrust than a wetted one', ...
            rv.T < rw.T, 'ventilated %.1f N vs wetted %.1f N', rv.T, rw.T);

    % --- partial immersion cuts thrust -----------------------------------
    fd = flow; fd.duty = 0.5*ones(1,ns);
    rd = bem_rotor(g, fd, struct('n',26), p);
    T = chk(T, 'half immersion roughly halves thrust', ...
            rd.T < rw.T && rd.T > 0.3*rw.T, ...
            'half-immersed %.1f N vs fully immersed %.1f N', rd.T, rw.T);
end

% =========================================================================
function n = local_match_thrust(g, flow, T_req, p)
    lo = 3; hi = 60;
    for it = 1:50
        mid = 0.5*(lo+hi);
        r = bem_rotor(g, flow, struct('n', mid), p);
        if r.T < T_req, lo = mid; else, hi = mid; end
    end
    n = 0.5*(lo+hi);
end

% =========================================================================
function tf = rejects(fn)
    tf = false;
    try, fn(); catch, tf = true; end
end

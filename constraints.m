function [c, labels, info] = constraints(E, params)
%CONSTRAINTS  All inequality constraints, in the convention c <= 0 is feasible.
%
%   Every constraint is NORMALISED by its own limit so that the entries are
%   dimensionless and comparable, which is what allows a single penalty scale to
%   be meaningful across quantities as different as newtons and pascals.
%
%   Constraints that are satisfied BY CONSTRUCTION are listed here anyway, with
%   their realised margin, so that nothing is enforced silently:
%     - required thrust: satisfied exactly by the speed solve in evaluate_design
%     - diameter, pitch, hub, shaft angle: enforced by the design-space bounds
%     - blade count: enforced by enumeration

U = units();
c = [];  labels = {};

    function add(name, value, limit, sense)
        % sense = 'max' -> value <= limit ; 'min' -> value >= limit
        if strcmp(sense,'max')
            c(end+1) = (value - limit)/max(abs(limit),1e-9);
        else
            c(end+1) = (limit - value)/max(abs(limit),1e-9);
        end
        labels{end+1} = name;
    end

% ---- geometric ----------------------------------------------------------
add('D_front <= D_max',        E.gF.D,               params.propeller.common.D_max_m, 'max');
add('D_rear <= D_max',         E.gR.D,               params.propeller.common.D_max_m, 'max');
add('d_hub < D_front',         E.d.d_hub_m,          0.85*E.gF.D,                     'max');
add('d_hub < D_rear',          E.d.d_hub_m,          0.85*E.gR.D,                     'max');
% Hub ratio bounds. These were configured in config.m but were not previously
% enforced anywhere, which let the optimiser return a hub occupying nearly 40%
% of the diameter - numerically attractive, because a small disk is cheap in
% profile drag, but a large real efficiency penalty, structurally awkward, and
% outside the range over which blade element theory has any claim to validity.
add('hub ratio front <= max',  E.gF.hubRatio, params.propeller.common.hubRatio_max, 'max');
add('hub ratio rear  <= max',  E.gR.hubRatio, params.propeller.common.hubRatio_max, 'max');
add('hub ratio front >= min',  E.gF.hubRatio, params.propeller.common.hubRatio_min, 'min');
add('hub ratio rear  >= min',  E.gR.hubRatio, params.propeller.common.hubRatio_min, 'min');
add('|beta_shaft| <= 5 deg',   abs(E.d.beta_deg),    params.propeller.common.beta_shaft_deg_max, 'max');

% ---- motor --------------------------------------------------------------
add('n_motor <= n_max',        E.motor.n_rpm,        params.motor.n_max_rpm,  'max');
add('Q_motor <= Q_max',        E.motor.Q_Nm,         params.motor.Q_max_Nm,   'max');
add('P_shaft <= P_continuous', E.motor.P_shaft_W,    params.motor.P_nominal_W,'max');
add('P_motor <= MEBC cap',     E.motor.P_shaft_W,    params.competition.P_motor_cap_W, 'max');
if params.motor.enforceCurrentLimit
    add('I <= I_limit',        E.motor.I_A,          params.motor.I_limit_A,  'max');
end

% ---- gearbox ------------------------------------------------------------
add('gear ratio front <= max', E.gearbox.ratio_front, params.gearbox.ratio_max, 'max');
add('gear ratio rear  <= max', E.gearbox.ratio_rear,  params.gearbox.ratio_max, 'max');
add('gear ratio front >= min', E.gearbox.ratio_front, params.gearbox.ratio_min, 'min');
add('gear ratio rear  >= min', E.gearbox.ratio_rear,  params.gearbox.ratio_min, 'min');

% ---- structural ---------------------------------------------------------
add('front blade stress',      E.struct.front.sigma_combined_Pa, E.struct.front.sigma_allow_Pa, 'max');
add('rear blade stress',       E.struct.rear.sigma_combined_Pa,  E.struct.rear.sigma_allow_Pa,  'max');

% ---- cavitation / ventilation ------------------------------------------
isSP = strcmpi(E.arch,'surfacepiercing') || strcmpi(E.arch,'sp');
if ~isSP
    add('front cavitation margin', params.cavitation.sigma_margin, E.cav.front.minMargin, 'max');
    add('rear cavitation margin',  params.cavitation.sigma_margin, E.cav.rear.minMargin,  'max');
    add('front Burrill loading',   E.cav.front.tau_c, E.cav.front.tau_allow, 'max');
    add('rear Burrill loading',    E.cav.rear.tau_c,  E.cav.rear.tau_allow,  'max');
else
    % For a ventilated blade the governing requirement is that the rotor is
    % ACTUALLY in the fully ventilated regime; the partially ventilated
    % transition is where thrust breakdown and violent load fluctuation occur.
    add('front Fn_D >= vent threshold', E.vent.front.FnD, params.surfacePiercing.FnD_vent_threshold, 'min');
    add('rear  Fn_D >= vent threshold', E.vent.rear.FnD,  params.surfacePiercing.FnD_vent_threshold, 'min');
    add('immersion ratio <= 0.85',      E.imm.front.I_T,  0.85, 'max');
end

% ---- physical sanity ----------------------------------------------------
add('efficiency <= 1',         E.eta.eta_D,          1.0,  'max');
add('efficiency >= 0',         E.eta.eta_D,          0.01, 'min');

info.violations = {};
for k = 1:numel(c)
    if c(k) > 1e-6
        info.violations{end+1} = sprintf('%s (violated by %.1f%%)', labels{k}, 100*c(k));
    end
end
info.nViolated  = numel(info.violations);
info.maxViolation = max([0 c]);
info.feasible = info.nViolated == 0;

% Constraints satisfied by construction, reported for transparency
info.byConstruction = { ...
    sprintf('required thrust met exactly: %.1f N (residual %.2e)', E.T_req_N, E.thrustSolve.residual), ...
    sprintf('blade counts fixed by enumeration: Z_front = %d, Z_rear = %d', E.Zf, E.Zr), ...
    'diameter, pitch, hub and shaft angle held inside the configured bounds by the design-space limits'};
end

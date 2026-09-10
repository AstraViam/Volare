function m = motor_model(n_rpm, Q_Nm, params)
%MOTOR_MODEL  Axial-flux PMSM envelope and operating point.
%
%   m = MOTOR_MODEL(n_rpm, Q_Nm, params)   evaluate an operating point
%   m = MOTOR_MODEL(n_rpm, [],   params)   query the envelope only
%
%   THE ENVELOPE
%     Three hard limits act at once. The available torque at any speed is
%     whichever of them binds first:
%
%       Q_available(n) = min( Q_max , P_cap / omega )        [N*m]
%       P_available(n) = min( P_cap , omega * Q_max )        [W]
%       n <= n_max
%
%     with omega = n * 2*pi/60. Below the corner speed the motor is torque
%     limited and power climbs with speed; above it the motor is power limited
%     and torque falls as P_cap/omega. The corner is where the two curves
%     cross:
%
%       n_corner = P_cap / (Q_max * 2*pi/60)
%
%     For the current numbers (25 kW, 100 N*m) that is 2387.3 rpm, which sits
%     just below the 2500 rpm speed limit. So the usable envelope has a short
%     constant-power region at the top, and at 2500 rpm the motor can only
%     deliver 95.5 N*m, not 100.
%
%   THE 25 kW CAP
%     P_cap is an absolute ceiling for every duration. Peak equals continuous;
%     there is no overload mode. The datasheet's 42 kW peak is recorded in
%     params.motor.P_max_spec_W and deliberately NOT used, because the team
%     has capped the motor at 25 kW. It was unreachable regardless: 42 kW
%     needs 160.4 N*m at 2500 rpm, or 4010.7 rpm at 100 N*m, each 60 percent
%     beyond a hard limit. MOTOR_CONSISTENCY_REPORT below prints this.
%
%   EFFICIENCY
%     A constant 0.95 for now, an ASSUMPTION. When a dyno map arrives, set
%     params.motor.etaMap to a function handle eta = f(rpm, Q) and this
%     function will use it with no other change. Efficiency at a corner of the
%     envelope is typically well below the peak figure a datasheet quotes, so
%     the constant is optimistic at low load.
%
%   Returns a struct with, for each input speed:
%     .n_rpm .omega_rads .Q_Nm .P_mech_W
%     .Q_limit_Nm .P_limit_W .n_corner_rpm
%     .limitedBy      'torque' | 'power' | 'speed'
%     .feasible       logical
%     .violations     cellstr, empty when feasible
%     .eta_motor .P_elec_W .I_A .withinCurrentLimit
%     .headroom_Q .headroom_P    fraction of the limit still unused
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

    U = units();

    if nargin < 3
        error('motor_model:args', 'usage: motor_model(n_rpm, Q_Nm, params)');
    end
    mo = params.motor;

    % The enforced ceiling. Fall back to the nominal rating if an older config
    % predates the cap, but never to the 42 kW spec.
    if isfield(mo, 'P_cap_W')
        P_cap = mo.P_cap_W;
    else
        P_cap = mo.P_nominal_W;
    end

    Q_max = mo.Q_max_Nm;
    n_max = mo.n_max_rpm;

    n_rpm = n_rpm(:).';                       % row, so outputs broadcast
    if any(~isfinite(n_rpm)) || any(n_rpm < 0)
        error('motor_model:speed', 'n_rpm must be finite and non-negative');
    end

    omega = n_rpm * U.rpm2rads;               % rad/s

    % --- envelope -------------------------------------------------------
    n_corner_rpm = P_cap / (Q_max * U.rpm2rads);

    % At standstill the power limit imposes no torque limit, so guard the
    % division rather than producing Inf.
    Q_limit = repmat(Q_max, size(omega));
    nz = omega > 0;
    Q_limit(nz) = min(Q_max, P_cap ./ omega(nz));

    P_limit = min(P_cap, omega * Q_max);

    limitedBy = cell(size(n_rpm));
    for k = 1:numel(n_rpm)
        if n_rpm(k) > n_max + 1e-9
            limitedBy{k} = 'speed';
        elseif n_rpm(k) <= n_corner_rpm
            limitedBy{k} = 'torque';
        else
            limitedBy{k} = 'power';
        end
    end

    m.n_rpm        = n_rpm;
    m.omega_rads   = omega;
    m.Q_limit_Nm   = Q_limit;
    m.P_limit_W    = P_limit;
    m.n_corner_rpm = n_corner_rpm;
    m.n_max_rpm    = n_max;
    m.Q_max_Nm     = Q_max;
    m.P_cap_W      = P_cap;
    m.limitedBy    = limitedBy;

    if isempty(Q_Nm)
        m.isEnvelopeOnly = true;
        return;                                % envelope query, done
    end
    m.isEnvelopeOnly = false;

    % --- operating point ------------------------------------------------
    Q_Nm = Q_Nm(:).';
    if numel(Q_Nm) == 1 && numel(n_rpm) > 1
        Q_Nm = repmat(Q_Nm, size(n_rpm));
    end
    if numel(Q_Nm) ~= numel(n_rpm)
        error('motor_model:size', ...
              'Q_Nm has %d elements but n_rpm has %d', numel(Q_Nm), numel(n_rpm));
    end
    if any(~isfinite(Q_Nm)) || any(Q_Nm < 0)
        error('motor_model:torque', 'Q_Nm must be finite and non-negative');
    end

    P_mech = omega .* Q_Nm;                    % W

    % --- feasibility, one reason per violated limit ----------------------
    tol = 1e-9;
    feasible   = true(size(n_rpm));
    violations = cell(size(n_rpm));
    for k = 1:numel(n_rpm)
        v = {};
        if n_rpm(k) > n_max + tol
            v{end+1} = sprintf('speed %.1f rpm exceeds %.0f rpm', n_rpm(k), n_max); %#ok<AGROW>
        end
        if Q_Nm(k) > Q_max + tol
            v{end+1} = sprintf('torque %.2f Nm exceeds %.1f Nm', Q_Nm(k), Q_max); %#ok<AGROW>
        end
        if P_mech(k) > P_cap + tol
            v{end+1} = sprintf('power %.0f W exceeds the %.0f W cap', P_mech(k), P_cap); %#ok<AGROW>
        end
        violations{k} = v;
        feasible(k) = isempty(v);
    end

    % --- efficiency and electrical --------------------------------------
    if isfield(mo, 'etaMap') && ~isempty(mo.etaMap)
        eta = arrayfun(@(nn, qq) mo.etaMap(nn, qq), n_rpm, Q_Nm);
        etaSource = 'map';
    else
        eta = repmat(mo.eta, size(n_rpm));
        etaSource = 'constant (ASSUMPTION)';
    end
    if any(eta <= 0 | eta > 1)
        error('motor_model:eta', 'motor efficiency outside (0, 1]');
    end

    P_elec = P_mech ./ eta;

    etaC = 1.0;
    if isfield(params, 'controller') && isfield(params.controller, 'enable') ...
            && params.controller.enable
        etaC = params.controller.eta;
        P_elec = P_elec ./ etaC;
    end

    I_A = P_elec / mo.V_system_V;

    withinI = true(size(I_A));
    if isfield(mo, 'enforceCurrentLimit') && mo.enforceCurrentLimit ...
            && isfield(mo, 'I_limit_A')
        withinI = I_A <= mo.I_limit_A + tol;
        for k = 1:numel(I_A)
            if ~withinI(k)
                violations{k}{end+1} = sprintf('current %.1f A exceeds %.1f A', ...
                                               I_A(k), mo.I_limit_A);
                feasible(k) = false;
            end
        end
    end

    m.Q_Nm               = Q_Nm;
    m.P_mech_W           = P_mech;
    m.feasible           = feasible;
    m.violations         = violations;
    m.eta_motor          = eta;
    m.eta_source         = etaSource;
    m.eta_controller     = etaC;
    m.P_elec_W           = P_elec;
    m.I_A                = I_A;
    m.withinCurrentLimit = withinI;
    m.headroom_Q         = 1 - Q_Nm ./ max(Q_limit, eps);
    m.headroom_P         = 1 - P_mech ./ max(P_limit, eps);
end

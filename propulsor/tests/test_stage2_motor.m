function T = test_stage2_motor()
%TEST_STAGE2_MOTOR  Gate for DESIGN.md stage 2.
%
%   The governing requirement: 25 kW is an absolute ceiling for every
%   duration. Peak equals continuous. Nothing may exceed it.
    T = [];
    U = units();
    p = config();
    cap  = p.motor.P_cap_W;
    Qmax = p.motor.Q_max_Nm;
    nmax = p.motor.n_max_rpm;

    T = chk(T, 'the enforced cap is 25 kW', cap == 25e3, 'got %g W', cap);
    T = chk(T, 'the 42 kW datasheet peak is recorded but not used', ...
            p.motor.P_max_spec_W == 42e3 && ~p.motor.usePeakSpec);

    % 1. Corner speed, where torque limiting hands over to power limiting.
    e = motor_model(1000, [], p);
    corner = cap / (Qmax * U.rpm2rads);
    T = chk(T, 'corner speed is 2387.3 rpm', abs(e.n_corner_rpm - corner) < 1e-9 ...
            && abs(corner - 2387.3242) < 1e-3, 'got %.4f rpm', e.n_corner_rpm);

    % 2. The cap holds across the whole speed range. This is the check that
    %    matters most; a single point above 25 kW is a specification breach.
    n = linspace(0, nmax, 5001);
    env = motor_model(n, [], p);
    T = chk(T, 'P_limit never exceeds the cap at any speed', ...
            max(env.P_limit_W) <= cap + 1e-6, ...
            'max %.4f W over 0 to %d rpm', max(env.P_limit_W), nmax);
    T = chk(T, 'Q_limit never exceeds the torque limit at any speed', ...
            max(env.Q_limit_Nm) <= Qmax + 1e-9, ...
            'max %.4f Nm', max(env.Q_limit_Nm));

    % 3. Envelope shape either side of the corner.
    below = motor_model(corner * 0.5, [], p);
    above = motor_model(nmax, [], p);
    T = chk(T, 'below the corner the motor is torque limited', ...
            strcmp(below.limitedBy{1}, 'torque') && abs(below.Q_limit_Nm - Qmax) < 1e-9);
    T = chk(T, 'above the corner the motor is power limited', ...
            strcmp(above.limitedBy{1}, 'power') && abs(above.P_limit_W - cap) < 1e-6);
    T = chk(T, 'at 2500 rpm only 95.49 Nm is available, not 100', ...
            abs(above.Q_limit_Nm - 95.4930) < 1e-3, 'got %.4f Nm', above.Q_limit_Nm);

    % 4. Every limit is enforced independently.
    over_n = motor_model(nmax + 1, 50, p);
    over_Q = motor_model(1000, Qmax + 1, p);
    over_P = motor_model(2400, 100, p);          % 25.13 kW, just over the cap
    T = chk(T, 'over-speed is rejected', ~over_n.feasible);
    T = chk(T, 'over-torque is rejected', ~over_Q.feasible);
    T = chk(T, 'over-power is rejected even when Q and n are each legal', ...
            ~over_P.feasible && over_P.Q_Nm <= Qmax && over_P.n_rpm <= nmax, ...
            'P = %.1f W at %.0f rpm and %.1f Nm', ...
            over_P.P_mech_W, over_P.n_rpm, over_P.Q_Nm);
    T = chk(T, 'a violation states its reason', ~isempty(over_P.violations{1}));

    % 5. A legal point produces a sane electrical chain.
    g = motor_model(2000, 47.9, p);
    T = chk(T, 'a legal point is feasible', g.feasible);
    T = chk(T, 'P_mech equals omega times Q', ...
            abs(g.P_mech_W - g.omega_rads*g.Q_Nm) < 1e-9);
    T = chk(T, 'electrical power exceeds mechanical power', g.P_elec_W > g.P_mech_W);
    T = chk(T, 'current is P_elec over bus voltage', ...
            abs(g.I_A - g.P_elec_W/p.motor.V_system_V) < 1e-9);
    T = chk(T, 'efficiency is flagged as an assumption until a map exists', ...
            ~isempty(strfind(g.eta_source, 'ASSUMPTION')));

    % 6. Exactly at each limit must be accepted, not rejected by float noise.
    at_corner = motor_model(corner, Qmax, p);
    T = chk(T, 'the corner point itself is feasible', at_corner.feasible, ...
            'P = %.6f W against a %.0f W cap', at_corner.P_mech_W, cap);

    % 7. The contradiction report states the numbers rather than asserting.
    txt = motor_consistency_report(p);
    T = chk(T, 'consistency report gives 160.4 Nm and 4010.7 rpm', ...
            ~isempty(strfind(txt, '160.4')) && ~isempty(strfind(txt, '4010.7')));
    T = chk(T, 'consistency report names the enforced cap', ...
            ~isempty(strfind(txt, '25 kW absolute cap')));
end

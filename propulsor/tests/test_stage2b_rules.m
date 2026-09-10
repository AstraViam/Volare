function T = test_stage2b_rules()
%TEST_STAGE2B_RULES  The 2027 competition limits, as configured.
%
%   Every number here is quoted from the Technical Rules 2027.1. If the
%   Organiser reissues the rules, these tests are what catches a stale config.
%   See docs/reference/RULES_CHANGES_2026_to_2027.md.
    T = [];
    p = config();
    R = p.rules;

    T = chk(T, 'config is written against rules edition 2027.1', ...
            strcmp(R.edition, '2027.1'), 'got %s', R.edition);

    % ENERGY_REQ_188 v1.1 - the cap the whole propulsion design turns on.
    T = chk(T, 'ENERGY_REQ_188: 25 kW instantaneous cap', R.P_motor_max_W == 25e3);
    T = chk(T, 'the motor cap is attributed to the rule, not to a preference', ...
            strcmp(p.motor.P_cap_rule, 'ENERGY_REQ_188 v1.1'));
    T = chk(T, 'motor P_cap matches the rule limit', ...
            p.motor.P_cap_W == R.P_motor_max_W);
    T = chk(T, 'the forbidden peak-power mode stays off', ~p.motor.usePeakSpec);

    % Unchanged 2026 -> 2027, and load-bearing.
    T = chk(T, 'ENERGY_REQ_48: 250 kg excluding hulls', R.mass_max_kg == 250);
    T = chk(T, 'ENERGY_REQ_48: hulls are 65 kg', R.hull_mass_kg == 65);
    T = chk(T, 'ENERGY_REQ_7: 10 kWh stored energy', R.E_stored_max_Wh == 10e3);
    T = chk(T, 'ENERGY_REQ_28: 4 m2 of solar', R.solar_area_max_m2 == 4);
    T = chk(T, 'ENERGY_REQ_37: 3 knot minimum speed', R.speed_min_kn == 3);
    T = chk(T, 'ENERGY_REQ_154: 40 deg steering each side', R.steering_min_deg == 40);

    % New or revised in 2027.
    T = chk(T, 'ENERGY_REQ_186 v1.1: hydrofoils are banned', ~R.hydrofoilsAllowed);
    T = chk(T, 'ENERGY_REQ_194: motor seat takes 200% of max torque', ...
            R.motorSeatTorqueFactor == 2.0);
    T = chk(T, 'ENERGY_REQ_194 gives a 200 Nm seat case', ...
            R.motorSeatTorqueFactor * p.motor.Q_max_Nm == 200, ...
            'got %.1f Nm', R.motorSeatTorqueFactor * p.motor.Q_max_Nm);
    T = chk(T, 'ENERGY_REQ_195: 220 x 111 x 80 mm sensor volume', ...
            isequal(R.powerSensorVolume_mm(:).', [220 111 80]));
    T = chk(T, 'ENERGY_REQ_185 v1.1: monitor volume at least 40 cm above beams', ...
            R.monitorHeightMin_m == 0.40);
    T = chk(T, 'ENERGY_REQ_184 v1.1: interface budget raised to 35 W', ...
            R.monitorInterface_W == 35);
    T = chk(T, 'ENERGY_REQ_93 v1.1: 60 C on any reachable surface', ...
            R.surface_temp_max_C == 60);
    T = chk(T, 'ENERGY_REQ_193: LFP required from August 2028 is recorded', ...
            strcmp(R.lfpRequiredFrom, '2028-08-01'));

    % The design speed must be legal.
    T = chk(T, 'the 20 kn design point clears the 3 kn minimum', ...
            p.vessel.V_design_kn >= R.speed_min_kn);

    % An operating point at the rule limit must be legal; a hair above must not.
    %
    % The speed matters. Below the 2387.3 rpm corner the motor is torque
    % limited, so 25 kW is not reachable there at all: at 2000 rpm it would
    % need 119.4 Nm against a 100 Nm limit. Test at a speed above the corner,
    % where the power cap is genuinely the binding constraint.
    U = units();
    n = 2450;                                   % above the corner
    Q_at_cap = R.P_motor_max_W / (n * U.rpm2rads);
    T = chk(T, 'at 2450 rpm the 25 kW point is within the torque limit', ...
            Q_at_cap <= p.motor.Q_max_Nm, ...
            'needs %.2f Nm against a %.0f Nm limit', Q_at_cap, p.motor.Q_max_Nm);

    at   = motor_model(n, Q_at_cap,          p);
    over = motor_model(n, Q_at_cap * 1.0001, p);
    T = chk(T, 'an operating point exactly at 25 kW is legal', at.feasible, ...
            'P = %.6f W, violations: %s', at.P_mech_W, strjoin(at.violations{1}, '; '));
    T = chk(T, 'a point 0.01 percent above 25 kW is rejected', ~over.feasible, ...
            'P = %.3f W', over.P_mech_W);

    % And below the corner, 25 kW must be unreachable, because the torque
    % limit binds first. This is the physical consequence of the cap.
    lowQ = R.P_motor_max_W / (2000 * U.rpm2rads);
    low  = motor_model(2000, lowQ, p);
    T = chk(T, 'below the corner, 25 kW is correctly unreachable', ~low.feasible, ...
            'would need %.1f Nm at 2000 rpm', lowQ);
end

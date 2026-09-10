function txt = motor_consistency_report(params, fid)
%MOTOR_CONSISTENCY_REPORT  State the motor specification contradiction plainly.
%
%   txt = MOTOR_CONSISTENCY_REPORT(params)        return the text
%   MOTOR_CONSISTENCY_REPORT(params, 1)           also print to stdout
%
%   Spec section 1 requires that the supplied numbers are never silently
%   altered and that any inconsistency is reported in the output. This does
%   that, and is called from print_assumptions.m and postprocess.m.
%
%   The 25 kW ceiling is not a team preference. It is ENERGY_REQ_188 v1.1 of
%   the 2027 Technical Rules, which caps the sum of instantaneous power over
%   all motors and forbids peaks. A design that breaches it is not a worse
%   design, it is an illegal one.

    U  = units();
    mo = params.motor;
    if nargin < 2, fid = []; end

    Q  = mo.Q_max_Nm;
    nM = mo.n_max_rpm;
    cap = mo.P_cap_W;
    spec = mo.P_max_spec_W;

    P_at_corner = nM * U.rpm2rads * Q;
    n_for_cap   = cap / (Q * U.rpm2rads);
    Q_for_spec  = spec / (nM * U.rpm2rads);
    n_for_spec  = spec / (Q * U.rpm2rads);

    L = {};
    L{end+1} = 'MOTOR SPECIFICATION CONSISTENCY';
    L{end+1} = '--------------------------------';
    L{end+1} = sprintf('  supplied : %.0f kW nominal, %.0f kW peak spec, %.0f Nm, %.0f rpm', ...
                       mo.P_nominal_W/1e3, spec/1e3, Q, nM);
    L{end+1} = sprintf('  enforced : %.0f kW absolute cap, all durations', cap/1e3);
    L{end+1} = sprintf('             rule  : %s', mo.P_cap_rule);
    L{end+1} =         '             The 2027 rules cap INSTANTANEOUS power summed over';
    L{end+1} =         '             all motors, and forbid peaks explicitly. The 2026';
    L{end+1} =         '             wording capped nominal power, which was looser.';
    L{end+1} = '';
    L{end+1} = sprintf('  Power available at the two hard limits together:');
    L{end+1} = sprintf('    %.0f rpm x %.0f Nm = %.2f kW', nM, Q, P_at_corner/1e3);
    L{end+1} = sprintf('    so %.0f Nm and %.0f rpm alone permit only %.2f kW.', ...
                       Q, nM, P_at_corner/1e3);
    L{end+1} = '';
    L{end+1} = sprintf('  The %.0f kW datasheet peak is UNREACHABLE inside those limits:', spec/1e3);
    L{end+1} = sprintf('    %.0f kW at %.0f rpm would need %.1f Nm  (%.0f%% over the %.0f Nm limit)', ...
                       spec/1e3, nM, Q_for_spec, 100*(Q_for_spec/Q - 1), Q);
    L{end+1} = sprintf('    %.0f kW at %.0f Nm would need %.1f rpm  (%.0f%% over the %.0f rpm limit)', ...
                       spec/1e3, Q, n_for_spec, 100*(n_for_spec/nM - 1), nM);
    L{end+1} = '';
    L{end+1} = '  ACTION: put this to the motor supplier. The likeliest readings are';
    L{end+1} = '  that 42 kW is a short peak at a higher speed or a higher bus voltage';
    L{end+1} = '  than 96 V, or that 100 Nm is continuous rather than absolute.';
    L{end+1} = '';
    L{end+1} = sprintf('  Not used by this tool either way: the enforced cap is %.0f kW.', cap/1e3);
    L{end+1} = sprintf('  Corner speed at the cap: %.1f rpm. Above it the motor is power', n_for_cap);
    L{end+1} = sprintf('  limited, so at %.0f rpm only %.1f Nm is available, not %.0f.', ...
                       nM, cap/(nM*U.rpm2rads), Q);

    txt = strjoin(L, sprintf('\n'));
    if ~isempty(fid)
        fprintf(fid, '%s\n', txt);
    end
end

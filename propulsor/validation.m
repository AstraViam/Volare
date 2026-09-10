function V = validation(params, fid)
%VALIDATION  Compare the analytical model against supplied reference data.
%
%   The only reference data available is a previous MODEL-SCALE CFD run:
%       J = 0.60, n = 4220 rpm, V_A = 3.40 m/s, Q = 1.06 N.m, P ~ 460 W
%   These are NOT full-scale design inputs and are used only as a check.
%
%   NOTE: no thrust and no diameter were supplied. The diameter is IMPLIED by
%   the other three numbers through J = V_A/(n*D), and the implied value is
%   reported below for confirmation, because if it does not match the propeller
%   that was actually run in CFD then one of the four supplied numbers is wrong
%   and the comparison is meaningless.
%
%   Anything that cannot be computed from the supplied data is reported as
%   "Not available - requires CFD/experimental validation". Nothing is invented.

if nargin < 2, fid = 1; end
U = units();  c = params.validation.cfd;

n_rps = c.n_rpm*U.rpm2rps;
D_implied = c.V_A_ms/(n_rps*c.J);
P_from_Q  = 2*pi*n_rps*c.Q_Nm;

% Use the SUPPLIED diameter when there is one; fall back to the value implied
% by J, n and V_A otherwise, and say which was used.
if ~isempty(c.D_m)
    D_ref = c.D_m;  V.D_source = 'supplied';
else
    D_ref = D_implied;  V.D_source = 'implied by J, n and V_A';
end

V.D_implied_m  = D_implied;
V.D_used_m     = D_ref;
V.P_from_Q_W   = P_from_Q;
V.P_supplied_W = c.P_W;
V.P_consistency_pct = 100*(P_from_Q - c.P_W)/c.P_W;
V.KQ = c.Q_Nm/(c.rho*n_rps^2*D_ref^5);

% K_T and eta_0 are computable ONLY if a thrust was supplied. They are computed
% when it is, and reported as unavailable when it is not - never invented.
if ~isempty(c.T_N)
    V.KT   = c.T_N/(c.rho*n_rps^2*D_ref^4);
    V.eta0 = c.J*V.KT/(2*pi*V.KQ);
else
    V.KT   = NaN;
    V.eta0 = NaN;
end

V.flags = {};
if isempty(c.D_m)
    V.flags{end+1} = sprintf(['Propeller diameter was NOT supplied. J, n and V_A imply D = %.1f mm. ', ...
        'CONFIRM THIS. If the CFD model was not a %.0f mm propeller then J, n or V_A is ', ...
        'inconsistent and this reference set cannot be used for validation.'], ...
        D_implied*1000, D_implied*1000);
end
if abs(V.P_consistency_pct) > 5
    V.flags{end+1} = sprintf('Supplied power %.0f W differs by %.1f%% from 2*pi*n*Q = %.0f W.', ...
        c.P_W, V.P_consistency_pct, P_from_Q);
end
if isempty(c.T_N)
    V.flags{end+1} = 'CFD thrust NOT supplied: K_T, eta_0 and the thrust error cannot be computed. Not available - requires CFD/experimental validation.';
end
if ~isempty(c.D_m) && abs(c.D_m - D_implied)/D_implied > 0.02
    V.flags{end+1} = sprintf(['SUPPLIED diameter %.1f mm disagrees with the %.1f mm implied by J, n and ', ...
        'V_A by %.1f%%. The reference set is internally inconsistent; coefficients below use the ', ...
        'supplied diameter.'], c.D_m*1000, D_implied*1000, 100*abs(c.D_m-D_implied)/D_implied);
end

% ---- run the model at the reference condition, if the geometry is known ----
V.modelRun = false;
V.note = ['To run the analytical model against this point, populate ', ...
          'params.validation.geometry with the CFD propeller geometry (D, Z, P/D, ', ...
          'EAR, chord/thickness/camber distributions). Without that geometry the ', ...
          'comparison cannot be made and is NOT faked.'];
if isfield(params.validation,'geometry') && ~isempty(params.validation.geometry)
    gv = propeller_geometry(params.validation.geometry, params);
    pv = params;  pv.water.rho = c.rho;
    flow = struct('Va', c.V_A_ms, 'Vt', 0, 'duty', 1, 'vent', 0);
    r = bem_rotor(gv, flow, struct('n', n_rps), pv);
    V.modelRun = true;
    V.model.T = r.T;  V.model.Q = r.Q;  V.model.P = r.P;
    V.model.KT = r.KT;  V.model.KQ = r.KQ;  V.model.eta0 = r.eta0;
    V.error.Q_pct = 100*(r.Q - c.Q_Nm)/c.Q_Nm;
    V.error.P_pct = 100*(r.P - c.P_W)/c.P_W;
    if ~isempty(c.T_N)
        V.error.T_pct = 100*(r.T - c.T_N)/c.T_N;
    else
        V.error.T_pct = NaN;
    end
end

print_validation(V, c, fid);
end

function print_validation(V, c, fid)
fprintf(fid,'\n-------------------------------------------------------------------------\n');
fprintf(fid,' VALIDATION AGAINST SUPPLIED REFERENCE DATA\n');
fprintf(fid,'-------------------------------------------------------------------------\n');
fprintf(fid,' Reference (MODEL SCALE - not a design input):\n');
fprintf(fid,'   J        = %.3f\n', c.J);
fprintf(fid,'   n        = %.0f rpm\n', c.n_rpm);
fprintf(fid,'   V_A      = %.2f m/s\n', c.V_A_ms);
fprintf(fid,'   Q        = %.3f N.m\n', c.Q_Nm);
fprintf(fid,'   P        = %.0f W\n', c.P_W);
fprintf(fid,'   T        = %s\n', tern(isempty(c.T_N),'NOT SUPPLIED', sprintf('%.2f N', c.T_N)));
fprintf(fid,' Derived:\n');
fprintf(fid,'   D implied by J,n,V_A = %.1f mm\n', V.D_implied_m*1000);
fprintf(fid,'   D used for coefficients = %.1f mm (%s)\n', V.D_used_m*1000, V.D_source);
fprintf(fid,'   2*pi*n*Q             = %.0f W  (%.1f%% vs supplied P)\n', V.P_from_Q_W, V.P_consistency_pct);
fprintf(fid,'   K_Q                  = %.4f\n', V.KQ);
if isfinite(V.KT)
    fprintf(fid,'   K_T                  = %.4f\n', V.KT);
    fprintf(fid,'   eta_0                = %.4f\n', V.eta0);
else
    fprintf(fid,'   K_T                  = Not available - requires CFD/experimental validation\n');
    fprintf(fid,'   eta_0                = Not available - requires CFD/experimental validation\n');
end
if V.modelRun
    fprintf(fid,' Model vs CFD:\n');
    fprintf(fid,'   Q  model %.3f N.m  vs CFD %.3f N.m   error %+.1f%%\n', V.model.Q, c.Q_Nm, V.error.Q_pct);
    fprintf(fid,'   P  model %.0f W    vs CFD %.0f W     error %+.1f%%\n', V.model.P, c.P_W, V.error.P_pct);
    if isfinite(V.error.T_pct)
        fprintf(fid,'   T  model %.2f N    vs CFD %.2f N     error %+.1f%%\n', V.model.T, c.T_N, V.error.T_pct);
        fprintf(fid,'   K_T model %.4f     vs CFD %.4f\n', V.model.KT, V.KT);
        fprintf(fid,'   eta_0 model %.4f   vs CFD %.4f\n', V.model.eta0, V.eta0);
    else
        fprintf(fid,'   T, K_T, eta_0: Not available - CFD thrust was not supplied.\n');
    end
else
    fprintf(fid,' Model comparison NOT RUN: %s\n', V.note);
end
for k = 1:numel(V.flags)
    fprintf(fid,' !! %s\n', V.flags{k});
end
fprintf(fid,'-------------------------------------------------------------------------\n');
end

function s = tern(cond, a, b)
if cond, s = a; else, s = b; end
end

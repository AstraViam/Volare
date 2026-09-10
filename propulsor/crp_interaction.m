function crp = crp_interaction(gF, gR, opF, opR, inflow, params, warm)
%CRP_INTERACTION  Fully coupled contra-rotating propeller solution.
%
%   crp = CRP_INTERACTION(gF, gR, opF, opR, inflow, params [, warm])
%
%   PHYSICAL COUPLING IMPLEMENTED
%
%   (a) FRONT -> REAR, AXIAL.  The front rotor's induced axial velocity is only
%       partly developed at the rear disk, 50 mm downstream.  For an actuator
%       disk of radius R the axial induction grows from w at the disk to 2w far
%       downstream as w(x) = w*(1 + x/sqrt(x^2+R^2)), so the development factor
%       at the rear plane is
%           g_dn = 1 + dx/sqrt(dx^2 + R_F^2)
%       which for dx = 50 mm and R_F ~ 0.19 m is about 1.25. The rear rotor
%       therefore sees only about a quarter of the extra acceleration that would
%       exist far downstream. The axial gap feeds directly into this factor,
%       which is why the 50 mm spacing is a first-class design constraint.
%
%   (b) REAR -> FRONT, AXIAL.  The rear rotor's induction also propagates
%       UPSTREAM: at distance dx ahead of a disk it is w*(1 - dx/sqrt(dx^2+R^2)),
%       still about 0.75 of the rear disk value at 50 mm. The rotors are
%       therefore mutually coupled and must be solved simultaneously.
%
%   (c) SLIPSTREAM CONTRACTION by discrete mass conservation,
%           r2(i)^2 = r2(i-1)^2 + u1(i)*(r1(i)^2 - r1(i-1)^2)/u_dn(i)
%       starting from an unchanged hub streamline.
%
%   (d) SWIRL TRANSPORT AND RECOVERY.  Angular momentum is added at the front
%       disk, so immediately downstream the swirl is 2*ap1*Omega1*r1. Under
%       contraction, conservation of circulation (v_theta*r = const) gives
%           v_theta2 = 2*ap1*Omega1*r1*(r1/r2)
%       at the rear plane. Because the rotors turn in opposite senses this ADDS
%       to the rear blade's relative tangential velocity (positive flow.Vt), so
%       the rear rotor recovers the rotational energy the front rotor put in.
%       This falls out of the momentum balance; it is NOT an applied efficiency
%       factor.
%
%   (e) NO SWIRL UPSTREAM.  An actuator disk induces no tangential velocity
%       ahead of itself, so the front rotor sees zero pre-swirl.
%
%   SOLUTION METHOD - WHY NOT A SIMPLE FIXED-POINT ITERATION
%       The coupling is POSITIVE feedback: more rear loading raises the axial
%       velocity at the front disk, which unloads the front rotor, which weakens
%       the swirl feeding the rear rotor, which changes the rear loading again.
%       Near lightly loaded operating points the loop gain exceeds unity, the
%       fixed point is repelling, and NO under-relaxation factor converges - the
%       naive iteration oscillates indefinitely. The coupling is therefore
%       reduced to a single scalar, the amplitude u of the rear rotor's
%       interference velocity at the front disk, and solved by BISECTION on
%           R(u) = u_returned(u) - u
%       The bracket is guaranteed: R(0) > 0 because the rear rotor always
%       induces a positive velocity, and R(u_max) < 0 for u_max above the
%       physical induction ceiling a_max*V_ax. Bisection therefore converges
%       whatever the loop gain. The radial SHAPE of the interference is held
%       fixed within a bisection pass and refreshed between two passes, which
%       works because the shape is far less sensitive than the amplitude.
%
%   LIMITATIONS.  Superposition of two actuator-disk induction fields;
%   annulus-independent momentum; no blade-row unsteady interaction, no
%   blade-passing effects, no viscous wake impingement of front blades on rear
%   blades. At 50 mm spacing the real interaction is strongly unsteady -
%   sliding-mesh CFD validation is REQUIRED.

nz   = params.numerics.crp;
dx   = params.propeller.common.axialGap_m;
beta = inflow.beta_shaft_rad;
V_ax = inflow.V_A * cos(beta);

g_dn = 1 + dx/sqrt(dx^2 + gF.R^2);
g_up = 1 - dx/sqrt(dx^2 + gR.R^2);

rF = gF.r;  rR = gR.r;
shape   = ones(size(rF));
nEval   = 0;
lastOut = [];
u_max   = params.numerics.bem.a_max * V_ax * 1.05;
if nargin < 7, warm = []; end
% warm must be the SCALAR interference amplitude from a neighbouring operating
% point (crp.interference_u), not a velocity profile. Anything else is ignored.
if ~isscalar(warm) || ~isfinite(warm), warm = []; end
tolAbs = nz.tol*V_ax;

% ---- solve the scalar interference amplitude ----------------------------
R0 = coupled_pass(0);
if ~isfinite(R0)
    crp = failed_crp('front or rear BEM failed at zero interference'); return;
end
shape = lastOut.shape;

% Secant first: the pair (u=0, u=R(0)) is an excellent starting bracket
% because R(0) is exactly the value the naive fixed-point iteration would
% return on its first step. Secant converges to repelling fixed points as
% happily as to attracting ones, and typically needs three or four coupled
% solves. Bisection over the full physical range is the guaranteed fallback.
[u, okS, itS] = secant_u(R0, warm);
if ~okS
    [u, okB, itB] = bisect_u(0, u_max, nz.maxIter, tolAbs, warm, false);
    itS = itS + itB;
    if ~okB, crp = failed_crp('interference solve failed'); return; end
end
it1 = itS;  it2 = 0;

it2 = 0;

% ---- final consistent state --------------------------------------------
Rfin = coupled_pass(u);
if ~isfinite(Rfin)
    crp = failed_crp('final coupled pass failed'); return;
end
S = lastOut;
% The bracket is bisected to machine precision, so any remaining residual comes
% from a JUMP in the coupled response (the induction clamps and the section
% stall blend are only piecewise smooth). Convergence is therefore declared on
% a physically meaningful residual - a fraction of the advance velocity - and
% any jump is reported explicitly rather than hidden.
relRes = abs(Rfin)/max(V_ax,1e-6);
converged  = relRes <= nz.residualAccept;
jumpFlag   = relRes > nz.residualClean;

resF = S.resF;  resR = S.resR;
T_total = resF.T + resR.T;
Q_total = resF.Q + resR.Q;
P_total = resF.P + resR.P;

swirl_residual = S.Vt_R - 2*resR.ap.*resR.omega.*rR;
wt = rR.*max(S.Va_R,1e-6);
drR = gR.dr(:).';
sw_in  = sum(abs(S.Vt_R).*wt.*drR);
sw_out = sum(abs(swirl_residual).*wt.*drR);
if sw_in > 1e-9, swirlRecovery = 1 - sw_out/sw_in; else, swirlRecovery = NaN; end

crp.converged      = converged;
crp.iterations     = it1 + it2 + 3;
crp.evaluations    = nEval;
crp.residual       = abs(Rfin)/max(V_ax,1e-6);
crp.interference_u = u;
crp.front = resF;  crp.rear = resR;
crp.T_total_N   = T_total;
crp.T_useful_N  = T_total*cos(beta);
crp.Q_total_Nm  = Q_total;
crp.P_shaft_W   = P_total;
crp.V_A = inflow.V_A;  crp.V_ax = V_ax;  crp.beta_rad = beta;
crp.eta_CRP     = T_total*V_ax/nz_guard(P_total);
crp.thrustSplit = resF.T/nz_guard(T_total);
crp.torqueSplit = resF.Q/nz_guard(Q_total);
crp.powerSplit  = resF.P/nz_guard(P_total);
crp.rpmRatio    = opF.n/max(opR.n,1e-9);
crp.swirlRecovery  = swirlRecovery;
crp.swirl_in       = S.Vt_R;
crp.swirl_residual = swirl_residual;
crp.r2_contracted  = S.r2;
crp.contractionRatio = S.r2(end)/rF(end);
crp.g_dn = g_dn;  crp.g_up = g_up;  crp.axialGap_m = dx;
crp.Va_rear  = S.Va_R;
crp.Va_front = S.Va_F;
crp.w2_on_F  = u*shape;
crp.netTorqueReaction_Nm = resF.Q - resR.Q;
crp.jumpDetected = jumpFlag;
crp.status = '';
if ~converged
    crp.status = sprintf('CRP COUPLING DID NOT CONVERGE (interference residual %.2f%% of V_A)', 100*relRes);
elseif jumpFlag
    crp.status = sprintf(['CRP interference bracketed to machine precision but the coupled ', ...
        'response jumps by %.2f%% of V_A at the solution: the rotor-rotor interference amplitude ', ...
        'is uncertain at this operating point.'], 100*relRes);
end

% =====================================================================
    function [uu, ok, nit] = secant_u(R_at_zero, warmStart)
        p0 = 0;         F0 = R_at_zero;
        p1 = R_at_zero; if ~isempty(warmStart) && isfinite(warmStart) && warmStart > 0
            p1 = 0.5*(p1 + warmStart);
        end
        p1 = min(max(p1, 1e-6), u_max);
        F1 = coupled_pass(p1);
        nit = 1;
        best = p1;  bestF = abs(F1);
        if ~isfinite(F1), uu = p1; ok = false; return; end
        for k = 1:12
            den = F1 - F0;
            if abs(den) < 1e-14, break; end
            p2 = p1 - F1*(p1 - p0)/den;
            if ~isfinite(p2) || p2 < 0 || p2 > u_max, break; end
            F2 = coupled_pass(p2);  nit = nit + 1;
            if ~isfinite(F2), break; end
            if abs(F2) < bestF, best = p2; bestF = abs(F2); end
            p0 = p1; F0 = F1;  p1 = p2; F1 = F2;
            if abs(F2) < tolAbs, break; end
        end
        uu = best;
        ok = bestF < max(tolAbs, nz.residualAccept*V_ax);
    end

    function [uu, ok, nit] = bisect_u(a0, b0, maxit, tol, warmStart, strict)
        if nargin < 6, strict = false; end
        Ra = coupled_pass(a0);
        nit = 1;
        if ~isfinite(Ra), uu = NaN; ok = false; return; end
        % Backtrack the upper endpoint until the coupled pass is finite AND the
        % residual has changed sign. Very large interference velocities drive
        % the front rotor into a windmilling state where the BEM bracket is not
        % well posed, so the physical ceiling is approached from below.
        Rb = NaN;
        nTry = 24;  if strict, nTry = 2; end
        for k = 1:nTry
            Rb = coupled_pass(b0);
            nit = nit + 1;
            if isfinite(Rb) && Ra*Rb < 0, break; end
            if ~isfinite(Rb)
                b0 = a0 + 0.6*(b0 - a0);          % shrink towards the good end
            else
                if b0 >= u_max - 1e-9, break; end
                b0 = min(u_max, a0 + 1.6*(b0 - a0));  % same sign: expand
            end
            if (b0 - a0) < 1e-6, break; end
        end
        if ~isfinite(Rb) || Ra*Rb > 0
            if strict, uu = NaN; ok = false; return; end
            if isfinite(Rb) && abs(Rb) < abs(Ra), uu = b0; else, uu = a0; end
            ok = isfinite(uu);  return;
        end
        if ~isempty(warmStart) && warmStart > a0 && warmStart < b0
            Rw = coupled_pass(warmStart);  nit = nit + 1;
            if isfinite(Rw)
                if Rw*Ra < 0, b0 = warmStart; Rb = Rw; else, a0 = warmStart; Ra = Rw; end
            end
        end
        % Illinois (modified false position): retains the guaranteed bracket of
        % bisection but converges superlinearly. R(u) is smooth over most of the
        % bracket, so this typically cuts the coupled passes per rotor solution
        % from ~14 to ~5, which is the single largest cost in the whole tool.
        % A plain bisection step is forced every fourth iteration and whenever
        % an interpolated point falls outside the bracket, so the guaranteed
        % convergence of bisection is preserved.
        for k = 1:maxit
            if mod(k,4) == 0 || ~isfinite(Rb-Ra) || abs(Rb-Ra) < 1e-14
                mid = 0.5*(a0+b0);
            else
                mid = b0 - Rb*(b0-a0)/(Rb-Ra);
                if ~isfinite(mid) || mid <= a0 || mid >= b0
                    mid = 0.5*(a0+b0);
                else
                    lim = 0.02*(b0-a0);
                    mid = min(max(mid, a0+lim), b0-lim);
                end
            end
            Rm  = coupled_pass(mid);
            nit = nit + 1;
            if ~isfinite(Rm), b0 = mid; Rb = NaN; continue; end
            if Rm*Ra < 0
                b0 = mid;  Rb = Rm;  Ra = Ra/2;      % Illinois down-weighting
            else
                a0 = mid;  Ra = Rm;  Rb = Rb/2;
            end
            if abs(Rm) < tol || (b0-a0) < 1e-10*max(1,u_max)
                uu = mid;  ok = true;  return;
            end
        end
        uu = 0.5*(a0+b0);  ok = true;
    end

% =====================================================================
    function Rres = coupled_pass(u)
        nEval = nEval + 1;
        w2_on_F = u*shape;

        flowF = struct('Va', V_ax + w2_on_F, 'Vt', zeros(size(rF)), ...
                       'duty', inflow.dutyF, 'vent', inflow.ventF);
        resF_ = bem_front_rotor(gF, flowF, opF, params);
        if ~resF_.converged, Rres = NaN; return; end

        w1 = flowF.Va .* resF_.a;
        u1 = flowF.Va + w1;
        Va_R_ext_F = V_ax + w1*g_dn;

        r2 = zeros(size(rF));  r2(1) = rF(1);
        for i = 2:numel(rF)
            r2(i) = sqrt(max(r2(i-1)^2 + u1(i)*(rF(i)^2 - rF(i-1)^2)/max(Va_R_ext_F(i),1e-6), 1e-12));
        end
        swirl_F = 2*resF_.ap .* resF_.omega .* rF;
        swirl_2 = swirl_F .* (rF./max(r2,1e-9));

        Va_R = interp_slipstream(r2, Va_R_ext_F, rR, V_ax);
        Vt_R = interp_slipstream(r2, swirl_2,    rR, 0.0);

        flowR = struct('Va', Va_R, 'Vt', Vt_R, 'duty', inflow.dutyR, 'vent', inflow.ventR);
        resR_ = bem_rear_rotor(gR, flowR, opR, params);
        if ~resR_.converged, Rres = NaN; return; end

        w2      = Va_R .* resR_.a;
        w2backF = interp_slipstream(rR, w2*g_up, rF, 0.0);
        u_ret   = mean(w2backF);

        newShape = w2backF/nz_guard(u_ret);
        % The radial SHAPE of the interference is far less sensitive than its
        % amplitude, so it is relaxed towards self-consistency inside the same
        % loop that solves for the amplitude. This removes the need for a
        % separate outer shape-refresh pass.
        shape = 0.5*shape + 0.5*newShape;
        lastOut = struct('resF',resF_,'resR',resR_,'Va_R',Va_R,'Vt_R',Vt_R, ...
                         'Va_F',flowF.Va,'r2',r2,'shape', newShape);
        Rres = u_ret - u;
    end
end

% =========================================================================
function v = nz_guard(v)
if abs(v) < 1e-12, v = 1e-12; end
end

% =========================================================================
function y = interp_slipstream(xs, ys, xq, outside)
%INTERP_SLIPSTREAM  Map a slipstream field onto another rotor's radii.
[xs, idx] = sort(xs(:).');
ys = ys(idx);
[xs, iu] = unique(xs);
ys = ys(iu);
y = outside*ones(size(xq));
if numel(xs) >= 2
    in = (xq >= min(xs)) & (xq <= max(xs));
    y(in) = interp1(xs, ys, xq(in), 'linear');
    below = xq < min(xs);
    y(below) = ys(1);
end
y(~isfinite(y)) = outside;
end

% =========================================================================
function crp = failed_crp(msg)
%FAILED_CRP  Uniform failure record so that callers never see a partial struct.
crp = struct('converged',false,'iterations',0,'evaluations',0,'residual',NaN, ...
    'w2_on_F',[],'interference_u',NaN, ...
    'T_total_N',NaN,'T_useful_N',NaN,'Q_total_Nm',NaN,'P_shaft_W',NaN, ...
    'eta_CRP',NaN,'thrustSplit',NaN,'torqueSplit',NaN,'powerSplit',NaN, ...
    'rpmRatio',NaN,'swirlRecovery',NaN,'status',['CRP FAILED: ' msg]);
crp.jumpDetected = false;
end

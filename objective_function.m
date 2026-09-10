function [J, E, brk] = objective_function(x, Zf, Zr, arch, params, ds, opts)
%OBJECTIVE_FUNCTION  Scalar objective for the optimiser.
%
%   PRIMARY OBJECTIVE: electrical energy per nautical mile at the design speed,
%   in Wh/nm. This is NOT propeller efficiency. A design with slightly lower
%   hydrodynamic efficiency wins if it puts the motor in a better place, needs a
%   simpler gearbox, or cuts blade stress and ventilation losses.
%
%   J = E_per_nm * (1 + sum(w_i * s_i)) + penalty
%
%   Every secondary term s_i is normalised to a dimensionless 0-ish to 1-ish
%   scale and multiplied by an explicitly declared weight from
%   params.optimization.weights. The weights are printed by postprocess.m so
%   that no weight is ever applied without being reported. Set them all to zero
%   to optimise energy alone; use optimization_driver's Pareto mode to avoid
%   choosing weights at all.

if nargin < 7, opts = struct(); end
E = evaluate_design(x, Zf, Zr, arch, params, ds, opts);
brk = struct();

if ~E.ok
    J = 1e9;                      % infeasible designs are pushed far away but
    brk.fail = E.fail;            % never return Inf/NaN, which breaks optimisers
    return;
end

[c, labels, cinfo] = constraints(E, params);
w = params.optimization.weights;

base = E.E_per_nm_Wh;

% ---- secondary, normalised penalty terms -------------------------------
isSP = strcmpi(arch,'surfacepiercing') || strcmpi(arch,'sp');
if isSP
    s_cav  = 0;                                                  % ventilated: not the governing risk
    s_vent = max(0, 1 - E.vent.front.FnD/params.surfacePiercing.FnD_vent_threshold);
else
    s_cav  = max(0, params.cavitation.sigma_margin/max(E.cav.front.minMargin,1e-3) - 1);
    s_vent = 0;
end
s_load   = max(0, (E.cav.front.tau_c/max(E.cav.front.tau_allow,1e-6)) - 1);
s_stress = max(E.struct.front.sigma_combined_Pa, E.struct.rear.sigma_combined_Pa) / ...
           max(E.struct.front.sigma_allow_Pa,1);
s_gear   = E.gearbox.complexity/3;
s_manu   = manufacturability_penalty(E);
s_robust = 0;
if isfield(opts,'robustness') && opts.robustness
    s_robust = robustness_penalty(x, Zf, Zr, arch, params, ds, E);
end

mult = 1 + w.cavMargin*s_cav + w.ventMargin*s_vent + w.bladeLoading*s_load + ...
           w.peakStress*s_stress + w.gearboxComplexity*s_gear + ...
           w.manufacturability*s_manu + w.robustness*s_robust;

% Penalty scaled BY THE OBJECTIVE, not by an absolute constant. An absolute
% penalty weight is meaningless here because the objective is in Wh/nm and its
% magnitude is not known in advance: with a fixed weight of 1e4 a 0.6%
% constraint violation cost 0.36 Wh/nm against an objective of 544, so the
% optimiser correctly ignored it and returned an infeasible design. Scaling by
% the objective makes a 1% violation cost ~10% of the objective and a 10%
% violation cost ten times the objective, which is what a penalty is for.
penalty = params.optimization.penaltyWeight * base * sum(max(0,c).^2);

J = w.energy*base*mult + penalty;

brk.E_per_nm_Wh = base;
brk.multiplier  = mult;
brk.penalty     = penalty;
brk.terms = struct('cav',s_cav,'vent',s_vent,'loading',s_load,'stress',s_stress, ...
                   'gearbox',s_gear,'manufacturability',s_manu,'robustness',s_robust);
brk.constraints = c;
brk.labels = labels;
brk.feasible = cinfo.feasible;
brk.fastEnabled = params.numerics.fast.enable;
brk.fastVsFull  = 0;   % overwritten by optimization_driver.m for optimised cases
brk.violations = cinfo.violations;
end

% =========================================================================
function s = manufacturability_penalty(E)
%MANUFACTURABILITY_PENALTY  Smoothness and castability proxies.
s = 0;
for g = {E.gF, E.gR}
    gg = g{1};
    dcdx = abs(gradient(gg.c, gg.x))/max(gg.c);
    s = s + max(0, max(dcdx)/8 - 1);                    % abrupt chord change
    s = s + max(0, 0.015/max(min(gg.toc),1e-6) - 1);    % too thin to cast/machine
    s = s + max(0, gg.EAR/1.0 - 1);                     % very high blade area
end
s = s/2;
end

% =========================================================================
function s = robustness_penalty(x, Zf, Zr, arch, params, ds, E0)
%ROBUSTNESS_PENALTY  Sensitivity of the objective to a small speed excursion.
%   A design that is only good exactly at 20 kn is not a good design.
s = 0;  n = 0;
for dV = [-1 1]
    o = struct('V_kn', params.vessel.V_design_kn + dV);
    Ei = evaluate_design(x, Zf, Zr, arch, params, ds, o);
    if Ei.ok
        s = s + abs(Ei.E_per_nm_Wh - E0.E_per_nm_Wh)/max(E0.E_per_nm_Wh,1e-9);
        n = n + 1;
    else
        s = s + 0.5;  n = n + 1;
    end
end
if n > 0, s = s/n; end
end

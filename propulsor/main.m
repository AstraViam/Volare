function RES = main(varargin)
%MAIN  MEBC Energy Class coaxial contra-rotating propulsor design tool.
%
%   RES = MAIN()                 full run (both architectures, all blade counts)
%   RES = MAIN('quick', true)    reduced optimiser budget for a fast check
%   RES = MAIN('arch', 'sub')    one architecture only ('sp' or 'sub')
%   RES = MAIN('plots', false)   suppress figure generation
%   RES = MAIN('report', 'my.txt')  also write the report to a file
%   RES = MAIN('budget', [nPop1 nIt1 nPop2 nIt2 nIt3])   explicit optimiser budget
%   RES = MAIN('zcombos', [3 3; 4 4])   restrict the blade-count enumeration
%   RES = MAIN('load', true)     reuse results/opt_<arch>.mat if it exists
%   RES = MAIN('inputs', S)      supply external data files; see load_inputs.m
%
%   The run is organised in the fourteen stages set out in the design brief,
%   each with its own sanity check, so that a failure can be isolated.
%
%   Team Volare / ICT Mumbai.  See README.md for how to interpret the output.

opt = parse_args(varargin);
params = config();
% Externally supplied data (measured resistance, CFD wake, polars, motor map,
% material, CFD reference) enters ONLY here, so the solver never needs editing.
[params, inputReport] = load_inputs(params, opt.inputs);
if ~isempty(opt.plots), params.plots.enable = opt.plots; end
if ~exist(params.io.resultsDir,'dir'), mkdir(params.io.resultsDir); end
if ~exist(params.io.figuresDir,'dir'), mkdir(params.io.figuresDir); end

fids = 1;
if ~isempty(opt.report)
    f2 = fopen(fullfile(params.io.resultsDir, opt.report),'w');
    fids = [1 f2];
end
    function out(fmt, varargin)
        for f = fids, fprintf(f, fmt, varargin{:}); end
    end

t0 = tic;
out('\n%s\n MEBC ENERGY CLASS - COAXIAL CONTRA-ROTATING PROPULSOR DESIGN TOOL\n', repmat('#',1,73));
out(' %s\n run started %s\n%s\n', params.meta.version, datestr(now,31), repmat('#',1,73));
out('\n[EXTERNAL INPUTS]\n');
for k = 1:numel(inputReport), out('   %s\n', inputReport{k}); end

% =====================================================================
% STAGE 1: hull resistance and effective power
% =====================================================================
out('\n[STAGE 1] Hull resistance and effective power\n');
rr = resistance_model(params.resistance.speed_kn, params, 'barehull');
for k = 1:numel(rr.V_kn)
    out('   %5.1f kn -> %7.1f N  [%s]\n', rr.V_kn(k), rr.R_total_N(k), rr.dataTag{k});
end
rd = resistance_model(params.vessel.V_design_kn, params, 'barehull');
out('   design point: R_T = %.1f N, P_E = %.3f kW  (check against the brief: 624 N, 6.42 kW)\n', ...
    rd.R_hull_N, rd.P_E_W/1e3);
assert(abs(rd.R_hull_N - 624) < 1e-6, 'STAGE 1 FAILED: resistance table not reproduced.');

% =====================================================================
% STAGE 2: motor envelope
% =====================================================================
out('\n[STAGE 2] Motor torque-speed-power envelope\n');
maud = motor_model(params.motor.n_max_rpm/60, params.motor.Q_max_Nm, params, 'continuous');
out('   ceiling at n_max and Q_max = %.2f kW\n', maud.audit.P_at_nmax_Qmax_W/1e3);
for k = 1:numel(maud.audit.flags), out('   !! %s\n', maud.audit.flags{k}); end
if maud.audit.consistent, out('   specification internally consistent.\n'); end

% =====================================================================
% STAGES 3-7: solver chain checked on the baseline design
% =====================================================================
out('\n[STAGES 3-7] Single rotor, front rotor, interaction, rear rotor, coupling\n');
archs = {};
if isempty(opt.arch) || any(strcmpi(opt.arch,{'sub','submerged'})),      archs{end+1} = 'submerged'; end
if isempty(opt.arch) || any(strcmpi(opt.arch,{'sp','surfacepiercing'})), archs{end+1} = 'surfacepiercing'; end

RES = struct();  RES.params = params;
baseline = struct();
for a = archs
    arch = a{1};
    ds = design_space(params, arch);
    xb = baseline_vector(params, ds);
    Eb = evaluate_design(xb, 3, 3, arch, params, ds, struct('detail',true));
    key = arch_key(arch);
    baseline.(key) = Eb;
    if Eb.ok
        out('   baseline (%s, 3/3, D = %.3f m, P = %.1f/%.1f in, equal speeds):\n', ...
            arch, Eb.gF.D, Eb.gF.P07_m*39.3701, Eb.gR.P07_m*39.3701);
        out('      %.0f rpm, %.2f kW shaft, eta_CRP = %.4f, %.1f Wh/nm\n', ...
            Eb.n_front_rps*60, Eb.P_shaft_W/1e3, Eb.crp.eta_CRP, Eb.E_per_nm_Wh);
        out('      coupling converged %d (%d evaluations), BEM %d/%d, thrust residual %.1e\n', ...
            Eb.crp.converged, Eb.crp.evaluations, Eb.crp.front.converged, Eb.crp.rear.converged, ...
            Eb.thrustSolve.residual);
        out('      swirl recovered by the rear rotor: %.1f%%; slipstream contraction %.4f\n', ...
            100*Eb.crp.swirlRecovery, Eb.crp.contractionRatio);
    else
        out('   baseline (%s) infeasible: %s\n', arch, Eb.fail);
    end
end
RES.baseline = baseline;

% =====================================================================
% STAGES 8-11: gearbox, surface piercing, checks, global optimisation
% =====================================================================
out('\n[STAGES 8-11] Global optimisation (energy per nautical mile)\n');
for a = archs
    arch = a{1};
    key = arch_key(arch);
    out('   optimising architecture: %s\n', arch);
    cacheFile = fullfile(params.io.resultsDir, sprintf('opt_%s.mat', key));
    if ~isempty(opt.load) && exist(cacheFile,'file')
        L = load(cacheFile);  OPT = L.OPT;
        out('   loaded cached result for %s from %s\n', arch, cacheFile);
    else
        OPT = optimization_driver(arch, params, struct('quick', opt.quick, ...
            'budget', opt.budget, 'ZcombosOnly', opt.Zcombos));
        try, save(cacheFile, 'OPT', '-v7'); catch, end
    end
    RES.(key) = OPT;
end

% choose the primary architecture: the better of the two on energy
primary = '';  bestE = Inf;
for a = archs
    key = arch_key(a{1});
    if RES.(key).best.E.ok && RES.(key).best.E.E_per_nm_Wh < bestE
        bestE = RES.(key).best.E.E_per_nm_Wh;  primary = key;
    end
end
if isempty(primary)
    out('\n!! NO FEASIBLE DESIGN FOUND IN ANY ARCHITECTURE. Check the constraints and bounds.\n');
    RES.ok = false;  return;
end
RES.primary = primary;
RES.primaryOPT = RES.(primary);
best = RES.(primary).best;

% re-evaluate the winner with detail on (cyclic loads) and a finer radial grid
pFine = params;  pFine.propeller.common.nRadial = params.propeller.common.nRadialFinal;
RES.primaryE = evaluate_design(best.x, best.Zf, best.Zr, RES.(primary).arch, pFine, ...
                               design_space(pFine, RES.(primary).arch), struct('detail',true));
if ~RES.primaryE.ok
    RES.primaryE = evaluate_design(best.x, best.Zf, best.Zr, RES.(primary).arch, params, ...
                                   design_space(params, RES.(primary).arch), struct('detail',true));
end

% =====================================================================
% Report
% =====================================================================
for f = fids
    postprocess(RES, params, f);
    sanity_checks(RES.primaryE, baseline.(primary), params, f);
    validation(params, f);
end

% =====================================================================
% STAGE 12: sensitivity
% =====================================================================
if ~opt.skipSensitivity
    for f = fids
        sensitivity_analysis(best.x, best.Zf, best.Zr, RES.(primary).arch, params, RES.(primary).ds, f);
    end
end

% =====================================================================
% STAGE 13: geometry export
% =====================================================================
out('\n[STAGE 13] Exporting geometry for CAD and Ansys\n');
files = export_geometry(RES.primaryE, params);
for k = 1:numel(files), out('   wrote %s\n', files{k}); end

% =====================================================================
% STAGE 14: plots and final summary
% =====================================================================
if params.plots.enable
    out('\n[STAGE 14] Generating figures\n');
    try
        plot_performance(RES, params);
        plot_geometry(RES.primaryE, params);
        out('   figures written to %s/\n', params.io.figuresDir);
    catch err
        out('   figure generation failed: %s\n', err.message);
    end
end

for f = fids, final_summary(RES.primaryE, RES, params, f); end

RES.runtime_s = toc(t0);
out('\n Total runtime: %.1f s\n', RES.runtime_s);
RES.ok = true;
try
    save(fullfile(params.io.resultsDir,'optimisation_results.mat'),'RES','-v7');
    out(' Full result structure saved to %s/optimisation_results.mat\n', params.io.resultsDir);
catch
end
if numel(fids) > 1, fclose(fids(2)); end
end

% =========================================================================
function final_summary(E, RES, params, fid)
U = units();
fprintf(fid,'\n==============================\n');
fprintf(fid,'OPTIMIZED MEBC CRP DESIGN\n');
fprintf(fid,'==============================\n');
fprintf(fid,'Architecture:            %s\n', upper(E.arch));
fprintf(fid,'Design speed:            %.1f knots\n', params.vessel.V_design_kn);
fprintf(fid,'Displacement:            %.0f kg\n', params.vessel.mass_design_kg);
fprintf(fid,'Hull resistance:         %.0f N (bare hull) + %.0f N drive leg\n', E.resistance.R_hull_N, E.resistance.R_app_N);
fprintf(fid,'Effective hull power:    %.2f kW\n', E.resistance.P_E_W/1e3);
fprintf(fid,'\nFront rotor:\n');
fprintf(fid,'  Diameter:              %.4f m (%.2f in)\n', E.gF.D, E.gF.D*U.m2in);
fprintf(fid,'  Blade count:           %d\n', E.gF.Z);
fprintf(fid,'  Pitch (0.7R):          %.4f m (%.2f in), P/D = %.3f\n', E.gF.P07_m, E.gF.P07_m*U.m2in, E.gF.P07_m/E.gF.D);
fprintf(fid,'  EAR:                   %.3f\n', E.gF.EAR);
fprintf(fid,'  Speed:                 %.0f rpm\n', E.n_front_rps*60);
fprintf(fid,'  Torque:                %.2f N.m\n', E.crp.front.Q);
fprintf(fid,'  Power:                 %.2f kW\n', E.crp.front.P/1e3);
fprintf(fid,'  Thrust:                %.1f N\n', E.crp.front.T);
fprintf(fid,'\nRear rotor:\n');
fprintf(fid,'  Diameter:              %.4f m (%.2f in)\n', E.gR.D, E.gR.D*U.m2in);
fprintf(fid,'  Blade count:           %d\n', E.gR.Z);
fprintf(fid,'  Pitch (0.7R):          %.4f m (%.2f in), P/D = %.3f\n', E.gR.P07_m, E.gR.P07_m*U.m2in, E.gR.P07_m/E.gR.D);
fprintf(fid,'  EAR:                   %.3f\n', E.gR.EAR);
fprintf(fid,'  Speed:                 %.0f rpm\n', E.n_rear_rps*60);
fprintf(fid,'  Torque:                %.2f N.m\n', E.crp.rear.Q);
fprintf(fid,'  Power:                 %.2f kW\n', E.crp.rear.P/1e3);
fprintf(fid,'  Thrust:                %.1f N\n', E.crp.rear.T);
fprintf(fid,'\nCRP:\n');
fprintf(fid,'  Total thrust:          %.1f N (required %.1f N)\n', E.crp.T_total_N, E.T_req_N);
fprintf(fid,'  Total shaft power:     %.2f kW\n', E.P_shaft_W/1e3);
fprintf(fid,'  Electrical power:      %.2f kW\n', E.P_elec_W/1e3);
fprintf(fid,'  Overall efficiency:    %.4f\n', E.eta_overall);
fprintf(fid,'  Energy per n.mile:     %.1f Wh/nm  (%.4f kWh/nm)\n', E.E_per_nm_Wh, E.E_per_nm_kWh);
fprintf(fid,'  Range on %.0f kWh:      %.1f nm\n', params.competition.E_stored_kWh, E.range_nm);
fprintf(fid,'\nMotor:\n');
fprintf(fid,'  Speed:                 %.0f rpm\n', E.motor.n_rpm);
fprintf(fid,'  Torque:                %.1f N.m\n', E.motor.Q_Nm);
fprintf(fid,'  Power:                 %.2f kW\n', E.motor.P_shaft_W/1e3);
fprintf(fid,'  Current at 96 V:       %.1f A\n', E.I_A);
fprintf(fid,'\nGearbox:\n');
fprintf(fid,'  Front ratio:           %.4f : 1\n', E.gearbox.ratio_front);
fprintf(fid,'  Rear ratio:            %.4f : 1\n', E.gearbox.ratio_rear);
fprintf(fid,'  Speed ratio F/R:       %.4f\n', E.gearbox.rpmRatio_F_over_R);
fprintf(fid,'  Torque ratio F/R:      %.4f\n', E.gearbox.torqueRatio_F_over_R);
fprintf(fid,'  Torque capacity:       %.1f N.m input\n', E.gearbox.rating.torque_input_Nm);
fprintf(fid,'  Power capacity:        %.2f kW\n', E.gearbox.rating.power_W/1e3);
fprintf(fid,'  Efficiency requirement:%.1f %%\n', 100*E.gearbox.rating.eta_required);
fprintf(fid,'  Counter-rotation:      REQUIRED\n');
fprintf(fid,'\nCavitation:\n');
fprintf(fid,'  Status:                %s (min margin %.2f)\n', ...
    tern(E.cav.front.anyCavitation,'PREDICTED','none predicted'), E.cav.front.minMargin);
fprintf(fid,'\nVentilation:\n');
if strcmpi(E.arch,'surfacepiercing')
    fprintf(fid,'  Status:                %s (Fn_D = %.2f, I_T = %.3f)\n', ...
        tern(E.vent.front.regimeFullyVentilated,'fully ventilated regime','TRANSITIONAL - UNRELIABLE'), ...
        E.vent.front.FnD, E.imm.front.I_T);
else
    fprintf(fid,'  Status:                not applicable (fully submerged)\n');
end
fprintf(fid,'\nStructural:\n');
fprintf(fid,'  Maximum stress:        %.1f MPa\n', max(E.struct.front.sigma_combined_Pa, E.struct.rear.sigma_combined_Pa)/1e6);
fprintf(fid,'  Safety factor:         %.2f\n', min(E.struct.front.SF_yield, E.struct.rear.SF_yield));
fprintf(fid,'  Status:                %s\n', tern(E.struct.front.ok && E.struct.rear.ok,'OK','FAIL'));
fprintf(fid,'\nOptimization:\n');
fprintf(fid,'  Objective:             %.1f Wh/nm (weighted %.1f)\n', E.E_per_nm_Wh, RES.primaryOPT.best.J);
fprintf(fid,'  Converged:             %d\n', RES.primaryOPT.converged);
fprintf(fid,'  Blade counts:          %d/%d\n', E.gF.Z, E.gR.Z);
fprintf(fid,'  Seed:                  %d\n', RES.primaryOPT.seed);
fprintf(fid,'==============================\n');
end

% =========================================================================
function x = baseline_vector(params, ds)
%BASELINE_VECTOR  The reference design from the brief: equal diameters, 3/3
%   blades, 26.5 in and 28.5 in pitch, equal speeds. NOT claimed to be optimal.
x = ds.x0;
i = ds.index;
x(i.D_front_m)   = 0.45;
x(i.D_rear_m)    = 0.45;
x(i.P07_front_m) = params.propeller.front.P07_ref_m;
x(i.P07_rear_m)  = params.propeller.rear.P07_ref_m;
x(i.rpmRatio_F_over_R) = 1.0;
x(i.d_hub_m)     = params.propeller.common.D_hub_m;
x(i.beta_shaft_deg) = 0;
x = min(max(x, ds.lb), ds.ub);
end

function k = arch_key(arch)
if strcmpi(arch,'surfacepiercing'), k = 'sp'; else, k = 'sub'; end
end

function s = tern(c,a,b)
if c, s = a; else, s = b; end
end

function o = parse_args(v)
o.quick = false;  o.arch = '';  o.plots = [];  o.report = 'design_report.txt';
o.skipSensitivity = false;  o.budget = [];  o.Zcombos = [];  o.load = '';
o.inputs = struct();
for k = 1:2:numel(v)
    switch lower(v{k})
        case 'quick',  o.quick = v{k+1};
        case 'arch',   o.arch = v{k+1};
        case 'plots',  o.plots = v{k+1};
        case 'report', o.report = v{k+1};
        case 'skipsensitivity', o.skipSensitivity = v{k+1};
        case 'budget', o.budget = v{k+1};      % [nPop1 nIt1 nPop2 nIt2 nIt3]
        case 'zcombos', o.Zcombos = v{k+1};    % e.g. [3 3; 4 4]
        case 'load',   o.load = v{k+1};        % reuse a saved architecture result
        case 'inputs', o.inputs = v{k+1};      % struct of external data files, see load_inputs.m
    end
end
end

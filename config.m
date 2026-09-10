function params = config()
%CONFIG  Central parameter structure for the MEBC contra-rotating propulsor tool.
%
%   params = CONFIG() returns the single source of truth for every engineering
%   number used by the framework.  No physical constant may be hard-coded
%   anywhere else in the project.
%
%   UNITS: SI throughout (m, kg, s, N, Pa, W, rad, rad/s).  Imperial inputs are
%   converted here, at the boundary, using units.m.  Rotational speed is stored
%   as rev/s internally ("n") and only converted to RPM for reporting.
%
%   ASSUMPTION BOOK-KEEPING: any value that was NOT supplied by the user and had
%   to be assumed is registered with add_assumption() so that print_assumptions.m
%   can list it.  Do not add an unsupplied number without registering it.
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

U = units();
params = struct();
params.assumptions = {};   % cell array of assumption records
params.meta.created  = datestr(now, 31);
params.meta.version  = 'v1.0';
params.meta.title    = 'MEBC Energy Class - coaxial contra-rotating propulsor design tool';

% =========================================================================
% 1. VESSEL
% =========================================================================
params.vessel.type            = 'catamaran';
params.vessel.L_hull_m        = 5.0;      % SUPPLIED
params.vessel.hullSpacing_m   = 2.5;      % SUPPLIED (note: crossbeam span is 3.0 m per MEBC rules - confirm which is meant)
params.vessel.mass_design_kg  = 250;      % SUPPLIED - design displacement
params.vessel.mass_worst_kg   = 300;      % SUPPLIED - sensitivity case (NO resistance curve supplied)
params.vessel.LCG_m           = 1.8;      % SUPPLIED - XCOG associated with the resistance curve
params.vessel.V_design_kn     = 20.0;     % SUPPLIED - primary design speed
params.vessel.V_design_ms     = 20.0 * U.kn2ms;
params.vessel.nProp           = 1;        % one contra-rotating propulsor unit

% =========================================================================
% 2. RESISTANCE DATA  (SUPPLIED - Energy Class curve, 250 kg, XCOG 1.8 m)
% =========================================================================
params.resistance.speed_kn        = [0    5    10   15   20 ];
params.resistance.R_total_N       = [0    89   212  381  624];
params.resistance.mass_kg         = 250;
params.resistance.LCG_m           = 1.8;
params.resistance.method          = 'pchip';   % shape-preserving; NO polynomial fit, NO V^2 law
params.resistance.allowExtrap     = false;     % extrapolation must be explicitly requested and is flagged
params.resistance.source          = 'SUPPLIED - MEBC Energy Class resistance curve (250 kg, LCG 1.8 m)';

% 300 kg worst case: NOT SUPPLIED. Leave empty; the code refuses to fabricate it.
params.resistance.speed_kn_300    = [];
params.resistance.R_total_N_300   = [];
params.resistance.scaling300.enable = false;   % if true, a CLEARLY LABELLED theoretical estimate is used
params.resistance.scaling300.exponent = 2/3;   % R ~ Delta^(2/3) crude wetted-area scaling - NOT VALIDATED

% Appendage drag.  CRITICAL: it is unknown whether the supplied 624 N includes
% the drive leg.  We assume BARE HULL and add drive-leg drag explicitly, because
% the submerged-vs-surface-piercing comparison is dominated by this term.
params.resistance.hullCurveIsBareHull = true;
params.appendage.enable          = true;
params.appendage.strut.chord_m   = 0.150;
params.appendage.strut.toc       = 0.12;    % thickness/chord
params.appendage.strut.span_sub_submerged_m = 0.35;  % wetted strut span, fully submerged config
params.appendage.strut.span_sub_sp_m        = 0.08;  % wetted strut span, surface-piercing config
params.appendage.pod.diameter_m  = 0.110;   % gearcase/torpedo
params.appendage.pod.length_submerged_m = 0.50;
params.appendage.pod.length_sp_m        = 0.00;  % SP: gearcase is out of the water
params.appendage.formFactor_strut = 1.5;
params.appendage.formFactor_pod   = 1.4;
params.appendage.spray_sp_N       = 15;     % surface-piercing shaft/hub spray + surface-disturbance drag

% =========================================================================
% 3. WATER PROPERTIES
% =========================================================================
params.water.type        = 'seawater';
params.water.T_C         = 20;          % ASSUMED
params.water.rho         = 1025.0;      % kg/m^3   ASSUMED (seawater, 20 C)
params.water.mu          = 1.07e-3;     % Pa.s     ASSUMED
params.water.nu          = params.water.mu / params.water.rho;
params.water.p_atm       = 101325;      % Pa
params.water.p_vapour    = 2339;        % Pa       ASSUMED (fresh/sea water at 20 C)
params.water.g           = 9.81;
params.water.sigma_surf  = 0.0728;      % N/m surface tension, for Weber-number ventilation check

% =========================================================================
% 4. MOTOR  (axial-flux PMSM, water cooled)
% =========================================================================
params.motor.type          = 'axial-flux PMSM';
params.motor.P_nominal_W   = 25.0e3;    % SUPPLIED continuous
params.motor.P_max_spec_W  = 42.0e3;    % SUPPLIED peak SPEC (see consistency check)
params.motor.Q_max_Nm      = 100.0;     % SUPPLIED hard torque limit
params.motor.n_nominal_rpm = 1300;      % SUPPLIED
params.motor.n_max_rpm     = 2500;      % SUPPLIED hard speed limit
params.motor.eta           = 0.95;      % SUPPLIED (constant, first version)
params.motor.etaMap        = [];        % placeholder: function handle eta = f(rpm, Q)
params.motor.V_system_V    = 96.0;      % SUPPLIED nominal DC bus
params.motor.I_limit_A     = 375;       % from drive datasheet - CONFIGURABLE, not enforced by default
params.motor.enforceCurrentLimit = true;
params.controller.eta      = 0.97;      % ASSUMED inverter/controller efficiency
params.controller.enable   = true;

% =========================================================================
% 5. GEARBOX / TRANSMISSION  (NOT YET DESIGNED)
% =========================================================================
params.gearbox.eta          = 0.96;     % ASSUMED overall mechanical efficiency
params.gearbox.eta_sens     = [0.90 0.93 0.96 0.98];  % sensitivity sweep
params.gearbox.ratio_min    = 0.30;     % n_prop/n_motor bounds - ASSUMED mechanical plausibility
params.gearbox.ratio_max    = 4.00;
params.gearbox.serviceFactor = 1.25;    % ASSUMED rating margin on torque/power capacity
params.gearbox.architecture = 'undetermined - specification to be produced by this tool';

% =========================================================================
% 6. PROPELLER - COMMON
% =========================================================================
params.propeller.common.D_max_m       = 21 * U.in2m;      % SUPPLIED 21 in = 0.5334 m
params.propeller.common.D_hub_m       = 0.120;            % SUPPLIED baseline
params.propeller.common.hubRatio_min  = 0.16;
params.propeller.common.hubRatio_max  = 0.30;
params.propeller.common.axialGap_m    = 0.050;            % SUPPLIED design value
params.propeller.common.axialGap_sens = [0.030 0.050 0.075 0.100];
params.propeller.common.L_shaft_m     = 0.500;            % SUPPLIED
params.propeller.common.beta_shaft_deg_min = -5;          % SUPPLIED limit
params.propeller.common.beta_shaft_deg_max = +5;
params.propeller.common.nRadial       = 24;               % radial stations (20-40 requested)
params.propeller.common.nRadialFinal  = 36;               % refined grid for the final reported design
params.propeller.common.rR_root       = 0.20;             % r/R at blade root
params.propeller.common.nAzimuth      = 72;               % azimuthal stations for surface-piercing
params.propeller.common.rotationSense = [+1 -1];          % front, rear (contra-rotating)

% Blade section geometry parameterisation (smooth, few design variables)
params.propeller.common.skew_tip_deg  = 15;   % geometric only - hydrodynamic effect NOT modelled
params.propeller.common.rake_tip_deg  = 5;    % geometric only
params.propeller.common.tTE_over_c    = 0.03; % trailing-edge thickness ratio (base drag, SC sections)

% =========================================================================
% 7. PROPELLER - FRONT / REAR REFERENCE VALUES AND BOUNDS
% =========================================================================
params.propeller.front.Z_options   = [3 4];
params.propeller.rear.Z_options    = [3 4];
params.propeller.front.P07_ref_m   = 26.5 * U.in2m;   % SUPPLIED reference pitch
params.propeller.rear.P07_ref_m    = 28.5 * U.in2m;   % SUPPLIED reference pitch
params.propeller.front.P07_min_m   = 22 * U.in2m;     % configurable search bounds
params.propeller.front.P07_max_m   = 30 * U.in2m;
params.propeller.rear.P07_min_m    = 24 * U.in2m;
params.propeller.rear.P07_max_m    = 32 * U.in2m;
params.propeller.front.D_min_m     = 0.30;
params.propeller.rear.D_min_m      = 0.30;
params.propeller.common.EAR_min    = 0.45;
params.propeller.common.EAR_max    = 1.05;
params.propeller.common.n_prop_min_rps = 5;     % ASSUMED propeller speed bounds (gearbox plausibility)
params.propeller.common.n_prop_max_rps = 60;
params.propeller.common.rpmRatio_min   = 0.70;  % n_front / n_rear
params.propeller.common.rpmRatio_max   = 1.40;

% =========================================================================
% 8. SURFACE-PIERCING PARAMETERS  (primary architecture)
% =========================================================================
params.surfacePiercing.enable        = true;
params.surfacePiercing.hShaft_over_R = 0.05;  % shaft-axis depth / R_front. I_T=(h/R+1)/2 => 0.525
params.surfacePiercing.hShaft_min    = -0.30; % optimiser bounds on h/R
params.surfacePiercing.hShaft_max    = 0.60;
params.surfacePiercing.entryAngle_deg = 25;   % ASSUMED blade-entry force build-up sector
params.surfacePiercing.exitAngle_deg  = 20;   % ASSUMED blade-exit cavity-drag-out sector
params.surfacePiercing.entryEfficiency = 0.55;% ASSUMED mean force factor within entry/exit sectors
params.surfacePiercing.ventFraction_full = 1.00; % fully ventilated blade sections assumed when criteria met
params.surfacePiercing.FnD_vent_threshold = 4.0; % ASSUMED n*D/sqrt(gD) for fully ventilated regime
params.surfacePiercing.We_threshold  = 260;   % ASSUMED Weber-number threshold for stable ventilation
params.surfacePiercing.k_sc          = 1.00;  % ventilated-section lift factor vs linear SC flat plate
params.surfacePiercing.Cd_base       = 0.030; % ASSUMED base (cavity closure) drag coefficient
params.surfacePiercing.sigma_vent    = 0.00;  % ventilated to atmosphere => cavity pressure ~ p_atm

% Fully submerged comparison configuration
params.submerged.hShaft_over_R       = 1.60;  % ASSUMED tip immersion for the submerged baseline
params.submerged.ventFraction        = 0.00;

% =========================================================================
% 9. HULL-PROPELLER INTERACTION  (NO EXPERIMENTAL DATA SUPPLIED)
% =========================================================================
params.hull.w        = 0.05;   % ASSUMED wake fraction  (slender catamaran demihull, transom flow)
params.hull.t        = 0.10;   % ASSUMED thrust deduction
params.hull.eta_R    = 1.00;   % ASSUMED relative rotative efficiency
params.hull.w_sens   = [0.00 0.03 0.05 0.08 0.12];
params.hull.t_sens   = [0.04 0.07 0.10 0.14 0.18];
params.hull.wakeField = [];    % placeholder: [rR, w(rR)] from CFD replaces the uniform-wake model
params.hull.useWakeField = false;

% =========================================================================
% 10. MATERIAL DATABASE  (grade NOT specified - generic austenitic assumption)
% =========================================================================
params.material.name        = 'GENERIC austenitic stainless steel (grade NOT specified)';
params.material.rho         = 7900;      % kg/m^3   ASSUMED
params.material.E           = 193e9;     % Pa       ASSUMED
params.material.nu          = 0.30;      % -        ASSUMED
params.material.sigma_yield = 250e6;     % Pa       ASSUMED
params.material.sigma_ult   = 550e6;     % Pa       ASSUMED
params.material.sigma_fatigue = 180e6;   % Pa       ASSUMED (corrosion fatigue, seawater, R=-1 basis)
params.material.SF_required = 3.0;       % ASSUMED design safety factor on yield
params.material.SF_fatigue  = 1.8;       % ASSUMED safety factor on fatigue for cyclic SP loading
params.material.sectionModulusCoeff = 0.10;  % Z ~ k*c*t^2 for propeller sections - ASSUMED

% =========================================================================
% 11. HYDROFOIL SECTION POLARS  (NO MEASURED DATA SUPPLIED)
% =========================================================================
params.polar.source        = 'PROVISIONAL ANALYTICAL MODEL - replace with XFOIL / CFD / experimental polars';
params.polar.external      = [];         % struct with fields alpha, Re, Cl, Cd -> triggers table lookup
params.polar.useExternal   = false;
params.polar.Cl_alpha      = 2*pi;       % per rad, thin-aerofoil
params.polar.alpha_stall_deg = 12;       % ASSUMED
params.polar.alpha_stall_rad = 12*pi/180;% precomputed - hot path, do not call units() there
params.polar.dCd_dCl2      = 0.012;      % ASSUMED drag bucket curvature
params.polar.Cl_design     = 0.25;       % ASSUMED bucket centre
params.polar.frictionLine  = 'ITTC-57';
params.polar.Re_min        = 5e4;        % below this the polar model is flagged out-of-range

% =========================================================================
% 12. CAVITATION / VENTILATION
% =========================================================================
params.cavitation.CpMin_peakFactor  = 2.0;   % ASSUMED loading peak factor in the Cp_min estimate
params.cavitation.sigma_margin      = 1.15;  % required sigma_local / |Cp_min|
params.cavitation.burrill.a         = 0.28;  % EMPIRICAL FIT to the Burrill 5%-back-cavitation line
params.cavitation.burrill.b         = 0.57;
params.cavitation.burrill.c         = 0.03;

% =========================================================================
% 13. COMPETITION CONSTRAINTS  (MEBC Energy Class)
% =========================================================================
params.competition.E_stored_kWh   = 10.0;   % SUPPLIED - configurable
params.competition.P_motor_cap_W  = 25.0e3; % Energy Class nominal motor cap
params.competition.mission_nm     = [];     % optional: mission length for range check

% =========================================================================
% 14. OPTIMISATION SETTINGS
% =========================================================================
params.optimization.seed          = 20260823;
params.optimization.stage1.nPop   = 60;     % coarse global (PSO)
params.optimization.stage1.nIter  = 40;
params.optimization.stage2.nPop   = 30;     % refinement around best candidates
params.optimization.stage2.nIter  = 25;
params.optimization.stage3.nIter  = 300;    % local Nelder-Mead / fmincon iterations
params.optimization.useToolbox    = false;  % true -> try ga/particleswarm/fmincon if licensed
params.optimization.penaltyWeight = 1e3;    % penalty = objective * weight * sum(max(0,c)^2)
                                            % c is normalised, so a 1% violation costs ~10% of
                                            % the objective and a 10% violation costs ~10x it
params.optimization.verbose       = true;

% Secondary objective weights - ALL documented, all applied to normalised terms
params.optimization.weights.energy        = 1.000;  % primary: Wh/nm
params.optimization.weights.cavMargin     = 0.020;
params.optimization.weights.ventMargin    = 0.020;
params.optimization.weights.bladeLoading  = 0.015;
params.optimization.weights.peakStress    = 0.015;
params.optimization.weights.gearboxComplexity = 0.010;
params.optimization.weights.manufacturability = 0.010;
params.optimization.weights.robustness    = 0.020;
params.optimization.paretoEnable          = true;

% =========================================================================
% 15. NUMERICS
% =========================================================================
params.numerics.bem.maxIter    = 40;
params.numerics.bem.tol        = 1e-6;   % rad, change in the root estimate
params.numerics.bem.ftol       = 1e-5;   % momentum/blade-element residual, fraction of W
params.numerics.bem.relax      = 0.25;
params.numerics.bem.a_max      = 1.50;
params.numerics.crp.maxIter    = 40;
params.numerics.crp.tol        = 1e-4;   % RELATIVE to the advance velocity
params.numerics.crp.relax      = 0.85;
params.numerics.crp.residualAccept = 0.03;  % accepted interference residual, fraction of V_A
params.numerics.crp.residualClean  = 0.005; % below this, no jump warning is raised
params.numerics.thrustSolve.tol      = 5e-4;   % relative thrust matching tolerance
params.numerics.thrustSolve.maxIter  = 80;
params.numerics.eps            = 1e-12;

% Fast mode: coarser discretisation and looser tolerances used ONLY during the
% global search stages. Every surviving candidate is re-evaluated at full
% fidelity before it is reported, and the difference between the fast and full
% evaluation of the winner is printed so the reduction is never hidden.
params.numerics.fast.enable     = false;  % see fast_params.m - reducing nRadial gives no useful speedup
params.numerics.fast.nRadial    = 18;
params.numerics.fast.bem_tol    = 1e-5;   % NOT loosened - see fast_params.m
params.numerics.fast.crp_tol    = 1e-4;   % NOT loosened - see fast_params.m
params.numerics.fast.thrust_tol = 5e-4;   % NOT loosened - see fast_params.m
params.numerics.fast.ladder     = 7;
params.numerics.ladderPoints    = 7;

% =========================================================================
% 16. VALIDATION REFERENCE DATA  (model scale - NOT a design input)
% =========================================================================
params.validation.enable   = true;
params.validation.cfd.J        = 0.60;
params.validation.cfd.n_rpm    = 4220;
params.validation.cfd.V_A_ms   = 3.40;
params.validation.cfd.Q_Nm     = 1.06;
params.validation.cfd.P_W      = 460;
params.validation.cfd.T_N      = [];    % NOT SUPPLIED
params.validation.cfd.D_m      = [];    % NOT SUPPLIED - implied by J, n, V_A (see validation.m)
params.validation.cfd.rho      = 1025;  % ASSUMED for the model test
params.validation.cfd.note     = 'Model-scale reference only. Not to be used as a full-scale input.';

% =========================================================================
% 17. OUTPUT / PLOTTING
% =========================================================================
params.io.resultsDir  = 'results';
params.io.figuresDir  = 'figures';
params.io.saveFigures = true;
params.plots.enable   = true;
params.plots.fontSize = 10;

% =========================================================================
% ASSUMPTION REGISTER - every unsupplied value used above
% =========================================================================
A = {};
A = add_assumption(A,'Water temperature',              params.water.T_C,'degC','Not supplied; sets rho, mu, p_v.');
A = add_assumption(A,'Seawater density',               params.water.rho,'kg/m^3','Standard seawater at 20 C. Scales all forces linearly.');
A = add_assumption(A,'Dynamic viscosity',              params.water.mu,'Pa.s','Sets blade Reynolds number and hence section drag.');
A = add_assumption(A,'Vapour pressure',                params.water.p_vapour,'Pa','Sets cavitation number.');
A = add_assumption(A,'Wake fraction w',                params.hull.w,'-','NO measurement supplied. Directly scales V_A and hence J and efficiency.');
A = add_assumption(A,'Thrust deduction t',             params.hull.t,'-','NO measurement supplied. Directly scales required thrust: T=R/(1-t).');
A = add_assumption(A,'Relative rotative efficiency',   params.hull.eta_R,'-','NO measurement supplied. Multiplies delivered power.');
A = add_assumption(A,'Gearbox efficiency',             params.gearbox.eta,'-','Gearbox NOT designed. Sensitivity swept in sensitivity_analysis.m.');
A = add_assumption(A,'Controller efficiency',          params.controller.eta,'-','Not supplied. Multiplies electrical power directly.');
A = add_assumption(A,'Gear ratio plausibility bounds', params.gearbox.ratio_max,'-','No gearbox architecture selected; bounds constrain the search only.');
A = add_assumption(A,'Hull curve is bare-hull',        1,'bool','Unknown whether the 624 N includes the drive leg. Appendage drag is ADDED. This dominates the SP-vs-submerged comparison.');
A = add_assumption(A,'Appendage drag model',           params.appendage.strut.chord_m,'m (strut chord)','Flat-plate friction + form factor. NOT validated. See resistance_model.m.');
A = add_assumption(A,'Stainless steel properties',     params.material.sigma_yield/1e6,'MPa yield','Grade NOT specified. Generic austenitic values.');
A = add_assumption(A,'Section modulus coefficient',    params.material.sectionModulusCoeff,'-','Z ~ k*c*t^2 for aerofoil sections. Screening only; FEA required.');
A = add_assumption(A,'Hydrofoil polars',               0,'-','NO section data supplied. Provisional analytical Cl/Cd model. Largest single uncertainty after the SP model.');
A = add_assumption(A,'Ventilated-section lift factor', params.surfacePiercing.k_sc,'-','Linearised supercavitating flat-plate theory (Cl=(pi/2)*alpha). Real SC sections differ.');
A = add_assumption(A,'Base/cavity drag coefficient',   params.surfacePiercing.Cd_base,'-','Sets surface-piercing L/D and therefore the whole SP efficiency.');
A = add_assumption(A,'Blade entry/exit sectors',       params.surfacePiercing.entryAngle_deg,'deg','Cyclic force build-up model. Requires CFD or experiment.');
A = add_assumption(A,'Shaft immersion h/R',            params.surfacePiercing.hShaft_over_R,'-','Optimisation variable; baseline value assumed.');
A = add_assumption(A,'Ventilation Froude threshold',   params.surfacePiercing.FnD_vent_threshold,'-','Empirical fully-ventilated transition criterion.');
A = add_assumption(A,'Burrill limit-line fit',         params.cavitation.burrill.a,'-','Empirical fit to a published cavitation limit chart, not a first-principles result.');
A = add_assumption(A,'Cp_min peak factor',             params.cavitation.CpMin_peakFactor,'-','Thin-section suction-peak estimate. Panel method or CFD required.');
A = add_assumption(A,'Propeller speed bounds',         params.propeller.common.n_prop_max_rps,'rev/s','Constrains the search space only.');
A = add_assumption(A,'Skew and rake',                  params.propeller.common.skew_tip_deg,'deg','Geometric output only - hydrodynamic effect NOT modelled.');
params.assumptions = A;

end

% -------------------------------------------------------------------------
function A = add_assumption(A, name, value, unit, note)
A{end+1} = struct('name',name,'value',value,'unit',unit,'note',note);
end

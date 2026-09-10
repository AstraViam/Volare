function sp = surface_piercing_model(action, varargin)
%SURFACE_PIERCING_MODEL  Partial-immersion and ventilation modelling.
%
%   TWO-LEVEL APPROACH, deliberately, and stated as such:
%
%   LEVEL 1 - CYCLE-AVERAGED PERFORMANCE (used by the solver)
%     Each radial station is immersed for only part of a revolution.  The
%     immersion duty at radius r, for a shaft axis at depth h below the free
%     surface, follows from  r*cos(theta) < h :
%         duty(r) = 1                       if h >= r      (always immersed)
%                 = 0                       if h <= -r     (never immersed)
%                 = 1 - acos(h/r)/pi        otherwise
%     This duty multiplies BOTH the blade-element force and the annulus
%     momentum area in bem_rotor.m, which is what produces the correct
%     reduced-disk-area induced-loss penalty.
%     A separate entry/exit efficiency factor accounts for the fact that a
%     blade does not develop full force the instant it touches the water.
%
%   LEVEL 2 - AZIMUTHAL CYCLIC LOADS (post-processing, for fatigue)
%     Once the cycle-averaged BEM has converged, the instantaneous loads are
%     reconstructed over one revolution to obtain peak, mean and minimum
%     thrust and torque and the cyclic torque amplitude, which the shaft,
%     gearbox and blade root must survive.
%
%   VENTILATION IS NOT CAVITATION.  Ventilation is atmospheric air drawn down
%   the low-pressure side of a blade that breaks the free surface; the cavity
%   pressure is close to atmospheric.  Cavitation is a vapour cavity at p_v.
%   They are computed and reported separately (see cavitation_model.m).
%
%   *** MODEL STATUS: ANALYTICAL/EMPIRICAL. The entry/exit force build-up, the
%   ventilated section polar and the effective blade area are the least
%   certain parts of this entire framework. They REQUIRE CFD (VOF, sliding
%   mesh) and free-surface tank testing before any of the surface-piercing
%   numbers here are used for a build decision. ***
%
%   USAGE
%     imm  = surface_piercing_model('immersion', g, hShaft_m, params)
%     vent = surface_piercing_model('ventilation', g, n_rps, hShaft_m, V_A, params)
%     cyc  = surface_piercing_model('cyclic', bemRes, hShaft_m, params)

switch lower(action)
    case 'immersion',   sp = immersion(varargin{:});
    case 'ventilation', sp = ventilation(varargin{:});
    case 'cyclic',      sp = cyclic(varargin{:});
    otherwise, error('surface_piercing_model:action','Unknown action "%s".', action);
end
end

% =========================================================================
function imm = immersion(g, hShaft_m, params)
%IMMERSION  Radial duty distribution and disk immersion ratio.
r = g.r(:).';
h = hShaft_m;
ratio = h ./ max(r, 1e-9);
duty  = 1 - acos( min(max(ratio,-1), 1) )/pi;
duty(ratio >=  1) = 1;
duty(ratio <= -1) = 0;

% entry/exit force build-up: within the entry and exit sectors the blade
% develops only a fraction of the steady force it would develop fully immersed.
U  = units();
spp = params.surfacePiercing;
dTheta = (spp.entryAngle_deg + spp.exitAngle_deg)*U.deg2rad;
% fraction of the immersed arc that lies in the entry/exit sectors
arc = 2*pi*duty;
fEE = min( dTheta ./ max(arc, 1e-6), 1 );
dutyEff = duty .* ( (1-fEE) + fEE*spp.entryEfficiency );
dutyEff(duty <= 0) = 0;

imm.r        = r;
imm.x        = g.x;
imm.duty     = duty;
imm.dutyEff  = dutyEff;
imm.hShaft_m = h;
imm.I_T      = min(max((h + g.R)/(2*g.R), 0), 1);      % immersed fraction of the disk diameter
imm.tipDepth_m  = h + g.R;
imm.hubExposed  = h < g.r_hub/2;
imm.fullySubmerged = all(duty >= 1-1e-9);
imm.wettedDiskFraction = sum(duty.*2*pi.*r.*g.dr)/(pi*(g.R^2 - (g.r_hub/2)^2));
imm.entryExitFraction = fEE;
end

% =========================================================================
function v = ventilation(g, n_rps, hShaft_m, V_A, params)
%VENTILATION  Regime criteria and the ventilated fraction of each section.
%   Empirical criteria, all thresholds configurable in config.m:
%     Froude number   Fn_D = n*D/sqrt(g*D)      fully ventilated above ~4
%     Weber number    We   = rho*V^2*D/sigma    surface-tension scaling
%   A section is treated as fully ventilated when it is partially immersed at
%   any point in the revolution AND the regime criteria are met.
spp = params.surfacePiercing;
gg  = params.water.g;
rho = params.water.rho;

FnD = n_rps*g.D/sqrt(gg*g.D);
Vtip = sqrt(V_A^2 + (pi*n_rps*g.D)^2);
We   = rho*Vtip^2*g.D/params.water.sigma_surf;

imm  = immersion(g, hShaft_m, params);
regimeOK = (FnD >= spp.FnD_vent_threshold) && (We >= spp.We_threshold);

ventFrac = zeros(size(g.r));
partial  = imm.duty < 1-1e-9;
if regimeOK
    ventFrac(partial) = spp.ventFraction_full;
else
    % transitional: partially ventilated, scaled by how far below threshold
    scale = min(max(FnD/spp.FnD_vent_threshold, 0), 1);
    ventFrac(partial) = spp.ventFraction_full*scale;
end
% A fully submerged station beneath a ventilating one can still be reached by
% the air cavity if the tip is exposed; flagged rather than modelled.
v.ventFrac = ventFrac;
v.FnD      = FnD;
v.We       = We;
v.regimeFullyVentilated = regimeOK;
v.I_T      = imm.I_T;
v.duty     = imm.duty;
v.dutyEff  = imm.dutyEff;
v.warnings = {};
if ~regimeOK && any(partial)
    v.warnings{end+1} = sprintf(['Partially immersed but Fn_D = %.2f < %.2f (or We = %.0f < %.0f): ', ...
        'the rotor is in the PARTIALLY ventilated / transitional regime, where thrust breakdown ', ...
        'and violent load fluctuation occur. This regime is NOT reliably modelled analytically.'], ...
        FnD, spp.FnD_vent_threshold, We, spp.We_threshold);
end
if imm.I_T > 0.85 && imm.I_T < 1
    v.warnings{end+1} = 'Immersion ratio 0.85-1.0: neither cleanly surface-piercing nor cleanly submerged. Air-drawing and thrust breakdown are likely.';
end
end

% =========================================================================
function cyc = cyclic(bemRes, hShaft_m, params)
%CYCLIC  Reconstruct instantaneous loads over one revolution (Level 2).
%   The converged cycle-averaged element loads are redistributed over the
%   azimuth according to which stations are wetted at each blade position, with
%   the entry/exit ramp applied. Blade positions are phased by 2*pi/Z.
U   = units();
spp = params.surfacePiercing;
g   = bemRes.geom;
Nz  = params.propeller.common.nAzimuth;
th  = linspace(0, 2*pi, Nz+1);  th(end) = [];      % 0 = top dead centre
r   = bemRes.r;
Z   = bemRes.Z;

% Steady (fully wetted) element loads: remove the duty factor that
% bem_rotor.m already applied, to recover the instantaneous values.
duty = max(bemRes.duty, 1e-9);
dT_wet = bemRes.dT_dr ./ duty;
dQ_wet = bemRes.dQ_dr ./ duty;

drv = g.dr(:).';
entry = spp.entryAngle_deg*U.deg2rad;
exitA = spp.exitAngle_deg *U.deg2rad;

T_t = zeros(1,Nz);  Q_t = zeros(1,Nz);
immersedArea = zeros(1,Nz);
for k = 1:Nz
    Tk = 0; Qk = 0; Ak = 0;
    for b = 0:Z-1
        thb = mod(th(k) + b*2*pi/Z, 2*pi);
        depth = hShaft_m + r*cos(thb);          % >0 means submerged
        wet   = depth > 0;
        ramp  = ones(size(r));
        % angular distance from the entry and exit points at each radius
        ratio = min(max(hShaft_m./max(r,1e-9), -1), 1);
        thEntry = acos(ratio);                  % blade enters the water here
        dEnter  = angdiff(thb, thEntry);
        dExit   = angdiff(2*pi - thEntry, thb);
        inEntry = wet & (dEnter >= 0) & (dEnter < entry);
        inExit  = wet & (dExit  >= 0) & (dExit  < exitA);
        ramp(inEntry) = spp.entryEfficiency + (1-spp.entryEfficiency).*(dEnter(inEntry)/entry);
        ramp(inExit)  = spp.entryEfficiency + (1-spp.entryEfficiency).*(dExit(inExit)/exitA);
        f = double(wet).*ramp;
        Tk = Tk + sum(dT_wet.*f.*drv/Z);        % dT_wet is for all Z blades
        Qk = Qk + sum(dQ_wet.*f.*drv/Z);
        Ak = Ak + sum(double(wet).*r.*drv)/Z;
    end
    T_t(k) = Tk;  Q_t(k) = Qk;  immersedArea(k) = Ak;
end

cyc.theta_rad = th;
cyc.theta_deg = th*U.rad2deg;
cyc.T_inst_N  = T_t;
cyc.Q_inst_Nm = Q_t;
cyc.T_mean_N  = mean(T_t);
cyc.T_max_N   = max(T_t);
cyc.T_min_N   = min(T_t);
cyc.Q_mean_Nm = mean(Q_t);
cyc.Q_max_Nm  = max(Q_t);
cyc.Q_min_Nm  = min(Q_t);
cyc.Q_amplitude_Nm = 0.5*(max(Q_t)-min(Q_t));
cyc.T_amplitude_N  = 0.5*(max(T_t)-min(T_t));
if cyc.Q_mean_Nm > 1e-9
    cyc.Q_cyclicRatio = cyc.Q_amplitude_Nm/cyc.Q_mean_Nm;
else
    cyc.Q_cyclicRatio = NaN;
end
cyc.bladeRate_Hz = bemRes.n*Z;
cyc.immersedFirstMoment = immersedArea;
cyc.note = ['Level-2 reconstruction from the cycle-averaged solution. It captures ', ...
            'the kinematics of immersion, NOT the unsteady hydrodynamics of water ', ...
            'entry (added mass, impact, spray sheet). Peak loads are therefore ', ...
            'UNDERESTIMATED. CFD/experiment required.'];
end

% =========================================================================
function d = angdiff(a, b)
%ANGDIFF  Positive angular distance from b to a, wrapped to [0, 2*pi).
d = mod(a - b, 2*pi);
end

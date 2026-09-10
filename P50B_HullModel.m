function Hull = P50B_HullModel(varargin)
%P50B_HULLMODEL  Resistance of the Monaco catamaran hull versus speed.
%
%   Hull = P50B_HullModel() builds the hull geometry and the resistance
%   model from params/volare_params.json and returns a struct carrying
%   both the numbers and the functions that evaluate them.
%
%   OPTIONS
%     "Displacement_kg"  override the floating mass
%     "Model"            "supplied" (default) or "parametric"
%     "Verbose"          logical, default false
%
%   WHY THIS EXISTS
%   ---------------
%   Until now the MATLAB side of this project had no boat in it. Missions
%   were written as shaft-power time series and motor speed was inferred
%   from a cube law, so nothing in MATLAB could answer "how fast does it
%   go", "how far does it get", or ENERGY_REQ_37, "does it make 3 knots".
%   Those questions lived only in the Python model, and a question that
%   only one of two independent models can answer is a question that
%   nothing cross-checks.
%
%   This is the MATLAB counterpart of python/volare/boat.py, evaluated
%   from the same parameters, so tools/crosscheck.py can hold the two
%   against each other the way it already does for the pack.
%
%   TWO MODELS, AND WHY THE DEFAULT CHANGED
%   ---------------------------------------
%   "supplied"    the MEBC Energy Class resistance curve, five measured
%                 points from 0 to 20 knots at 250 kg, held in
%                 hydro.resistance_bare_hull_N. Interpolated with a
%                 shape-preserving spline. This is the default.
%
%   "parametric"  the original estimate: Holtrop wetted surface, ITTC
%                 friction, a wave-making hump and a Savitsky planing
%                 term. Retained for comparison and for speeds past the
%                 end of the supplied data.
%
%   They disagree badly, and the supplied data is right:
%
%        speed      supplied      parametric
%         5 kn          89 N          ~470 N
%        10 kn         212 N          ~640 N
%        15 kn         381 N          ~720 N
%        20 kn         624 N          ~815 N
%
%   The parametric model was applying a PLANING model to a hull that
%   does not plane. Each demihull is about 5 m by 0.45 m -- a slender
%   semi-displacement form with an L/B near 11, whose resistance climbs
%   smoothly with no wave-making hump worth the name. The Savitsky term
%   alone contributed a flat 585 N above 20 km/h that simply is not
%   there, and it was the largest single error in the model.
%
%   Both are still evaluated, and Verbose prints the two side by side,
%   because a model that quietly replaced one answer with another would
%   have hidden the very disagreement that was worth finding.
%
%   WHAT THE SUPPLIED CURVE DOES NOT COVER
%   --------------------------------------
%   It stops at 20 knots, and it is for a 250 kg boat. Our floating mass
%   is 315 kg. Above the last point, and away from that displacement,
%   this function extrapolates and says so -- see Hull.Extrapolating.
%
%   Air resistance is added on top of the supplied curve in both modes:
%   the curve is a towing figure for the hulls, and the cockpit and the
%   two organiser crossbeams are in the air either way.
%
%   See also P50B_Propeller, P50B_BoatDynamics, P50B_BoatPerformance.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct("Displacement_kg",[],"Model","supplied","Verbose",false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_HullModel:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% =========================================================
    % PHYSICAL CONSTANTS
    %
    % Seawater, not fresh. Monaco is the Mediterranean: 1025 kg/m3
    % against 998 is 2.7% on every hydrodynamic force in the model.
    %% =========================================================

    C = P50B_HydroConstants();

    %% =========================================================
    % PARAMETERS
    %% =========================================================

    Pt = P50B_LoadParams();
    P  = P50B_LoadParams("Plain",true);

    B = P.boat;

    displacement_kg = B.displacement_kg;

    if ~isempty(opts.Displacement_kg)
        displacement_kg = opts.Displacement_kg;
    end

    %% =========================================================
    % GEOMETRY
    %
    % Wetted surface from the Holtrop approximation, per demihull,
    % multiplied by the number of hulls. This is the single
    % largest term in frictional resistance and therefore the
    % geometric quantity worth replacing with a real number from
    % the Annex II drawings or an STL first.
    %% =========================================================

    Lwl = B.Lwl_m;
    Bwl = B.Bwl_m;
    T   = B.hull_draft_m;
    Cb  = B.block_coefficient;

    S_perHull = Lwl * (2*T + Bwl) * sqrt(Cb) * ...
                (0.453 + 0.4425*Cb - 0.2862*Cb^2);

    wettedArea_m2 = S_perHull * B.n_hulls;

    volume_m3 = displacement_kg / C.RhoSeawater;

    G = struct();

    G.WaterlineLength_m   = Lwl;
    G.WaterlineBeam_m     = Bwl;
    G.Draft_m             = T;
    G.NumberOfHulls       = B.n_hulls;
    G.BlockCoefficient    = Cb;
    G.PrismaticCoefficient = B.prismatic_coefficient;
    G.WettedArea_m2       = wettedArea_m2;
    G.WettedAreaPerHull_m2 = S_perHull;
    G.Displacement_kg     = displacement_kg;
    G.DisplacedVolume_m3  = volume_m3;
    G.OverallLength_m     = B.loa_m;
    G.OverallWidth_m      = B.boa_m;
    G.Freeboard_m         = B.freeboard_m;

    G.FrontalArea_m2      = B.cockpit_frontal_area_m2;
    G.CockpitCd           = B.cockpit_Cd;
    G.BeamDiameter_m      = B.beam_diameter_m;
    G.BeamSpan_m          = B.beam_span_m;
    G.NumberOfBeams       = B.n_beams;
    G.BeamCd              = B.beam_Cd;
    G.BeamsFaired         = logical(B.beams_faired);

    %% ---------------------------------------------------------
    % Crossbeam frontal area
    %
    % ENERGY_REQ_3 forbids modifying the beams the organiser
    % supplies, so a fairing would have to be a non-structural
    % clip-on and would need the Technical Committee's agreement.
    % The unfaired case is therefore the default, and the faired
    % case is kept so the value of asking can be quantified.
    %% ---------------------------------------------------------

    if G.BeamsFaired
        beamArea_m2 = 0;
        beamCd      = 0.35;
    else
        beamArea_m2 = G.NumberOfBeams * G.BeamDiameter_m * G.BeamSpan_m;
        beamCd      = G.BeamCd;
    end

    G.BeamFrontalArea_m2 = beamArea_m2;

    %% =========================================================
    % COEFFICIENTS
    %% =========================================================

    Ca        = B.correlation_allowance;
    kForm     = B.form_factor_k;
    appendage = B.appendage_factor;
    spray     = B.spray_factor;
    FnTrans   = B.planing_transition_Fn;
    planingLD = B.planing_LD;
    wettedFrac = B.planing_wetted_frac;
    aeroOn    = logical(B.aero_enabled);

    mode = lower(string(opts.Model));

    if ~ismember(mode,["supplied","parametric"])
        error("P50B_HullModel:UnknownModel", ...
            "Model must be 'supplied' or 'parametric', not '%s'.",mode);
    end

    useSupplied = mode == "supplied";

    %% =========================================================
    % RESISTANCE COMPONENTS
    %
    % Written as nested closures over the values above so that a
    % Hull struct is self-contained: pass it around and it carries
    % its own physics, with no dependence on the caller having
    % loaded the same parameters.
    %% =========================================================

    froude = @(v) abs(v) ./ sqrt(C.Gravity * max(volume_m3,1e-9)^(1/3));

    blend = @(v) 1 ./ (1 + exp(-(froude(v) - FnTrans) * 5.0));

    function R = frictional(v)

        v = max(abs(v),1e-3);

        Re = v * Lwl / C.KinematicViscosity;

        Cf = 0.075 ./ (log10(max(Re,1e3)) - 2.0).^2;

        Ct = Cf * (1 + kForm) + Ca;

        R = 0.5 * C.RhoSeawater * Ct * wettedArea_m2 .* v.^2 * appendage;

    end

    function R = residuary(v)

        Fn = froude(v);

        hump = 0.55 * exp(-((Fn - 1.05)/0.42).^2);

        tail = 0.10 ./ (1 + exp((Fn - FnTrans) * 4.0));

        Cr = hump + tail;

        R = 0.5 * C.RhoSeawater * Cr * volume_m3^(2/3) .* v.^2 * 0.35;

    end

    function R = planing(v)

        W = displacement_kg * C.Gravity;

        R = blend(v) .* (W / planingLD) * spray;

    end

    function R = aerodynamic(v,vWind)

        if nargin < 2 || isempty(vWind)
            vWind = B.wind_speed_ms;
        end

        if ~aeroOn
            R = zeros(size(v));
            return;
        end

        va = v + vWind;

        R = 0.5 * C.RhoAir * va.^2 * ...
            (G.CockpitCd * G.FrontalArea_m2 + beamCd * beamArea_m2);

    end

    function R = parametricHydro(v)

        b = blend(v);

        R = (1 - b) .* (frictional(v) + residuary(v)) + ...
            planing(v) + ...
            b .* frictional(v) * wettedFrac;

    end

    %% ---------------------------------------------------------
    % The supplied curve
    %
    % Five points, bare hull, 250 kg. Interpolated with pchip
    % rather than a cubic spline: a spline through five points
    % that all curve the same way will overshoot between them,
    % and a resistance curve that dips below its neighbours is
    % not a physical answer.
    %
    % PAST THE LAST POINT
    %
    % Two estimates are available above 20 knots and neither is
    % data, so the LARGER is used.
    %
    % The first is a power law fitted to the top two supplied
    % points. On its own it would understate: the local exponent
    % of the supplied curve is not constant, it climbs steadily
    % with speed --
    %
    %       5 to 10 kn    v^1.25
    %      10 to 15 kn    v^1.45
    %      15 to 20 kn    v^1.72
    %
    % -- so freezing it at 1.72 assumes the hull stops getting
    % harder to push exactly where the data stops, which is a
    % coincidence nobody should bank on.
    %
    % The second is the parametric model, which is too high in
    % the displacement range but is at least built from physics
    % rather than from the end of a table.
    %
    % Taking the maximum errs towards more drag, which means less
    % range and a lower top speed. That is the correct direction
    % to be wrong in for a boat whose whole event is decided by
    % whether the energy lasts.
    %% ---------------------------------------------------------

    vCurve_kn = double(P.hydro.resistance_speed_kn(:))';
    RCurve_N  = double(P.hydro.resistance_bare_hull_N(:))';

    vCurve_ms = vCurve_kn / C.KnotsPerMs;

    vMaxValid_ms = P.hydro.resistance_max_valid_kn / C.KnotsPerMs;

    %% Power-law tail, fitted to the top two supplied points.
    tailExp = log(RCurve_N(end)/RCurve_N(end-1)) / ...
              log(vCurve_ms(end)/vCurve_ms(end-1));

    tailCoeff = RCurve_N(end) / vCurve_ms(end)^tailExp;

    %% Drive-leg and appendage drag, scaled from the design point.
    legDrag_N_at_design = P.hydro.drive_leg_drag_N_at_20kn;

    legCoeff = legDrag_N_at_design / vMaxValid_ms^2;

    function R = suppliedHydro(v)

        v = abs(v);

        R = zeros(size(v));

        inRange = v <= vMaxValid_ms;

        if any(inRange(:))
            R(inRange) = interp1(vCurve_ms,RCurve_N,v(inRange),"pchip");
        end

        if any(~inRange(:))
            tail = tailCoeff * v(~inRange).^tailExp;
            R(~inRange) = max(tail, parametricHydro(v(~inRange)));
        end

        %% Drive leg, which the supplied bare-hull curve excludes.
        R = R + legCoeff * v.^2;

    end

    function tf = extrapolating(v)

        tf = any(abs(v) > vMaxValid_ms);

    end

    function R = total(v,vWind)

        if nargin < 2 || isempty(vWind)
            vWind = B.wind_speed_ms;
        end

        if useSupplied
            R = suppliedHydro(v) + aerodynamic(v,vWind);
        else
            R = parametricHydro(v) + aerodynamic(v,vWind);
        end

    end

    %% =========================================================
    % ASSEMBLE
    %% =========================================================

    Hull = struct();

    Hull.Geometry = G;
    Hull.Constants = C;

    Hull.Froude          = froude;
    Hull.PlaningBlend    = blend;
    Hull.Frictional_N    = @frictional;
    Hull.Residuary_N     = @residuary;
    Hull.Planing_N       = @planing;
    Hull.Aerodynamic_N   = @aerodynamic;
    Hull.Resistance_N    = @total;
    Hull.EffectivePower_W = @(v,varargin) total(v,varargin{:}) .* v;

    Hull.Model              = mode;
    Hull.SuppliedHydro_N    = @suppliedHydro;
    Hull.ParametricHydro_N  = @parametricHydro;
    Hull.Extrapolating      = @extrapolating;
    Hull.MaxValidSpeed_ms   = vMaxValid_ms;
    Hull.MaxValidSpeed_kmh  = vMaxValid_ms * C.KmhPerMs;
    Hull.MaxValidSpeed_knots = P.hydro.resistance_max_valid_kn;
    Hull.CurveSpeed_knots   = vCurve_kn;
    Hull.CurveResistance_N  = RCurve_N;
    Hull.TailExponent       = tailExp;
    Hull.CurveDisplacement_kg = P.hydro.resistance_displacement_kg;

    %% ---------------------------------------------------------
    % The curve was measured at 250 kg and the boat floats at
    % 315 kg. Flagged rather than corrected: scaling resistance
    % for displacement needs a form-factor assumption this model
    % has no basis for, and the hydrodynamics team's own report
    % says the heavier case cannot be considered validated.
    %% ---------------------------------------------------------

    Hull.DisplacementMatchesCurve = ...
        abs(displacement_kg - Hull.CurveDisplacement_kg) < 1.0;

    Hull.DisplacementExcess_kg = ...
        displacement_kg - Hull.CurveDisplacement_kg;

    %% ---------------------------------------------------------
    % Provenance for the report
    %% ---------------------------------------------------------

    Hull.P = struct( ...
        "Lwl_m",              Pt.boat.Lwl_m, ...
        "Bwl_m",              Pt.boat.Bwl_m, ...
        "Draft_m",            Pt.boat.hull_draft_m, ...
        "Displacement_kg",    Pt.boat.displacement_kg, ...
        "BlockCoefficient",   Pt.boat.block_coefficient, ...
        "CorrelationAllowance", Pt.boat.correlation_allowance, ...
        "FormFactor",         Pt.boat.form_factor_k, ...
        "AppendageFactor",    Pt.boat.appendage_factor, ...
        "SprayFactor",        Pt.boat.spray_factor, ...
        "PlaningTransitionFn", Pt.boat.planing_transition_Fn, ...
        "PlaningLD",          Pt.boat.planing_LD, ...
        "PlaningWettedFraction", Pt.boat.planing_wetted_frac, ...
        "CockpitCd",          Pt.boat.cockpit_Cd, ...
        "CockpitFrontalArea_m2", Pt.boat.cockpit_frontal_area_m2, ...
        "BeamCd",             Pt.boat.beam_Cd);

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose

        fprintf("\n");
        fprintf("================================================================\n");
        fprintf(" HULL MODEL\n");
        fprintf("================================================================\n");

        fprintf("\nGEOMETRY\n");
        fprintf("  Waterline length         : %.2f m per demihull\n",Lwl);
        fprintf("  Waterline beam           : %.2f m\n",Bwl);
        fprintf("  Draft                    : %.3f m\n",T);
        fprintf("  Hulls                    : %d\n",G.NumberOfHulls);
        fprintf("  Wetted surface           : %.2f m2 total\n",wettedArea_m2);
        fprintf("  Floating mass            : %.1f kg\n",displacement_kg);
        fprintf("  Displaced volume         : %.4f m3\n",volume_m3);

        fprintf("\nAIR\n");
        fprintf("  Cockpit frontal area     : %.3f m2 at Cd %.2f\n", ...
            G.FrontalArea_m2,G.CockpitCd);
        if G.BeamsFaired
            fairedNote = "  (faired -- needs Technical Committee agreement)";
        else
            fairedNote = "  (bare organiser tubes)";
        end

        fprintf("  Crossbeam frontal area   : %.3f m2 at Cd %.2f%s\n", ...
            beamArea_m2,beamCd,fairedNote);

        fprintf("\nRESISTANCE MODEL          : %s\n",upper(mode));
        fprintf("  Supplied curve valid to  : %.0f knots (%.1f km/h) " + ...
            "at %.0f kg\n", ...
            Hull.MaxValidSpeed_knots,Hull.MaxValidSpeed_kmh, ...
            Hull.CurveDisplacement_kg);

        if ~Hull.DisplacementMatchesCurve
            fprintf("  NOTE: the boat floats at %.0f kg, %+.0f kg from the\n", ...
                displacement_kg,Hull.DisplacementExcess_kg);
            fprintf("        condition the curve was measured at. Not " + ...
                "corrected for.\n");
        end

        fprintf("\nRESISTANCE AT SAMPLE SPEEDS\n");
        fprintf("  %6s %6s %11s %11s %9s %8s\n", ...
            "knots","km/h","supplied N","parametric","air N","source");

        for vkn = [5 10 15 20 25 30]

            v = vkn / C.KnotsPerMs;

            if vkn <= Hull.MaxValidSpeed_knots
                src = "data";
            else
                src = "EXTRAP";
            end

            fprintf("  %6.0f %6.1f %11.0f %11.0f %9.0f %8s\n", ...
                vkn, v*C.KmhPerMs, suppliedHydro(v), parametricHydro(v), ...
                aerodynamic(v), src);

        end

        fprintf("\n  The parametric column is the model this project used\n");
        fprintf("  before the supplied curve arrived. The gap is a planing\n");
        fprintf("  term applied to a hull that does not plane.\n");

        fprintf("================================================================\n\n");

    end

end

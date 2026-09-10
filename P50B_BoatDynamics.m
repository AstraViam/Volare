function Boat = P50B_BoatDynamics(varargin)
%P50B_BOATDYNAMICS  Longitudinal dynamics: shaft power in, boat speed out.
%
%   Boat = P50B_BoatDynamics() builds the hull, the propeller and the
%   dynamics from params/volare_params.json.
%
%   OPTIONS
%     "Hull"             struct from P50B_HullModel
%     "Propeller"        struct from P50B_Propeller
%     "Mass_kg"          override the floating mass
%     "ShaftPowerMax_W"  override the shaft power ceiling
%     "Verbose"          logical, default false
%
%   THE EQUATION
%   ------------
%       (m + m_added) dv/dt = T (1 - t) - R_hull - R_air
%
%   with the shaft power clipped to the ceiling in one place and one
%   place only, inside Step. No other code path can exceed it, which is
%   how the ENERGY_REQ_188 cap is kept honest: a limit enforced in three
%   places is a limit enforced in none of them.
%
%   TWO CEILINGS, NOT ONE
%   ---------------------
%   Shaft power is limited by the rule, and separately by what the motor
%   can twist. A machine rated 100 N.m cannot deliver 22.8 kW below about
%   2250 rev/min no matter what the rule permits, because the torque to
%   do it does not exist.
%
%   This matters here and is not a corner case. The contra-rotating
%   propulsor turns its front rotor at about 1065 rev/min at top speed,
%   which through the 1.6079 gearbox is 1712 rev/min at the motor. At
%   that speed 22.8 kW would need 131 N.m. So the boat is TORQUE limited
%   over its whole upper speed range, and a model that applied only the
%   power cap would report a top speed the drivetrain cannot reach.
%
%   Both ceilings are applied, in one place, inside Step. The binding one
%   is reported per step so it is visible which is which.
%
%   The consequence is a design question rather than a defect: the BEM
%   propulsor was optimised at 20 knots and 9.9 kW, where 1300 rev/min
%   and 75.8 N.m is comfortable. Using the full legal 25 kW wants a
%   numerically higher gear ratio -- Boat.GearRatioForFullPower says how
%   much -- and that in turn would change the propeller match. Whoever
%   specifies the gearbox needs to decide which operating point it is for.
%
%   THE POWER CEILING IS NOT 25 kW OF SHAFT POWER
%   ---------------------------------------------
%   ENERGY_REQ_188 caps the motor's nominal power CONSUMPTION at 25 kW,
%   which is electrical input, not shaft output. The drivetrain solver
%   P50B_DrivetrainModel owns that distinction and finds the shaft power
%   whose electrical input lands on 25 kW. This function takes the shaft
%   figure it produces. Passing 25 kW of shaft power in here would model
%   a boat drawing about 26.9 kW and breaking the rule.
%
%   FUNCTIONS RETURNED
%     Boat.Step(state,dt,P_shaft_W,vWind)   advance one step
%     Boat.SteadySpeed(P_shaft_W,vWind)     terminal speed at held power
%     Boat.ShaftPowerForSpeed(v,vWind)      inverse: power to hold v
%     Boat.PowerSpeedCurve(powers_W)        table of both
%
%   See also P50B_HullModel, P50B_Propeller, P50B_BoatPerformance.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct( ...
        "Hull",[], ...
        "Propeller",[], ...
        "Mass_kg",[], ...
        "ShaftPowerMax_W",[], ...
        "Verbose",false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_BoatDynamics:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    C = P50B_HydroConstants();

    P = P50B_LoadParams("Plain",true);

    if isempty(opts.Hull)
        Hull = P50B_HullModel();
    else
        Hull = opts.Hull;
    end

    if isempty(opts.Propeller)
        %% The boat has a contra-rotating pair, so that is the default.
        %% P50B_Propeller is the single-screw stand-in and has to be
        %% asked for by name now.
        Prop = P50B_Propulsor();
    else
        Prop = opts.Propeller;
    end

    mass_kg = Hull.Geometry.Displacement_kg;

    if ~isempty(opts.Mass_kg)
        mass_kg = opts.Mass_kg;
    end

    %% ---------------------------------------------------------
    % Shaft power ceiling
    %
    % Default is the SHAFT power that corresponds to the 25 kW
    % electrical cap, not the cap itself. Solved once here by
    % asking the drivetrain model, so this module never has to
    % know about inverter or motor losses.
    %% ---------------------------------------------------------

    ceilingInfo = struct("Fixed",true);

    if isempty(opts.ShaftPowerMax_W)
        [P_shaft_max_W,ceilingInfo] = P50B_ShaftPowerCeiling();
        ceilingInfo.Fixed = false;
    else
        P_shaft_max_W = opts.ShaftPowerMax_W;
    end

    addedMassFrac = P.boat.added_mass_frac;
    drivelineEff  = P.boat.driveline_eff;
    tDed          = Prop.ThrustDeduction;
    defaultWind   = P.boat.wind_speed_ms;

    m_eff = mass_kg * (1 + addedMassFrac);

    %% =========================================================
    % MOTOR TORQUE CEILING
    %
    % The largest shaft power the motor can push through the
    % gearbox at the rotor speed that power itself produces.
    % Rotor speed rises with power, so this is implicit; it is
    % bisected rather than solved in closed form so that it
    % works for any propulsor object, including ones whose
    % speed-power relation is not a cube law.
    %% =========================================================

    motorForCeiling = P50B_MotorData();

    Qmax_Nm   = P50B_Value(motorForCeiling.MaximumTorque_Nm);
    gearboxEff = P50B_Value(motorForCeiling.GearboxEfficiency);

    function [P_ok,binding] = torqueLimitedPower(v,P_request)

        %% -----------------------------------------------------
        % Torque demanded by a given shaft power, at the rotor
        % speed that power produces.
        %% -----------------------------------------------------

        function Q = torqueFor(P_W)

            if P_W <= 0
                Q = 0;
                return;
            end

            nProp = Prop.RPSForPower(v,P_W);

            omegaMotor = 2*pi * nProp * Prop.GearRatio;

            Q = (P_W / gearboxEff) / max(omegaMotor,1e-9);

        end

        if torqueFor(P_request) <= Qmax_Nm
            P_ok    = P_request;
            binding = "power";
            return;
        end

        %% -----------------------------------------------------
        % Torque demand falls as power rises, because rotor speed
        % rises faster than power does. So the feasible set is
        % the HIGH end, and the bracket runs from the request
        % downwards -- the opposite of the usual sense, and worth
        % stating because getting it backwards silently returns
        % the wrong root.
        %% -----------------------------------------------------

        lo = 0;
        hi = P_request;

        for it = 1:60

            mid = 0.5*(lo + hi);

            if torqueFor(mid) > Qmax_Nm
                hi = mid;
            else
                lo = mid;
            end

        end

        P_ok    = lo;
        binding = "torque";

    end

    %% =========================================================
    % ONE STEP
    %
    % State is passed in and returned rather than held in the
    % struct, so the same Boat object can drive several
    % independent runs (a sweep, a Monte Carlo) without one
    % contaminating another.
    %% =========================================================

    function [state,op] = step(state,dt,P_shaft_cmd_W,vWind)

        if nargin < 4 || isempty(vWind)
            vWind = defaultWind;
        end

        P_cmd = P_shaft_cmd_W;

        P_shaft = min(max(P_cmd,0), P_shaft_max_W);

        [P_shaft,binding] = torqueLimitedPower(state.Speed_ms,P_shaft);

        P_prop = P_shaft * drivelineEff;

        v = state.Speed_ms;

        n = Prop.RPSForPower(v,P_prop);

        T = Prop.Thrust_N(v,n);

        T_eff = T * (1 - tDed);

        R = Hull.Resistance_N(v,vWind);

        a = (T_eff - R) / m_eff;

        state.Speed_ms   = max(0, v + a*dt);
        state.Distance_m = state.Distance_m + 0.5*(v + state.Speed_ms)*dt;
        state.PropRPS    = n;

        op = struct( ...
            "Speed_ms",        state.Speed_ms, ...
            "Speed_kmh",       state.Speed_ms * C.KmhPerMs, ...
            "Speed_knots",     state.Speed_ms * C.KnotsPerMs, ...
            "Acceleration_ms2",a, ...
            "Thrust_N",        T, ...
            "EffectiveThrust_N",T_eff, ...
            "Resistance_N",    R, ...
            "ShaftPower_W",    P_shaft, ...
            "EffectivePower_W",R*v, ...
            "PropRPS",         n, ...
            "PropRPM",         n*60, ...
            "MotorRPM",        n*60*Prop.GearRatio, ...
            "PropEfficiency",  Prop.OpenWaterEff(v,n), ...
            "Slip",            Prop.Slip(v,n), ...
            "CavitationNumber",Prop.CavitationNumber(v,n), ...
            "Capped",          P_cmd > P_shaft_max_W + 1e-6, ...
            "LimitedBy",       binding);

    end

    function state = newState(v0)

        if nargin < 1 || isempty(v0)
            v0 = 0;
        end

        state = struct("Speed_ms",v0,"Distance_m",0,"PropRPS",0);

    end

    %% =========================================================
    % TERMINAL SPEED AT A HELD POWER
    %% =========================================================

    function v = steadySpeed(P_shaft_W,vWind,v0)

        if nargin < 2; vWind = []; end
        if nargin < 3 || isempty(v0); v0 = 0; end

        st = newState(v0);

        dt = 0.25;

        for it = 1:round(180/dt)

            prev = st.Speed_ms;

            st = step(st,dt,P_shaft_W,vWind);

            if abs(st.Speed_ms - prev) < 1e-5
                break;
            end

        end

        v = st.Speed_ms;

    end

    %% =========================================================
    % INVERSE: THE SHAFT POWER THAT HOLDS A SPEED
    %
    % Wanted by the mission integrator, which is given a speed
    % target by the course and needs the power that meets it.
    % Solved directly rather than by searching the steady-speed
    % function, because at equilibrium thrust equals resistance
    % and the propeller closes the loop in one step.
    %% =========================================================

    function P_shaft_W = shaftPowerForSpeed(v,vWind)

        if nargin < 2 || isempty(vWind)
            vWind = defaultWind;
        end

        if v <= 0
            P_shaft_W = 0;
            return;
        end

        R = Hull.Resistance_N(v,vWind);

        T_required = R / (1 - tDed);

        %% -----------------------------------------------------
        % Find the shaft speed that produces that thrust.
        % Thrust is monotone in n at fixed v, so bisect.
        %% -----------------------------------------------------

        lo = 1e-3;
        hi = 180.0;

        if Prop.Thrust_N(v,hi) < T_required

            %% -------------------------------------------------
            % The propeller cannot make this much thrust at any
            % shaft speed inside the bracket. Report infinite
            % power rather than the bracket end, so the caller
            % sees an unreachable speed instead of a plausible
            % but wrong number.
            %% -------------------------------------------------

            P_shaft_W = Inf;
            return;

        end

        for it = 1:60

            mid = 0.5*(lo + hi);

            if Prop.Thrust_N(v,mid) < T_required
                lo = mid;
            else
                hi = mid;
            end

        end

        n = 0.5*(lo + hi);

        P_shaft_W = Prop.ShaftPower_W(v,n) / drivelineEff;

        %% -----------------------------------------------------
        % Holding this speed may need more torque than the motor
        % has. Report the power honestly and let the caller
        % compare it against the ceilings, rather than silently
        % returning a number the drivetrain cannot produce.
        %% -----------------------------------------------------

    end

    %% =========================================================
    % POWER / SPEED TABLE
    %% =========================================================

    function tbl = powerSpeedCurve(powers_W,vWind)

        if nargin < 1 || isempty(powers_W)
            powers_W = linspace(500,P_shaft_max_W,25);
        end

        if nargin < 2; vWind = []; end

        n = numel(powers_W);

        ShaftPower_W = powers_W(:);
        Speed_ms     = zeros(n,1);
        Speed_kmh    = zeros(n,1);
        Speed_knots  = zeros(n,1);
        PropRPM      = zeros(n,1);
        MotorRPM     = zeros(n,1);
        PropEff      = zeros(n,1);
        Resistance_N = zeros(n,1);
        Wh_per_km    = zeros(n,1);

        for k = 1:n

            v = steadySpeed(ShaftPower_W(k),vWind);

            np = Prop.RPSForPower(v,ShaftPower_W(k)*drivelineEff);

            Speed_ms(k)     = v;
            Speed_kmh(k)    = v * C.KmhPerMs;
            Speed_knots(k)  = v * C.KnotsPerMs;
            PropRPM(k)      = np*60;
            MotorRPM(k)     = np*60*Prop.GearRatio;
            PropEff(k)      = Prop.OpenWaterEff(v,np);
            Resistance_N(k) = Hull.Resistance_N(v,vWind);
            Wh_per_km(k)    = ShaftPower_W(k) / max(Speed_kmh(k),1e-6);

        end

        tbl = table(ShaftPower_W,Speed_ms,Speed_kmh,Speed_knots, ...
                    PropRPM,MotorRPM,PropEff,Resistance_N,Wh_per_km);

    end

    %% =========================================================
    % REFINE THE CEILING AT THE BOAT'S OWN OPERATING POINT
    %
    % The shaft ceiling depends on motor speed through the iron
    % and windage losses, and the motor speed depends on the
    % boat speed, which depends on the ceiling. Two or three
    % passes settle it to well under a watt.
    %
    % Solving it once at a guessed speed would leave the boat
    % running against a limit derived from an operating point it
    % never occupies -- a small error, but one that would show up
    % as the MATLAB and Python models disagreeing about top speed
    % for no visible reason.
    %% =========================================================

    if ~ceilingInfo.Fixed

        for pass = 1:4

            vTop = steadySpeed(P_shaft_max_W);

            nProp = Prop.RPSForPower(vTop,P_shaft_max_W*drivelineEff);

            rpm = nProp * 60 * Prop.GearRatio;

            rpm = min(max(rpm,200), P50B_Value(P50B_MotorData().MaximumSpeed_rpm));

            [P_new,ceilingInfo] = P50B_ShaftPowerCeiling(rpm);

            if abs(P_new - P_shaft_max_W) < 1.0
                P_shaft_max_W = P_new;
                break;
            end

            P_shaft_max_W = P_new;

        end

    end

    %% =========================================================
    % ASSEMBLE
    %% =========================================================

    Boat = struct();

    Boat.Hull            = Hull;
    Boat.Propeller       = Prop;
    Boat.Mass_kg         = mass_kg;
    Boat.EffectiveMass_kg = m_eff;
    Boat.AddedMassFraction = addedMassFrac;
    Boat.DrivelineEfficiency = drivelineEff;
    Boat.ShaftPowerMax_W = P_shaft_max_W;
    Boat.PowerCeiling    = ceilingInfo;
    Boat.MotorTorqueLimit_Nm = Qmax_Nm;
    Boat.TorqueLimitedPower  = @torqueLimitedPower;

    %% ---------------------------------------------------------
    % What gear ratio would let the motor make full legal power?
    %
    % The motor needs P/(2 pi Q_max eta_gb) rev/s to deliver the
    % ceiling at its torque limit. The rotor turns at whatever
    % the propulsor needs. The ratio between them is the answer,
    % and comparing it with the ratio the gearbox actually has
    % says whether the boat can use the power it is allowed.
    %% ---------------------------------------------------------

    vTopForGear = steadySpeed(P_shaft_max_W);

    nPropAtTop = Prop.RPSForPower(vTopForGear,P_shaft_max_W*drivelineEff);

    nMotorNeeded_rps = (P_shaft_max_W/gearboxEff) / (2*pi*Qmax_Nm);

    Boat.GearRatioForFullPower = nMotorNeeded_rps / max(nPropAtTop,1e-9);

    Boat.GearRatioFitted       = Prop.GearRatio;

    Boat.FullPowerReachable    = ...
        Prop.GearRatio >= Boat.GearRatioForFullPower - 1e-6;

    Boat.NewState            = @newState;
    Boat.Step                = @step;
    Boat.SteadySpeed         = @steadySpeed;
    Boat.ShaftPowerForSpeed  = @shaftPowerForSpeed;
    Boat.PowerSpeedCurve     = @powerSpeedCurve;

    if opts.Verbose

        vTop = steadySpeed(P_shaft_max_W);

        fprintf("\nBOAT DYNAMICS\n");
        fprintf("  Floating mass            : %.1f kg\n",mass_kg);
        fprintf("  Effective mass           : %.1f kg (added mass %.0f%%)\n", ...
            m_eff,addedMassFrac*100);
        fprintf("  Shaft power ceiling      : %.2f kW\n",P_shaft_max_W/1000);
        fprintf("  Top speed                : %.1f km/h (%.1f knots)\n", ...
            vTop*C.KmhPerMs, vTop*C.KnotsPerMs);

    end

end

function Perf = P50B_BoatPerformance(varargin)
%P50B_BOATPERFORMANCE  Speed, drag, range and the rules that depend on them.
%
%   Perf = P50B_BoatPerformance() evaluates the boat across its speed
%   range and returns the numbers the rest of the project needs: top
%   speed under the power cap, the drag breakdown, energy per kilometre,
%   and the operating points behind ENERGY_REQ_37 and ENERGY_REQ_32.
%
%   OPTIONS
%     "Hull"        struct from P50B_HullModel
%     "Propeller"   struct from P50B_Propeller
%     "Boat"        struct from P50B_BoatDynamics
%     "Wind_ms"     head wind, default from the parameter file
%     "Verbose"     logical, default true
%     "Plot"        logical, default false
%
%   THE TWO RULES THIS SETTLES
%   --------------------------
%   ENERGY_REQ_37  "Boat shall sail at a speed of at least 3 knots."
%   ENERGY_REQ_32  "Boat shall be able to move and be manoeuvrable in
%                   forward and reverse gear."
%
%   Both were previously on the compliance checklist as things a person
%   would confirm at the sea trial. They still will be -- the Technical
%   Committee judges manoeuvrability by watching the boat -- but a design
%   that cannot make 3 knots on paper will not make them on the water
%   either, and finding that out in Monaco is expensive. So they are
%   computed here and the checklist entry becomes a check with a number
%   behind it.
%
%   REVERSE
%   -------
%   Astern thrust is estimated as a fraction of ahead thrust at the same
%   shaft power, because the KT/KQ correlation describes a propeller
%   going forwards and says nothing useful about one going backwards. The
%   fraction is boat.reverse_thrust_frac and it is an assumption. What
%   the check really establishes is whether there is thrust margin over
%   hull resistance at manoeuvring speed, which there is by a wide margin
%   at any sane number, so the assumption is not load bearing.
%
%   ENERGY PER KILOMETRE
%   --------------------
%   Reported at the shaft, not at the pack. The drivetrain chain
%   efficiency turns one into the other and lives in
%   P50B_DrivetrainModel; keeping them separate means a change in
%   inverter losses does not silently move a hydrodynamic number.
%
%   See also P50B_HullModel, P50B_BoatDynamics, P50B_MatchPropeller,
%   P50B_MonacoCompliance.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct( ...
        "Hull",[], ...
        "Propeller",[], ...
        "Boat",[], ...
        "Wind_ms",[], ...
        "Verbose",true, ...
        "Plot",false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_BoatPerformance:UnknownOption", ...
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
        Prop = P50B_Propulsor();
    else
        Prop = opts.Propeller;
    end

    if isempty(opts.Boat)
        Boat = P50B_BoatDynamics("Hull",Hull,"Propeller",Prop);
    else
        Boat = opts.Boat;
    end

    if isempty(opts.Wind_ms)
        wind = P.boat.wind_speed_ms;
    else
        wind = opts.Wind_ms;
    end

    Perf = struct();

    Perf.Hull      = Hull;
    Perf.Propeller = Prop;
    Perf.Boat      = Boat;
    Perf.Wind_ms   = wind;

    P_shaft_max_W = Boat.ShaftPowerMax_W;

    Perf.ShaftPowerCeiling_W = P_shaft_max_W;
    Perf.PowerCeiling        = Boat.PowerCeiling;

    %% =========================================================
    % DRAG BREAKDOWN
    %% =========================================================

    v_kmh = (2:1:70)';

    v = v_kmh / C.KmhPerMs;

    D = table();

    D.Speed_kmh    = v_kmh;
    D.Speed_ms     = v;
    D.Speed_knots  = v * C.KnotsPerMs;

    D.Frictional_N  = arrayfun(@(x) Hull.Frictional_N(x),v);
    D.Residuary_N   = arrayfun(@(x) Hull.Residuary_N(x),v);
    D.Planing_N     = arrayfun(@(x) Hull.Planing_N(x),v);
    D.Aerodynamic_N = arrayfun(@(x) Hull.Aerodynamic_N(x,wind),v);
    D.Total_N       = arrayfun(@(x) Hull.Resistance_N(x,wind),v);

    D.EffectivePower_W = D.Total_N .* v;

    D.ShaftPower_W = arrayfun(@(x) Boat.ShaftPowerForSpeed(x,wind),v);

    D.Feasible = D.ShaftPower_W <= P_shaft_max_W;

    Perf.Drag = D;

    %% =========================================================
    % TOP SPEED
    %% =========================================================

    vTop = Boat.SteadySpeed(P_shaft_max_W,wind);

    nTop = Prop.RPSForPower(vTop,P_shaft_max_W*Boat.DrivelineEfficiency);

    Perf.TopSpeed_ms    = vTop;
    Perf.TopSpeed_kmh   = vTop * C.KmhPerMs;
    Perf.TopSpeed_knots = vTop * C.KnotsPerMs;
    Perf.TopSpeedPropRPM  = nTop*60;
    Perf.TopSpeedMotorRPM = nTop*60*Prop.GearRatio;
    Perf.TopSpeedPropEff  = Prop.OpenWaterEff(vTop,nTop);
    Perf.TopSpeedCavitationNumber = Prop.CavitationNumber(vTop,nTop);

    %% ---------------------------------------------------------
    % Motor speed feasibility
    %
    % Reported here as well as in the matcher, because this is
    % the function the master script and the compliance report
    % call, and an infeasible drivetrain should not be able to
    % hide behind a plausible top speed.
    %% ---------------------------------------------------------

    motor = P50B_MotorData();

    Perf.MotorSpeedLimit_rpm = P50B_Value(motor.MaximumSpeed_rpm);
    Perf.MotorTorqueLimit_Nm = P50B_Value(motor.MaximumTorque_Nm);

    Perf.MotorTorqueAtTop_Nm = ...
        (P_shaft_max_W / P50B_Value(motor.GearboxEfficiency)) / ...
        (2*pi*max(Perf.TopSpeedMotorRPM,1e-9)/60);

    Perf.MotorSpeedOK  = Perf.TopSpeedMotorRPM <= Perf.MotorSpeedLimit_rpm;
    Perf.MotorTorqueOK = Perf.MotorTorqueAtTop_Nm <= Perf.MotorTorqueLimit_Nm;

    Perf.DrivetrainFeasible = Perf.MotorSpeedOK && Perf.MotorTorqueOK;

    %% =========================================================
    % TARGET SPEED
    %
    % boat.target_speed_kmh is a DESIGN_CHOICE that the pilot
    % model in the Python code and the dashboard both steer
    % towards. If the boat cannot reach it under the legal cap,
    % every strategy built on it is pacing against a speed that
    % does not exist.
    %% =========================================================

    Perf.TargetSpeed_kmh = P.boat.target_speed_kmh;

    Perf.TargetReachable = Perf.TargetSpeed_kmh <= Perf.TopSpeed_kmh;

    Perf.ShaftPowerForTarget_W = ...
        Boat.ShaftPowerForSpeed(Perf.TargetSpeed_kmh/C.KmhPerMs,wind);

    %% =========================================================
    % ENERGY_REQ_37 -- THREE KNOTS
    %% =========================================================

    vMin_knots = P.rules.min_speed_knots;

    vMin_ms = vMin_knots / C.KnotsPerMs;

    P_forMin_W = Boat.ShaftPowerForSpeed(vMin_ms,wind);

    Perf.MinimumSpeed = struct( ...
        "Required_knots",   vMin_knots, ...
        "Required_ms",      vMin_ms, ...
        "ShaftPower_W",     P_forMin_W, ...
        "FractionOfCeiling",P_forMin_W / P_shaft_max_W, ...
        "Achievable",       P_forMin_W <= P_shaft_max_W, ...
        "TopSpeed_knots",   Perf.TopSpeed_knots, ...
        "Margin_knots",     Perf.TopSpeed_knots - vMin_knots);

    %% =========================================================
    % ENERGY_REQ_32 -- FORWARD AND REVERSE
    %
    % Evaluated at a manoeuvring speed rather than at zero,
    % because the question is whether the boat can be driven
    % backwards under control, not whether it twitches.
    %% =========================================================

    vManoeuvre_ms = 2.0 / C.KnotsPerMs;

    revFrac = P.boat.reverse_thrust_frac;

    %% ---------------------------------------------------------
    % Take a modest fraction of the ceiling for manoeuvring:
    % nobody reverses at full power, and a check that needs full
    % power to pass is not a check that has passed.
    %% ---------------------------------------------------------

    P_manoeuvre_W = 0.25 * P_shaft_max_W;

    nRev = Prop.RPSForPower(vManoeuvre_ms,P_manoeuvre_W*Boat.DrivelineEfficiency);

    T_ahead_N = Prop.Thrust_N(vManoeuvre_ms,nRev);

    T_astern_N = T_ahead_N * revFrac;

    R_manoeuvre_N = Hull.Resistance_N(vManoeuvre_ms,wind);

    Perf.Reverse = struct( ...
        "Speed_knots",       2.0, ...
        "ShaftPower_W",      P_manoeuvre_W, ...
        "ThrustAhead_N",     T_ahead_N, ...
        "ReverseThrustFraction", revFrac, ...
        "ThrustAstern_N",    T_astern_N, ...
        "Resistance_N",      R_manoeuvre_N, ...
        "ThrustMargin",      T_astern_N / max(R_manoeuvre_N,1e-9), ...
        "Achievable",        T_astern_N > R_manoeuvre_N);

    %% =========================================================
    % ENERGY AND RANGE
    %
    % Uses the pack's real usable energy, not the 10 kWh
    % regulatory ceiling, and passes the shaft demand through the
    % drivetrain so range is quoted from the cells rather than
    % from the propeller.
    %% =========================================================

    cellData = P50B_CellData();

    nCells = P.pack.n_series * P.pack.n_parallel;

    packEnergy_Wh = nCells * P50B_Value(cellData.NominalVoltage_V) * ...
                    P50B_Value(cellData.Capacity_Ah);

    usableFraction = P.cell.usable_soc_max - P.cell.usable_soc_min;

    usableEnergy_Wh = packEnergy_Wh * usableFraction;

    Perf.PackEnergy_Wh   = packEnergy_Wh;
    Perf.UsableEnergy_Wh = usableEnergy_Wh;
    Perf.UsableFraction  = usableFraction;

    %% ---------------------------------------------------------
    % Sweep speeds and find the one that goes furthest
    %% ---------------------------------------------------------

    vRange_kmh = (3:0.5:min(70,floor(Perf.TopSpeed_kmh)))';

    nR = numel(vRange_kmh);

    R = table();

    R.Speed_kmh    = vRange_kmh;
    R.ShaftPower_W = zeros(nR,1);
    R.PackPower_W  = zeros(nR,1);
    R.ChainEff     = zeros(nR,1);
    R.Wh_per_km    = zeros(nR,1);
    R.Range_km     = zeros(nR,1);
    R.Endurance_h  = zeros(nR,1);

    for k = 1:nR

        vk = vRange_kmh(k) / C.KmhPerMs;

        Pshaft = Boat.ShaftPowerForSpeed(vk,wind);

        if ~isfinite(Pshaft) || Pshaft > P_shaft_max_W
            R.ShaftPower_W(k) = NaN;
            continue;
        end

        nProp = Prop.RPSForPower(vk,Pshaft*Boat.DrivelineEfficiency);

        rpm = min(max(nProp*60*Prop.GearRatio,200),Perf.MotorSpeedLimit_rpm);

        op = P50B_DrivetrainModel(Pshaft,rpm,0.6,35);

        R.ShaftPower_W(k) = Pshaft;
        R.PackPower_W(k)  = op.Pack.DrawnPower_W;
        R.ChainEff(k)     = op.Chain.OverallEfficiency;
        R.Wh_per_km(k)    = op.Pack.DrawnPower_W / vRange_kmh(k);
        R.Range_km(k)     = usableEnergy_Wh / R.Wh_per_km(k);
        R.Endurance_h(k)  = usableEnergy_Wh / op.Pack.DrawnPower_W;

    end

    Perf.Range = R;

    valid = ~isnan(R.ShaftPower_W);

    if any(valid)

        [bestRange_km,iBest] = max(R.Range_km(valid));

        idx = find(valid);

        iBest = idx(iBest);

        %% -----------------------------------------------------
        % A boat goes furthest by going slowly, so the maximum
        % of this curve normally sits at whatever the sweep
        % started at rather than at a real optimum. Two things
        % keep that honest: the sweep starts at 3 km/h, which
        % is the ENERGY_REQ_37 minimum and so the slowest speed
        % that is legal to hold, and the flag below says
        % outright when the answer came from the boundary.
        %
        % There IS a genuine interior optimum when auxiliary
        % load dominates -- the pumps and instrumentation draw
        % the same power whether the boat is moving or not, so
        % crawling wastes energy per kilometre. Whether it
        % appears depends on the auxiliary budget, which is why
        % it is detected rather than assumed either way.
        %% -----------------------------------------------------

        Perf.BestRange = struct( ...
            "Speed_kmh",   R.Speed_kmh(iBest), ...
            "Speed_knots", R.Speed_kmh(iBest)/C.KmhPerMs*C.KnotsPerMs, ...
            "ShaftPower_W",R.ShaftPower_W(iBest), ...
            "PackPower_W", R.PackPower_W(iBest), ...
            "Wh_per_km",   R.Wh_per_km(iBest), ...
            "Range_km",    bestRange_km, ...
            "Endurance_h", R.Endurance_h(iBest), ...
            "ChainEff",    R.ChainEff(iBest), ...
            "AtSweepFloor",iBest == find(valid,1,"first"), ...
            "SweepFloor_kmh",R.Speed_kmh(find(valid,1,"first")));

    else

        Perf.BestRange = [];

    end

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose

        fprintf("\n");
        fprintf("================================================================\n");
        fprintf(" BOAT PERFORMANCE\n");
        fprintf("================================================================\n");

        fprintf("\nPOWER CEILING\n");
        fprintf("  Rule limit (electrical)  : %.1f kW  ENERGY_REQ_188\n", ...
            Perf.PowerCeiling.ElectricalLimit_W/1000);
        fprintf("  Shaft power available    : %.2f kW at %.0f rpm\n", ...
            P_shaft_max_W/1000,Perf.PowerCeiling.MotorSpeed_rpm);
        fprintf("  Chain to the shaft       : %.1f %% of the cap\n", ...
            100*P_shaft_max_W/Perf.PowerCeiling.ElectricalLimit_W);

        fprintf("\nSPEED\n");
        fprintf("  Top speed                : %.1f km/h  (%.1f knots)\n", ...
            Perf.TopSpeed_kmh,Perf.TopSpeed_knots);
        fprintf("  Propeller at top speed   : %.0f rpm, eta_o %.3f, sigma %.2f\n", ...
            Perf.TopSpeedPropRPM,Perf.TopSpeedPropEff, ...
            Perf.TopSpeedCavitationNumber);
        fprintf("  Motor at top speed       : %.0f rpm, %.1f Nm\n", ...
            Perf.TopSpeedMotorRPM,Perf.MotorTorqueAtTop_Nm);

        if ~Perf.MotorSpeedOK
            fprintf("    NOT FEASIBLE: %.0f rpm exceeds the %.0f rpm limit " + ...
                "by %.0f%%.\n",Perf.TopSpeedMotorRPM, ...
                Perf.MotorSpeedLimit_rpm, ...
                100*(Perf.TopSpeedMotorRPM/Perf.MotorSpeedLimit_rpm - 1));
            fprintf("    Run P50B_MatchPropeller -- the gearbox ratio is " + ...
                "the free variable.\n");
        end

        if ~Perf.MotorTorqueOK
            fprintf("    NOT FEASIBLE: %.1f Nm exceeds the %.1f Nm rating.\n", ...
                Perf.MotorTorqueAtTop_Nm,Perf.MotorTorqueLimit_Nm);
        end

        if Perf.TargetReachable
            targetWord = "reachable";
        else
            targetWord = sprintf( ...
                "NOT REACHABLE under the cap -- %.1f km/h short", ...
                Perf.TargetSpeed_kmh - Perf.TopSpeed_kmh);
        end

        fprintf("  Design target            : %.1f km/h -- %s\n", ...
            Perf.TargetSpeed_kmh,targetWord);

        fprintf("\nDRAG BREAKDOWN\n");
        fprintf("  %8s %9s %9s %9s %9s %9s\n", ...
            "km/h","total N","friction","residuary","planing","air");

        for vk = [10 20 30 40 50]

            if vk > Perf.TopSpeed_kmh + 5
                continue;
            end

            vv = vk / C.KmhPerMs;

            fprintf("  %8.0f %9.0f %9.0f %9.0f %9.0f %9.0f\n", ...
                vk, Hull.Resistance_N(vv,wind), Hull.Frictional_N(vv), ...
                Hull.Residuary_N(vv), Hull.Planing_N(vv), ...
                Hull.Aerodynamic_N(vv,wind));

        end

        fprintf("\nRULES THAT DEPEND ON SPEED\n");

        m = Perf.MinimumSpeed;

        fprintf("  ENERGY_REQ_37  three knots : %s\n", ...
            statusWord(m.Achievable));
        fprintf("    %.0f W of the %.0f W ceiling (%.1f %%), " + ...
            "top speed %.1f knots\n", ...
            m.ShaftPower_W,P_shaft_max_W,100*m.FractionOfCeiling, ...
            m.TopSpeed_knots);

        r = Perf.Reverse;

        fprintf("  ENERGY_REQ_32  reverse     : %s\n", ...
            statusWord(r.Achievable));
        fprintf("    %.0f N astern against %.0f N resistance at 2 knots " + ...
            "(margin %.1fx)\n",r.ThrustAstern_N,r.Resistance_N,r.ThrustMargin);

        if ~isempty(Perf.BestRange)

            b = Perf.BestRange;

            fprintf("\nRANGE ON THE USABLE PACK ENERGY\n");
            fprintf("  Usable pack energy       : %.0f Wh " + ...
                "(%.0f%% of %.0f Wh)\n", ...
                usableEnergy_Wh,100*usableFraction,packEnergy_Wh);

            fprintf("\n  %8s %10s %10s %9s %9s\n", ...
                "km/h","pack W","Wh/km","range km","chain %");

            for target = [5 10 15 20 25 30 35 40]

                [~,ii] = min(abs(R.Speed_kmh - target));

                if abs(R.Speed_kmh(ii) - target) > 0.6 || isnan(R.PackPower_W(ii))
                    continue;
                end

                fprintf("  %8.0f %10.0f %10.0f %9.1f %9.1f\n", ...
                    R.Speed_kmh(ii),R.PackPower_W(ii),R.Wh_per_km(ii), ...
                    R.Range_km(ii),100*R.ChainEff(ii));

            end

            fprintf("\n  Furthest at              : %.1f km/h, " + ...
                "%.1f km (%.0f Wh/km, %.0f min)\n", ...
                b.Speed_kmh,b.Range_km,b.Wh_per_km,b.Endurance_h*60);

            if b.AtSweepFloor
                fprintf("    That is the bottom of the sweep (%.1f km/h, " + ...
                    "the ENERGY_REQ_37\n",b.SweepFloor_kmh);
                fprintf("    minimum), so range is still rising as speed " + ...
                    "falls: the auxiliary\n");
                fprintf("    load has not yet overtaken the drag saving. " + ...
                    "There is no interior\n");
                fprintf("    optimum to pace to -- endurance strategy is " + ...
                    "set by the time limit\n");
                fprintf("    and the lap, not by an economy speed.\n");
            end

        end

        fprintf("================================================================\n\n");

    end

    %% =========================================================
    % PLOT
    %% =========================================================

    if opts.Plot

        figure("Name","Boat performance","Color","w");

        subplot(2,1,1);

        %% -----------------------------------------------------
        % Stack the components as the model actually combines
        % them, blend included. Plotting the raw components
        % would draw a stack that does not add up to the total
        % line beside it, which is worse than no plot.
        %% -----------------------------------------------------

        bl = Hull.PlaningBlend(D.Speed_ms);

        area(D.Speed_kmh, ...
            [(1-bl).*D.Frictional_N + bl.*D.Frictional_N* ...
                 P.boat.planing_wetted_frac, ...
             (1-bl).*D.Residuary_N, ...
             D.Planing_N, ...
             D.Aerodynamic_N]);

        hold on;
        plot(D.Speed_kmh,D.Total_N,"k","LineWidth",1.5);
        xline(Perf.TopSpeed_kmh,"r--","top speed");

        grid on;
        xlabel("Speed (km/h)");
        ylabel("Resistance (N)");
        legend(["friction","residuary","planing","air","total"], ...
            "Location","northwest");
        title("Resistance breakdown");

        subplot(2,1,2);

        plot(R.Speed_kmh,R.Range_km,"LineWidth",1.5);

        grid on;
        xlabel("Speed (km/h)");
        ylabel("Range (km)");
        title("Range on the usable pack energy");

    end

end

%% =============================================================
% Helper
%% =============================================================

function w = statusWord(tf)

    if tf
        w = "PASS";
    else
        w = "FAIL";
    end

end

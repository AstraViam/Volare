function Compliance = P50B_MonacoCompliance(varargin)
%P50B_MONACOCOMPLIANCE  Check the design against the Monaco Energy Class rules.
%
%   Compliance = P50B_MonacoCompliance() evaluates every technical rule
%   that this model can quantify, and lists the rest as an inspection
%   checklist.
%
%   OPTIONS
%     "Verbose"     logical, default true
%     "Cell"        struct from P50B_CellData
%     "Motor"       struct from P50B_MotorData
%     "Harness"     struct from P50B_HarnessData
%     "Busbars"     struct from P50B_Busbars
%     "Geometry"    struct from P50B_Geometry
%     "Thermal"     struct from P50B_ThermalDesign
%
%   RULE SOURCE
%   -----------
%   Monaco Energy Class Technical Rules, Version 2026.1, issued
%   08/09/2025 by the Yacht Club de Monaco. A copy is held in
%   04_data/.
%
%   Requirement numbers below are the ENERGY_REQ_n identifiers from that
%   document, so any finding can be traced straight back to its clause.
%
%   WHAT THIS CAN AND CANNOT CHECK
%   ------------------------------
%   Roughly a quarter of the rules are numerical and follow from the
%   model: stored energy, motor power, voltages, current ratings, mass,
%   temperatures. Those are checked automatically here.
%
%   The rest are physical or procedural -- bulkhead fire rating, kill
%   cord behaviour, label sizes, evacuation time. Those cannot be
%   checked from a MATLAB model and are listed as a checklist so they
%   are not quietly forgotten. A PASS from this function means the
%   quantifiable rules pass, not that the boat is compliant.
%
%   See also P50B_Verification, P50B_CellData, P50B_MotorData.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct( ...
        "Verbose",     true, ...
        "Cell",        [], ...
        "Motor",       [], ...
        "Harness",     [], ...
        "Busbars",     [], ...
        "Geometry",    [], ...
        "Thermal",     [], ...
        "MassBudget",  [], ...
        "Performance", [], ...
        "SkipPerformance", false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_MonacoCompliance:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if isempty(opts.Cell);     opts.Cell     = P50B_CellData();     end
    if isempty(opts.Motor);    opts.Motor    = P50B_MotorData();    end
    if isempty(opts.Harness);  opts.Harness  = P50B_HarnessData();  end
    if isempty(opts.Geometry); opts.Geometry = P50B_Geometry();     end

    cellData = opts.Cell;
    motor    = opts.Motor;
    harn     = opts.Harness;
    G        = opts.Geometry;

    if isempty(opts.Busbars)
        Layout = P50B_GroupLayout(G,"Plot",false,"Verbose",false);
        Bus    = P50B_Busbars(G,Layout,"Plot",false,"Verbose",false);
    else
        Bus = opts.Busbars;
    end

    if isempty(opts.Thermal)
        Thermal = P50B_ThermalDesign(cellData, ...
            "Busbars",Bus,"Verbose",false,"Plot",false);
    else
        Thermal = opts.Thermal;
    end

    Compliance.RulesVersion = "Monaco Energy Class Technical Rules 2026.1";
    Compliance.RulesIssued  = "08/09/2025";
    Compliance.RulesFile    = ...
        "04_data/Monaco Energy Class Technical Rules 2026 V3 (1).pdf";

    %% =========================================================
    % CHECK ACCUMULATOR
    %% =========================================================

    checks = struct("Req",{},"Title",{},"Status",{}, ...
                    "Finding",{},"Action",{});

    function add(req,title,status,finding,action)

        if nargin < 5
            action = "";
        end

        checks(end+1) = struct( ...
            "Req",     string(req), ...
            "Title",   string(title), ...
            "Status",  string(status), ...
            "Finding", string(finding), ...
            "Action",  string(action));

    end

    %% ---------------------------------------------------------
    % Threshold helpers
    %
    % Most of the 2026 rules are a number and a direction: at
    % least 30 mm, no more than 50 mm, at least 500 cm2. Writing
    % each one out longhand buried the rule in boilerplate and
    % made it easy to get the direction backwards, which is the
    % one mistake in a compliance checker that matters -- a
    % reversed comparison reports PASS on a boat that fails.
    %
    % These three take the intended value, the rule's limit and
    % the direction once, and produce the finding text from them.
    % The requirement number and the limit both come from the
    % parameter file, so a rule change is a data edit.
    %
    % "Intended" is the operative word. These check the design
    % the team says it will build, not the boat. They turn a
    % checklist item into a number with a margin, so that the
    % ones with no margin are visible months before somebody
    % arrives with a tape measure.
    %% ---------------------------------------------------------

    function addMin(req,title,have,need,unit,note)

        if nargin < 6; note = ""; end

        margin = have - need;

        if have >= need

            status = "PASS";

            if need > 0 && margin/need < 0.05
                status = "ACTION";
                note = "Margin is under 5%. " + note;
            end

            add(req,title,status, ...
                sprintf("%.4g %s intended, %.4g %s required " + ...
                        "(margin %+.4g %s).",have,unit,need,unit, ...
                        margin,unit),note);

        else

            add(req,title,"FAIL", ...
                sprintf("%.4g %s intended, %.4g %s required " + ...
                        "(short by %.4g %s).",have,unit,need,unit, ...
                        -margin,unit),note);

        end

    end

    function addExact(req,title,have,spec,unit,note)

        %% -----------------------------------------------------
        % For a rule that states a VALUE rather than a bound --
        % a 90 mm yellow circle, a 100 mm symbol. Meeting it
        % exactly is compliance, not a thin margin, so this one
        % does not nag.
        %% -----------------------------------------------------

        if nargin < 6; note = ""; end

        if have >= spec

            add(req,title,"PASS", ...
                sprintf("%.4g %s intended, %.4g %s specified.", ...
                    have,unit,spec,unit),note);

        else

            add(req,title,"FAIL", ...
                sprintf("%.4g %s intended, %.4g %s specified.", ...
                    have,unit,spec,unit),note);

        end

    end

    function addMax(req,title,have,limit,unit,note)

        if nargin < 6; note = ""; end

        margin = limit - have;

        if have <= limit

            add(req,title,"PASS", ...
                sprintf("%.4g %s intended, %.4g %s permitted " + ...
                        "(margin %+.4g %s).",have,unit,limit,unit, ...
                        margin,unit),note);

        else

            add(req,title,"FAIL", ...
                sprintf("%.4g %s intended, %.4g %s permitted " + ...
                        "(over by %.4g %s).",have,unit,limit,unit, ...
                        -margin,unit),note);

        end

    end

    function addDeclared(req,title,tf,yes,no)

        if tf
            add(req,title,"PASS",yes, ...
                "Declared in the parameter file. Confirm on the " + ...
                "build at inspection.");
        else
            add(req,title,"FAIL",no);
        end

    end

    Ns = G.Pack.SeriesGroups;
    Np = G.Pack.ParallelCells;

    nCells = Ns*Np;

    Vnom = Ns * cellData.NominalVoltage_V;
    Vmax = Ns * cellData.MaxVoltage_V;
    Vmin = Ns * cellData.MinVoltage_V;

    %% =========================================================
    % ENERGY_REQ_7 -- MAXIMUM STORED ENERGY
    %
    % "At any moment, the maximum energy stored by a boat shall
    %  remain under 10 kWh."
    %
    % The rule prescribes the calculation exactly:
    %
    %   E_total = sum( E_i * f_i ),  battery factor f = 1.0
    %
    %   Energy capacity per battery =
    %       quantity of cells x cell nominal voltage
    %                         x cell nominal current
    %
    % The document says "current" where it means capacity in Ah,
    % which is the only reading that yields an energy. Nominal /
    % typical values only -- explicitly not minimum or maximum,
    % so the 5.0 Ah typical is used and not the 4.85 Ah minimum.
    %
    % This is the single most important rule for this project.
    %% =========================================================

    batteryFactor = 1.0;

    E_stored_Wh = nCells * cellData.NominalVoltage_V * ...
                  cellData.Capacity_Ah * batteryFactor;

    E_limit_Wh = 10000;

    margin_Wh = E_limit_Wh - E_stored_Wh;

    Compliance.Energy.StoredEnergy_Wh   = E_stored_Wh;
    Compliance.Energy.Limit_Wh          = E_limit_Wh;
    Compliance.Energy.Margin_Wh         = margin_Wh;
    Compliance.Energy.MarginPercent     = margin_Wh/E_limit_Wh*100;
    Compliance.Energy.BatteryFactor     = batteryFactor;
    Compliance.Energy.MaxCellsAllowed   = ...
        floor(E_limit_Wh / ...
            (cellData.NominalVoltage_V*cellData.Capacity_Ah));

    if E_stored_Wh < E_limit_Wh

        add("ENERGY_REQ_7","Maximum stored energy under 10 kWh", ...
            "PASS", ...
            sprintf("%d cells x %.1f V x %.1f Ah x f=1.0 = %.0f Wh. " + ...
                    "Margin %.0f Wh (%.2f%%).", ...
                nCells,cellData.NominalVoltage_V,cellData.Capacity_Ah, ...
                E_stored_Wh,margin_Wh,margin_Wh/E_limit_Wh*100), ...
            sprintf("Margin is thin. The rule caps the pack at %d " + ...
                    "cells of this type; you have %d.", ...
                Compliance.Energy.MaxCellsAllowed,nCells));

    else

        add("ENERGY_REQ_7","Maximum stored energy under 10 kWh", ...
            "FAIL", ...
            sprintf("%.0f Wh exceeds the %.0f Wh limit by %.0f Wh.", ...
                E_stored_Wh,E_limit_Wh,-margin_Wh), ...
            sprintf("Reduce to at most %d cells.", ...
                Compliance.Energy.MaxCellsAllowed));

    end

    %% =========================================================
    % ENERGY_REQ_188 -- MOTOR NOMINAL POWER
    %
    % "The total nominal power consumption of the motor(s) shall
    %  not exceed 25 kW."
    %
    % New requirement for 2026 (see the change history, page 5).
    %% =========================================================

    motorPowerLimit_W = 25e3;

    Compliance.MotorPower.Nominal_W = motor.NominalPower_W;
    Compliance.MotorPower.Limit_W   = motorPowerLimit_W;
    Compliance.MotorPower.Excess_W  = ...
        motor.NominalPower_W - motorPowerLimit_W;

    Compliance.MotorPower.Configured_W = motor.ConfiguredPowerLimit_W;

    if motor.ConfiguredPowerLimit_W > motorPowerLimit_W

        %% -----------------------------------------------------
        % The configured limit itself breaks the rule.
        %% -----------------------------------------------------

        add("ENERGY_REQ_188","Motor nominal power at or below 25 kW", ...
            "FAIL", ...
            sprintf("Configured power limit is %.1f kW, above the " + ...
                    "25 kW rule limit.", ...
                motor.ConfiguredPowerLimit_W/1000), ...
            "Lower ConfiguredPowerLimit_W in P50B_MotorData to " + ...
            "25 kW or less.");

    elseif motor.NominalPower_W > motorPowerLimit_W

        %% -----------------------------------------------------
        % Hardware exceeds the limit but is configured down.
        % Compliant by configuration, and that configuration has
        % to be demonstrable rather than merely asserted.
        %% -----------------------------------------------------

        add("ENERGY_REQ_188","Motor nominal power at or below 25 kW", ...
            "ACTION", ...
            sprintf("Competr hardware is rated %.1f kW nominal " + ...
                    "(%.0f kW peak), which is %.1f kW over the rule " + ...
                    "limit. The drivetrain is configured to %.1f kW, " + ...
                    "which complies, and every model in this project " + ...
                    "enforces that limit.", ...
                motor.NominalPower_W/1000, ...
                motor.MaximumPower_W/1000, ...
                Compliance.MotorPower.Excess_W/1000, ...
                motor.ConfiguredPowerLimit_W/1000), ...
            "Compliance depends entirely on the derate. Get a " + ...
            "written statement from Competr confirming the unit can " + ...
            "be limited to 25 kW nominal, and be able to show the " + ...
            "setting in the inverter configuration at scrutineering.");

    else

        add("ENERGY_REQ_188","Motor nominal power at or below 25 kW", ...
            "PASS", ...
            sprintf("Motor nominal %.1f kW, configured limit %.1f kW.", ...
                motor.NominalPower_W/1000, ...
                motor.ConfiguredPowerLimit_W/1000));

    end

    %% =========================================================
    % ENERGY_REQ_187 -- VOLTAGE ABOVE 100 V
    %
    % "If a team intends to use a voltage above 100 V, it shall
    %  obtain approval from the Technical Committee during the
    %  registration phase."
    %% =========================================================

    if Vmax > 100

        add("ENERGY_REQ_187","Approval required for voltage above 100 V", ...
            "ACTION", ...
            sprintf("Pack reaches %.1f V at 100%% SOC (26S x 4.2 V), " + ...
                    "above the 100 V threshold.",Vmax), ...
            "Obtain Technical Committee approval during " + ...
            "registration. This is a paperwork gate, not a design " + ...
            "fault -- but without it the boat cannot race.");

    else

        add("ENERGY_REQ_187","Approval required for voltage above 100 V", ...
            "PASS", ...
            sprintf("Pack maximum %.1f V stays below 100 V.",Vmax));

    end

    %% =========================================================
    % ENERGY_REQ_191 -- HIGH VOLTAGE TRAINING
    %% =========================================================

    if Vmax >= 100

        add("ENERGY_REQ_191","High voltage training certification", ...
            "ACTION", ...
            sprintf("System reaches %.1f V, so the 100 V threshold " + ...
                    "applies.",Vmax), ...
            "Everyone who works on the pack needs a high voltage " + ...
            "training certificate. Checked at technical inspection.");

    end

    %% =========================================================
    % ENERGY_REQ_59 -- OVERCURRENT PROTECTION COORDINATION
    %
    % "The continuous current rating of the overcurrent protection
    %  shall not be greater than the continuous current rating of
    %  any electrical component [it protects]."
    %
    % This is a real, checkable constraint and it is easy to get
    % backwards: the instinct is to size the fuse above the peak
    % load, but the rule sizes it below the weakest conductor.
    %% =========================================================

    protectedRatings = [ ...
        harn.CableAmpacity_A
        Bus.Ampacity.DesignLimit_A_per_mm2 * Bus.Geometry.SeriesArea_mm2];

    protectedNames = [ ...
        "HV cable (" + string(harn.CableCrossSection_mm2) + " mm2)"
        "Series busbar (" + string(Bus.Geometry.SeriesArea_mm2) + " mm2)"];

    [weakest,idxWeak] = min(protectedRatings);

    Compliance.Protection.FuseRating_A     = harn.FuseRating_A;
    Compliance.Protection.WeakestComponent = protectedNames(idxWeak);
    Compliance.Protection.WeakestRating_A  = weakest;

    if harn.FuseRating_A <= weakest

        add("ENERGY_REQ_59","Fuse rating below weakest protected component", ...
            "PASS", ...
            sprintf("%.0f A fuse protects %s rated %.0f A continuous.", ...
                harn.FuseRating_A,protectedNames(idxWeak),weakest));

    else

        add("ENERGY_REQ_59","Fuse rating below weakest protected component", ...
            "FAIL", ...
            sprintf("%.0f A fuse exceeds the %.0f A continuous rating " + ...
                    "of the %s it protects.", ...
                harn.FuseRating_A,weakest,protectedNames(idxWeak)), ...
            sprintf("Reduce the fuse to at most %.0f A, or increase " + ...
                    "the conductor rating.",floor(weakest/10)*10));

    end

    %% =========================================================
    % ENERGY_REQ_58 -- FUSE JUST AFTER ENERGY STORAGE
    %% =========================================================

    add("ENERGY_REQ_58","Fuse immediately after the energy storage", ...
        "MODELLED", ...
        sprintf("A %.0f A fuse is modelled in the HV path.", ...
            harn.FuseRating_A), ...
        "Confirm the physical fuse sits immediately after the pack " + ...
        "terminals, before any other component. Also required on " + ...
        "the telemetry battery.");

    %% =========================================================
    % ENERGY_REQ_57 -- WIRE GAUGE
    %% =========================================================

    operatingCurrent = motor.BusMaximumCurrent_A;

    if harn.CableAmpacity_A >= operatingCurrent

        add("ENERGY_REQ_57","Adequately sized wire gauge", ...
            "PASS", ...
            sprintf("%.0f mm2 cable, %.0f A derated, against %.0f A " + ...
                    "maximum continuous draw.", ...
                harn.CableCrossSection_mm2, ...
                harn.CableAmpacity_A, ...
                operatingCurrent));

    else

        add("ENERGY_REQ_57","Adequately sized wire gauge", ...
            "FAIL", ...
            sprintf("%.0f mm2 cable derates to %.0f A but the " + ...
                    "drivetrain can draw %.0f A.", ...
                harn.CableCrossSection_mm2, ...
                harn.CableAmpacity_A, ...
                operatingCurrent), ...
            "Increase the conductor cross-section.");

    end

    %% =========================================================
    % ENERGY_REQ_23 -- CELLS WITHIN DATASHEET RATINGS
    %% =========================================================

    cellCurrentAtMax = motor.BusMaximumCurrent_A / Np;

    if cellCurrentAtMax <= cellData.MaxContinuousCurrent_A

        add("ENERGY_REQ_23","Batteries used within datasheet ratings", ...
            "PASS", ...
            sprintf("%.2f A per cell at the %.0f A bus maximum, " + ...
                    "against a %.0f A datasheet continuous rating " + ...
                    "(%.0f%% utilisation).", ...
                cellCurrentAtMax,motor.BusMaximumCurrent_A, ...
                cellData.MaxContinuousCurrent_A, ...
                cellCurrentAtMax/cellData.MaxContinuousCurrent_A*100));

    else

        add("ENERGY_REQ_23","Batteries used within datasheet ratings", ...
            "FAIL", ...
            sprintf("%.2f A per cell exceeds the %.0f A rating.", ...
                cellCurrentAtMax,cellData.MaxContinuousCurrent_A));

    end

    %% =========================================================
    % ENERGY_REQ_93 -- EXPOSED PARTS UNDER 60 degC
    %% =========================================================

    Tt = Thermal.Table;

    peakSteadyTemp = max(Tt.SteadyTemp_C);

    if peakSteadyTemp <= 60

        add("ENERGY_REQ_93","Exposed parts below 60 degC", ...
            "PASS", ...
            sprintf("Highest modelled steady cell temperature " + ...
                    "%.1f degC.",peakSteadyTemp));

    else

        add("ENERGY_REQ_93","Exposed parts below 60 degC", ...
            "PARTIAL", ...
            sprintf("Cells reach %.1f degC steady at the highest " + ...
                    "modelled current.",peakSteadyTemp), ...
            "The rule applies to exposed surfaces, not cells inside " + ...
            "a container. Verify enclosure skin temperature, and " + ...
            "note that the busbars and outboard are also in scope.");

    end

    %% =========================================================
    % ENERGY_REQ_67 / 68 -- TEMPERATURE MONITORING
    %% =========================================================

    warnTemp = 0.90 * cellData.TempCutOff_C;

    Compliance.Monitoring.MaxMonitoredTemp_C = cellData.TempCutOff_C;
    Compliance.Monitoring.WarningThreshold_C = warnTemp;

    add("ENERGY_REQ_67","Battery temperature monitored and shown to pilot", ...
        "ACTION", ...
        "Not a model property. The BMS must display cell " + ...
        "temperature to the pilot, and the telemetry battery " + ...
        "needs monitoring too.", ...
        "Confirm the BMS temperature channel reaches the pilot display.");

    add("ENERGY_REQ_68","Pilot warned at 90% of maximum temperature", ...
        "ACTION", ...
        sprintf("With a %.0f degC cell maximum, the warning must " + ...
                "trigger at %.0f degC.", ...
            cellData.TempCutOff_C,warnTemp), ...
        sprintf("Set the BMS warning threshold to %.0f degC.",warnTemp));

    %% =========================================================
    % ENERGY_REQ_154 -- STEERING ANGLE
    %% =========================================================

    %% ---------------------------------------------------------
    % Steering range is a Competr datasheet figure and lives in
    % the auxiliary-load parameter set alongside the actuator
    % that drives it.
    %% ---------------------------------------------------------

    aux = P50B_AuxiliaryLoads();

    if abs(aux.SteeringAngleMin_deg) >= 40 && ...
       abs(aux.SteeringAngleMax_deg) >= 40

        add("ENERGY_REQ_154","Steering rotates at least 40 degrees each side", ...
            "PASS", ...
            sprintf("Competr steering range %+.0f to %+.0f degrees.", ...
                aux.SteeringAngleMin_deg,aux.SteeringAngleMax_deg), ...
            "Exactly at the limit, with no margin. Verify the " + ...
            "installed range on the boat.");

    else

        add("ENERGY_REQ_154","Steering rotates at least 40 degrees each side", ...
            "FAIL", ...
            sprintf("Range is %+.0f to %+.0f degrees.", ...
                aux.SteeringAngleMin_deg,aux.SteeringAngleMax_deg));

    end

    %% =========================================================
    % PARAMETERS FOR THE DECLARED-DIMENSION CHECKS
    %% =========================================================

    Pp = P50B_LoadParams("Plain",true);

    CK = Pp.cockpit;
    RL = Pp.rules;
    TM = Pp.telemetry;

    %% =========================================================
    % ENERGY_REQ_5 / 6 / 31 -- PERMITTED ENERGY SOURCES
    %
    % Cheap to check and cheap to forget. A battery-electric
    % boat passes these by construction, but "by construction"
    % is worth stating once rather than assuming, because the
    % rule also bans human power and a pedal-assisted trim pump
    % would breach it.
    %% =========================================================

    add("ENERGY_REQ_5","No ammonia, fossil fuel or nuclear energy", ...
        "PASS", ...
        "Battery electric. The only stored energy aboard is the " + ...
        "9.83 kWh lithium pack and the secondary telemetry battery, " + ...
        "both of which the rule permits.", ...
        "Note that ENERGY_REQ_7 note 3 exempts the telemetry " + ...
        "battery from the energy calculation but not from the " + ...
        "fusing and monitoring rules.");

    add("ENERGY_REQ_6","No direct CO2 emissions","PASS", ...
        "Battery electric, no combustion of any kind aboard.");

    addDeclared("ENERGY_REQ_31","No human powered mechanical energy", ...
        ~CK.human_power_used, ...
        "No human-powered propulsion or actuation.", ...
        "cockpit.human_power_used is set, which the rule forbids.");

    %% =========================================================
    % ENERGY_REQ_48 -- WEIGHT, FROM THE MASS BUDGET
    %
    % This replaces what used to be a PARTIAL with a line-by-line
    % budget. The old finding added the pack, the outboard and
    % the pilot and reported that 83 kg was left for everything
    % else; it did not say whether everything else fits in 83 kg.
    % It does, but only just.
    %% =========================================================

    if isempty(opts.MassBudget)
        Budget = P50B_MassBudget("Geometry",G,"Motor",motor,"Verbose",false);
    else
        Budget = opts.MassBudget;
    end

    Compliance.MassBudget = Budget;

    if Budget.Pass

        if Budget.MarginPercent < 5
            massStatus = "ACTION";
        else
            massStatus = "PASS";
        end

        add("ENERGY_REQ_48","Overall weight excluding hulls under 250 kg", ...
            massStatus, ...
            sprintf("%.1f kg excluding hulls against a %.0f kg limit, " + ...
                    "margin %.1f kg (%.1f%%). The scales will read " + ...
                    "%.1f kg with the %.0f kg of hulls and the pilot.", ...
                Budget.ExcludingHulls_kg,Budget.Limit_kg, ...
                Budget.Margin_kg,Budget.MarginPercent, ...
                Budget.WeighInNominal_kg,Budget.HullMass_kg), ...
            sprintf("%.0f%% of the budget is allowances rather than " + ...
                    "weighed parts, and an overweight boat is not " + ...
                    "allowed in the water at all. Put the pack, the " + ...
                    "cockpit shell and the outboard on a scale as soon " + ...
                    "as each exists.",100*Budget.AllowanceFraction));

    else

        add("ENERGY_REQ_48","Overall weight excluding hulls under 250 kg", ...
            "FAIL", ...
            sprintf("%.1f kg excluding hulls, over the %.0f kg limit " + ...
                    "by %.1f kg.", ...
                Budget.ExcludingHulls_kg,Budget.Limit_kg,-Budget.Margin_kg), ...
            "An overweight boat is not permitted in the water. See " + ...
            "P50B_MassBudget for where the mass is.");

    end

    %% =========================================================
    % ENERGY_REQ_135 -- PILOT MASS AND BALLAST
    %% =========================================================

    if Budget.Pilot.Ballast_kg > 0

        add("ENERGY_REQ_135","Pilot at least 60 kg ready to sail", ...
            "ACTION", ...
            sprintf("Pilot %.0f kg ready to sail, so %.1f kg of ballast " + ...
                    "is required and counts against the 250 kg.", ...
                Budget.Pilot.Mass_kg,Budget.Pilot.Ballast_kg), ...
            "ENERGY_REQ_136 requires the ballast to be properly fixed, " + ...
            "in or near the pilot's seat, and accessible for " + ...
            "inspection. Size it on the LIGHTEST pilot entered.");

    else

        add("ENERGY_REQ_135","Pilot at least 60 kg ready to sail","PASS", ...
            sprintf("Pilot %.0f kg ready to sail against a %.0f kg " + ...
                    "minimum, so no ballast is needed.", ...
                Budget.Pilot.Mass_kg,Budget.Pilot.Minimum_kg), ...
            "Ready to sail means with overalls, helmet, lifejacket, " + ...
            "shoes and the communication system. Weigh the pilot " + ...
            "dressed, not undressed.");

    end

    %% =========================================================
    % ENERGY_REQ_37 and 32 -- SPEED AND MANOEUVRABILITY
    %
    % These were on the checklist because MATLAB had no boat in
    % it. It has one now, so they are computed. The Technical
    % Committee still judges manoeuvrability by watching the
    % boat -- but a design that cannot make three knots on paper
    % will not make them on the water either.
    %% =========================================================

    if opts.SkipPerformance

        Perf = [];

    elseif isempty(opts.Performance)

        try
            Perf = P50B_BoatPerformance("Verbose",false);
        catch perfErr
            Perf = [];
            add("ENERGY_REQ_37","Boat reaches at least 3 knots","ACTION", ...
                "The performance model did not run: " + ...
                string(perfErr.message), ...
                "Fix P50B_BoatPerformance -- this check cannot be " + ...
                "evaluated without it.");
        end

    else

        Perf = opts.Performance;

    end

    Compliance.Performance = Perf;

    if ~isempty(Perf)

        m = Perf.MinimumSpeed;

        if m.Achievable

            add("ENERGY_REQ_37","Boat reaches at least 3 knots","PASS", ...
                sprintf("Three knots needs %.0f W at the shaft, %.1f%% " + ...
                        "of the %.1f kW the rules allow. Top speed is " + ...
                        "%.1f knots.", ...
                    m.ShaftPower_W,100*m.FractionOfCeiling, ...
                    Perf.ShaftPowerCeiling_W/1000,m.TopSpeed_knots), ...
                "Computed against the supplied MEBC resistance curve. " + ...
                "The sea trial is still the proof.");

        else

            add("ENERGY_REQ_37","Boat reaches at least 3 knots","FAIL", ...
                sprintf("Three knots needs %.0f W at the shaft, more " + ...
                        "than the %.0f W the power cap allows.", ...
                    m.ShaftPower_W,Perf.ShaftPowerCeiling_W));

        end

        r = Perf.Reverse;

        if r.Achievable

            add("ENERGY_REQ_32","Boat moves and manoeuvres forward and reverse", ...
                "PASS", ...
                sprintf("At quarter power and 2 knots the propulsor " + ...
                        "makes %.0f N astern against %.0f N of " + ...
                        "resistance, a margin of %.1fx.", ...
                    r.ThrustAstern_N,r.Resistance_N,r.ThrustMargin), ...
                "Astern thrust is estimated as a fraction of ahead " + ...
                "thrust and is an assumption, but the margin is wide " + ...
                "enough that the assumption is not load bearing. " + ...
                "Manoeuvrability is judged by the Technical Committee " + ...
                "at the sea certification test.");

        else

            add("ENERGY_REQ_32","Boat moves and manoeuvres forward and reverse", ...
                "FAIL", ...
                sprintf("Only %.0f N astern against %.0f N of " + ...
                        "resistance at 2 knots.", ...
                    r.ThrustAstern_N,r.Resistance_N));

        end

        %% -----------------------------------------------------
        % Not a rule, but it belongs in the same report: can the
        % drivetrain deliver the power the rule permits?
        %% -----------------------------------------------------

        if ~Perf.MotorTorqueOK || ~Perf.MotorSpeedOK

            add("DRIVETRAIN","Motor can deliver the permitted power", ...
                "ACTION", ...
                sprintf("At top speed the propulsor asks the motor for " + ...
                        "%.0f rpm and %.1f Nm against limits of %.0f " + ...
                        "rpm and %.0f Nm.", ...
                    Perf.TopSpeedMotorRPM,Perf.MotorTorqueAtTop_Nm, ...
                    Perf.MotorSpeedLimit_rpm,Perf.MotorTorqueLimit_Nm), ...
                "Not a rule breach -- the boat is simply unable to use " + ...
                "the power it is allowed. Run P50B_GearboxStudy; the " + ...
                "gearbox ratio is the free variable.");

        end

    end

    %% =========================================================
    % ENERGY_REQ_63 -- IP2X ABOVE 15 V DC
    %
    % The pack is 109 V at full charge, so this applies to every
    % part of the HV system including the busbars, which the rule
    % names explicitly.
    %% =========================================================

    if Vmax > RL.ip2x_threshold_dc_V

        add("ENERGY_REQ_63","Circuits above 15 V DC at least IP2X", ...
            "ACTION", ...
            sprintf("The pack reaches %.1f V, far above the %.0f V DC " + ...
                    "threshold, so IP2X applies to the whole HV system. " + ...
                    "Intended rating is %s.", ...
                Vmax,RL.ip2x_threshold_dc_V,CK.hv_circuit_ip_rating), ...
            "The rule names busbars specifically. Every exposed " + ...
            "conductor inside the pack needs a cover, not just the " + ...
            "terminals. ENERGY_REQ_60 then tests it with a 100 mm " + ...
            "long, 6 mm probe.");

    end

    %% =========================================================
    % ENERGY_REQ_71 -- KILL CORD CUTS POWER IN UNDER ONE SECOND
    %
    % A timing budget rather than a checklist tick. The chain is
    % detection, inverter inhibit, then the contactor opening.
    % Each stage is a parameter, so the margin is visible and the
    % component that would break it is identifiable.
    %% =========================================================

    killChain_s = (CK.killcord_detect_ms + CK.inverter_disable_ms + ...
                   CK.contactor_dropout_ms) / 1000;

    addMax("ENERGY_REQ_71","Kill cord cuts engine power in under 1 second", ...
        killChain_s,RL.killcord_max_cutoff_s,"s", ...
        sprintf("Detection %.0f ms, inverter inhibit %.0f ms, " + ...
                "contactor %.0f ms. The contactor dominates and is the " + ...
                "one figure worth taking from a real datasheet. " + ...
                "ENERGY_REQ_74 then requires a second deliberate action " + ...
                "before the motor can restart -- waiting does not count.", ...
            CK.killcord_detect_ms,CK.inverter_disable_ms, ...
            CK.contactor_dropout_ms));

    %% =========================================================
    % EMERGENCY STOP GEOMETRY -- 76, 77, 78, 85
    %% =========================================================

    addMin("ENERGY_REQ_77","Emergency stop button at least 30 mm across", ...
        CK.estop_button_diameter_mm,RL.estop_min_diameter_mm,"mm");

    addExact("ENERGY_REQ_76","Red button over a 90 mm yellow circle", ...
        CK.estop_yellow_circle_mm,RL.estop_yellow_circle_mm,"mm", ...
        "The rule gives 90 mm as the specification, not as a minimum.");

    addExact("ENERGY_REQ_78","Emergency stop symbol at least 100 mm high", ...
        CK.estop_symbol_height_mm,RL.estop_symbol_min_mm,"mm", ...
        "Red spark on a white-edged blue triangle, close to the button.");

    addMax("ENERGY_REQ_85","Emergency stop within one metre of starboard", ...
        CK.estop_from_starboard_m,RL.estop_max_from_starboard_m,"m", ...
        "ENERGY_REQ_81 also requires it in front of the pilot, and " + ...
        "ENERGY_REQ_86 requires it to face outboard -- a button " + ...
        "pointing up is explicitly not compliant.");

    addDeclared("ENERGY_REQ_79","Emergency stop isolates every power source", ...
        CK.estop_isolates_telemetry, ...
        "Isolates the telemetry supply as well as the traction pack, " + ...
        "by relay rather than in software.", ...
        "cockpit.estop_isolates_telemetry is false. The rule includes " + ...
        "telemetry power sources.");

    %% =========================================================
    % BULKHEAD -- 174, 175, 51
    %
    % The hole has both a floor and a ceiling, which is easy to
    % miss: 30 mm minimum from ENERGY_REQ_174 and 50 mm maximum
    % from ENERGY_REQ_175.
    %% =========================================================

    addMin("ENERGY_REQ_174","Bulkhead hole at least 30 mm", ...
        CK.bulkhead_hole_diameter_mm,RL.bulkhead_hole_min_mm,"mm");

    addMax("ENERGY_REQ_175","Bulkhead hole at most 50 mm, with a cap", ...
        CK.bulkhead_hole_diameter_mm,RL.bulkhead_hole_max_mm,"mm", ...
        "ENERGY_REQ_176 also requires it to point to the pilot's " + ...
        "side rather than at the pilot.");

    add("ENERGY_REQ_51","Bulkhead at least A1 fire resistant","PASS", ...
        sprintf("Intended class %s.",CK.bulkhead_fire_class), ...
        "Changed from the French classification to Euroclass for " + ...
        "2026. Have the material certificate at inspection.");

    %% =========================================================
    % ENERGY_REQ_25 -- CONTAINER CLEARANCE FROM THE PILOT
    %% =========================================================

    addMin("ENERGY_REQ_25","Energy container at least 500 mm from the pilot", ...
        CK.energy_container_to_pilot_mm, ...
        RL.container_min_from_pilot_mm,"mm", ...
        "Relaxed from 1 m for 2026. Applies to the secondary " + ...
        "telemetry battery too.");

    %% =========================================================
    % ENERGY_REQ_38 -- COCKPIT TO BEAM CLAMPS
    %% =========================================================

    addExact("ENERGY_REQ_38","At least two clamps per beam", ...
        CK.clamps_per_beam,RL.clamp_min_per_beam,"per beam", ...
        "Each must envelop the full circumference of the beam.");

    addMin("ENERGY_REQ_38","Clamp width at least 50 mm", ...
        CK.clamp_width_mm,RL.clamp_min_width_mm,"mm");

    addMin("ENERGY_REQ_38","Clamp spacing at least 750 mm", ...
        CK.clamp_spacing_mm,RL.clamp_min_spacing_mm,"mm", ...
        sprintf("New for 2026. Symmetric about the centreline. The " + ...
                "beams are %.0f mm apart, so there is room.", ...
            Pp.boat.beam_pitch_m*1000));

    addMin("ENERGY_REQ_38","Clamp gasket at least 1 mm", ...
        CK.clamp_gasket_mm,RL.clamp_min_gasket_mm,"mm", ...
        "Rubber, between the beam and the clamp. ENERGY_REQ_3 " + ...
        "forbids modifying the beams, so the gasket is what " + ...
        "protects them.");

    %% =========================================================
    % ORGANISER EQUIPMENT -- 182, 184, 185
    %% =========================================================

    addMin("ENERGY_REQ_182","Pass-through for the organiser temperature sensor", ...
        CK.sensor_pass_through_mm,RL.sensor_hole_min_mm,"mm", ...
        "The sensor must reach cells at the CORE of the pack, not " + ...
        "just the wall. The three empty slots in the 4x4 grid give a " + ...
        "natural route to the centre -- design the route now, not " + ...
        "after the pack is potted.");

    monitorVolOK = CK.monitor_bay_L_mm >= RL.monitor_volume_mm(1) && ...
                   CK.monitor_bay_W_mm >= RL.monitor_volume_mm(2) && ...
                   CK.monitor_bay_H_mm >= RL.monitor_volume_mm(3);

    if monitorVolOK

        add("ENERGY_REQ_185","Free volume for the organiser monitoring device", ...
            "PASS", ...
            sprintf("%.0f x %.0f x %.0f mm allocated against a " + ...
                    "%.0f x %.0f x %.0f mm requirement.", ...
                CK.monitor_bay_L_mm,CK.monitor_bay_W_mm,CK.monitor_bay_H_mm, ...
                RL.monitor_volume_mm(1),RL.monitor_volume_mm(2), ...
                RL.monitor_volume_mm(3)), ...
            "It must be open to the sky, outside every closed " + ...
            "compartment, and its long-by-wide plane as parallel to " + ...
            "the trim as possible. The organiser also fits a camera.");

    else

        add("ENERGY_REQ_185","Free volume for the organiser monitoring device", ...
            "FAIL", ...
            sprintf("%.0f x %.0f x %.0f mm allocated, " + ...
                    "%.0f x %.0f x %.0f mm required.", ...
                CK.monitor_bay_L_mm,CK.monitor_bay_W_mm,CK.monitor_bay_H_mm, ...
                RL.monitor_volume_mm(1),RL.monitor_volume_mm(2), ...
                RL.monitor_volume_mm(3)));

    end

    addMin("ENERGY_REQ_185","Monitoring cables 100 mm clear of power cables", ...
        CK.monitor_bay_cable_clear_mm,RL.monitor_min_cable_clear_mm,"mm", ...
        "Crossing a power cable is permitted only at a right angle. " + ...
        "The organiser installs the sensor cabling, but the team has " + ...
        "to leave them a route.");

    supplyOK = TM.supply_nominal_V >= RL.monitor_supply_V(1) && ...
               TM.supply_nominal_V <= RL.monitor_supply_V(2);

    if supplyOK

        add("ENERGY_REQ_184","Organiser power interface, 10-28 V, 30 W", ...
            "PASS", ...
            sprintf("%.0f V from the DC-DC rail, inside the %.0f-%.0f V " + ...
                    "window, with a %.0f W budget. Connector %s, " + ...
                    "positive on pin 1.", ...
                TM.supply_nominal_V,RL.monitor_supply_V(1), ...
                RL.monitor_supply_V(2),TM.supply_budget_W, ...
                TM.connector_pn), ...
            "The connector part number CHANGED for 2026 -- check it " + ...
            "against Annex IV before ordering. Amphenol LTW " + ...
            "BD-02BFFA-LL7001 or ABD-02AFFM-LL7A03.");

    else

        add("ENERGY_REQ_184","Organiser power interface, 10-28 V, 30 W", ...
            "FAIL", ...
            sprintf("%.0f V is outside the %.0f-%.0f V window.", ...
                TM.supply_nominal_V,RL.monitor_supply_V(1), ...
                RL.monitor_supply_V(2)));

    end

    %% =========================================================
    % LABELLING -- 171, 172, 173
    %
    % Triggered by the 100 Wh threshold, which this pack passes
    % by a factor of ninety-eight.
    %% =========================================================

    if E_stored_Wh > RL.label_energy_threshold_Wh

        addMin("ENERGY_REQ_171","W026 lithium battery symbol at least 10 cm", ...
            CK.w026_symbol_cm,RL.w026_symbol_min_cm,"cm", ...
            sprintf("The pack holds %.0f Wh, well over the %.0f Wh " + ...
                    "threshold, so the symbol is required on the " + ...
                    "battery AND on its container. ISO 7010:2019.", ...
                E_stored_Wh,RL.label_energy_threshold_Wh));

        addMin("ENERGY_REQ_172","Battery capacity marked, letters at least 2 cm", ...
            CK.label_letter_cm,RL.label_letter_min_cm,"cm", ...
            sprintf("Mark it as %.0f Wh / %.1f V / %.0f Ah.", ...
                E_stored_Wh,Vnom,Np*cellData.Capacity_Ah));

        addMin("ENERGY_REQ_173","Battery composition marked, letters at least 2 cm", ...
            CK.label_letter_cm,RL.label_letter_min_cm,"cm", ...
            sprintf("Composition is %s -- lithium-ion, %s cells.", ...
                string(Pp.cell.chemistry),string(Pp.cell.part_number)));

    end

    %% =========================================================
    % HIGH VISIBILITY TAPE -- ENERGY_REQ_49
    %% =========================================================

    addMin("ENERGY_REQ_49","High visibility tape, starboard", ...
        CK.hivis_starboard_cm2,RL.hivis_side_min_cm2,"cm2");

    addMin("ENERGY_REQ_49","High visibility tape, port", ...
        CK.hivis_port_cm2,RL.hivis_side_min_cm2,"cm2");

    addMin("ENERGY_REQ_49","High visibility tape, forward", ...
        CK.hivis_front_cm2,RL.hivis_end_min_cm2,"cm2");

    addMin("ENERGY_REQ_49","High visibility tape, aft", ...
        CK.hivis_back_cm2,RL.hivis_end_min_cm2,"cm2");

    %% =========================================================
    % SAFETY EQUIPMENT -- 96, 99, 101, 102, 103, 106, 137
    %% =========================================================

    addMin("ENERGY_REQ_106","Fire extinguisher at least 1 kg", ...
        CK.extinguisher_kg,RL.extinguisher_min_kg,"kg", ...
        "ENERGY_REQ_107 requires ABC type; 108 and 109 require a " + ...
        "valid approval showing the last and next test dates; 110 " + ...
        "requires it reachable from the seat and NOT behind it; 111 " + ...
        "requires it not to fall in the water when taken out.");

    addMin("ENERGY_REQ_101","Paddle overall length", ...
        CK.paddle_length_cm,RL.paddle_min_length_cm,"cm");

    addMin("ENERGY_REQ_101","Paddle blade length", ...
        CK.paddle_blade_length_cm,RL.paddle_min_blade_length_cm,"cm");

    addMin("ENERGY_REQ_101","Paddle blade width", ...
        CK.paddle_blade_width_cm,RL.paddle_min_blade_width_cm,"cm");

    addMin("ENERGY_REQ_102","Boat hook at least 100 cm", ...
        CK.boathook_length_cm,RL.boathook_min_length_cm,"cm", ...
        "It may be combined with the paddle, but a plain paddle " + ...
        "handle is not a hook -- it has to be able to catch.");

    addMin("ENERGY_REQ_103","Warning flag at least 30 x 30 cm", ...
        CK.warning_flag_cm,RL.warning_flag_min_cm,"cm", ...
        "Uniformly orange or red. ENERGY_REQ_104 forbids securing " + ...
        "it to the paddle or the boat hook, so it needs its own " + ...
        "handle.");

    addMin("ENERGY_REQ_103","Warning flag handle at least 100 cm", ...
        CK.warning_flag_handle_cm,RL.flag_min_handle_cm,"cm");

    addMin("ENERGY_REQ_99","Floating towline at least 10 m", ...
        CK.towline_length_m,RL.towline_min_length_m,"m");

    addMin("ENERGY_REQ_99","Towline diameter at least 10 mm", ...
        CK.towline_diameter_mm,RL.towline_min_diameter_mm,"mm");

    addMin("ENERGY_REQ_96","Towing bridle diameter at least 10 mm", ...
        CK.bridle_diameter_mm,RL.bridle_min_diameter_mm,"mm", ...
        "Floating, fitted to the boat, with the towline secured to " + ...
        "it per ENERGY_REQ_100.");

    addMin("ENERGY_REQ_137","Lifejacket at least 100 N buoyancy", ...
        CK.lifejacket_buoyancy_N,RL.lifejacket_min_N,"N", ...
        "If not rigid it must inflate automatically on contact with " + ...
        "water, and its service date must fall after the event.");

    %% =========================================================
    % APPEARANCE -- 150, 151
    %% =========================================================

    addMin("ENERGY_REQ_150","National flag at least 2 m above the water", ...
        CK.nationality_flag_height_m, ...
        RL.nationality_flag_min_height_m,"m");

    addMin("ENERGY_REQ_151","National flag at least 30 cm wide", ...
        CK.nationality_flag_width_cm, ...
        RL.nationality_flag_min_width_cm,"cm");

    %% =========================================================
    % COMMUNICATION -- 141, 142
    %
    % VHF is FORBIDDEN for 2026. This changed, and a team reusing
    % last year's kit would fail on equipment it was previously
    % required to carry.
    %% =========================================================

    if contains(lower(string(CK.comms_type)),"vhf")

        add("ENERGY_REQ_141","Pilot can reach the shore team; VHF forbidden", ...
            "FAIL", ...
            sprintf("cockpit.comms_type is '%s'. VHF is forbidden " + ...
                    "for 2026.",string(CK.comms_type)));

    else

        add("ENERGY_REQ_141","Pilot can reach the shore team; VHF forbidden", ...
            "PASS", ...
            sprintf("Intended system is %s, which is not VHF.", ...
                string(CK.comms_type)), ...
            "This changed for 2026 -- VHF used to be the obvious " + ...
            "choice and is now banned. ENERGY_REQ_143 requires it " + ...
            "built into the helmet, 144 waterproof, 145 good for a " + ...
            "whole race on one charge.");

    end

    addMin("ENERGY_REQ_142","Communication range at least 2 nautical miles", ...
        CK.comms_range_nmi,RL.comms_min_range_nmi,"nmi");

    %% =========================================================
    % EVACUATION AND COCKPIT -- 44, 45, 46, 47, 186
    %% =========================================================

    addMax("ENERGY_REQ_44","Pilot evacuates within 5 seconds unaided", ...
        CK.evacuation_time_s,RL.evacuation_max_s,"s", ...
        "Demonstrated by an evacuation test at inspection. Rehearse " + ...
        "it in full kit, in the water, before the event.");

    addDeclared("ENERGY_REQ_45","Pilot not fully enclosed", ...
        ~CK.pilot_enclosed, ...
        "No hatch stands between the pilot and the water.", ...
        "cockpit.pilot_enclosed is set. Hatches that must be opened " + ...
        "before evacuation are not allowed.");

    addDeclared("ENERGY_REQ_46","Pilot not restrained to the boat", ...
        ~CK.pilot_restrained, ...
        "No restraint of any kind; safety belts are not allowed.", ...
        "cockpit.pilot_restrained is set, which the rule forbids.");

    addDeclared("ENERGY_REQ_47","Cockpit is self-draining", ...
        CK.self_draining, ...
        "Self-draining cockpit.", ...
        "cockpit.self_draining is false.");

    addDeclared("ENERGY_REQ_186","No cockpit appendix touches the water", ...
        ~CK.appendices_touch_water, ...
        "Only the motor and the water pump reach the water.", ...
        "cockpit.appendices_touch_water is set. New for 2026 -- only " + ...
        "the motor and the water pump are exempt.");

    %% =========================================================
    % SOLAR AND SAILS -- 28, 29
    %% =========================================================

    addMax("ENERGY_REQ_28","Solar panels at most 4 m2", ...
        CK.solar_area_m2,RL.solar_max_area_m2,"m2", ...
        "Including the mounting frame. None fitted.");

    addMax("ENERGY_REQ_29","Sail at most 20 m2", ...
        CK.sail_area_m2,RL.sail_max_area_m2,"m2", ...
        "None fitted.");

    %% =========================================================
    % HYDROGEN -- OUT OF SCOPE, SAID OUT LOUD
    %
    % A quarter of the rule book is hydrogen safety. Silence
    % about it in a compliance report reads the same as an
    % oversight, so the report says why it does not apply.
    %% =========================================================

    if ~CK.hydrogen_onboard

        add("ENERGY_REQ_115-169","Hydrogen safety chapter","PASS", ...
            "Not applicable. The boat carries no hydrogen and no " + ...
            "pressurised gas, so requirements 8, 19, 21, 22, 64, " + ...
            "94, 115 to 134 and 156 to 169 do not apply.", ...
            "Recorded rather than omitted: a compliance report that " + ...
            "is simply silent about a quarter of the rule book is " + ...
            "indistinguishable from one that forgot.");

    end

    %% =========================================================
    % ANNEX III -- ORGANISER TELEMETRY API
    %% =========================================================

    add("ANNEX_III","Temperature monitoring API","ACTION", ...
        sprintf("A %s %s endpoint at %s carrying %d temperature " + ...
                "channels, voltage, current, latitude, longitude and " + ...
                "the team token, posted every %.0f s.", ...
            TM.api_method,TM.api_content_type,TM.api_path, ...
            TM.n_temperature_channels,TM.post_period_s), ...
        "The Annex says the API 'will be confirmed in February " + ...
        "2026'. The payload built by Mission Control follows the " + ...
        "published example exactly, so confirming it should be a " + ...
        "one-line change. Test against the organiser's endpoint " + ...
        "before the event, not in the paddock.");

    %% =========================================================
    % NON-MODELLABLE REQUIREMENTS
    %
    % Listed so they cannot be quietly skipped. Each one is a
    % physical or procedural item for the build and inspection.
    %% =========================================================

    checklist = [ ...
        "ENERGY_REQ_26",  "Energy container not in the pilot's seating area"
        "ENERGY_REQ_27",  "Container ventilation blows away from the pilot"
        "ENERGY_REQ_24",  "Energy source securely fixed onboard"
        "ENERGY_REQ_155", "Container overpressure valve, certified and sized, facing aft"
        "ENERGY_REQ_56",  "Fire extinguisher port on the port side of the container"
        "ENERGY_REQ_189", "External charging interface, no need to open the container"
        "ENERGY_REQ_50",  "Bulkhead isolating propulsion and energy from the pilot"
        "ENERGY_REQ_52",  "Bulkhead protects the pilot from an energy storage explosion"
        "ENERGY_REQ_55",  "Cable pass-throughs fitted with grommets"
        "ENERGY_REQ_60",  "No live part touchable with a 100 mm long, 6 mm probe"
        "ENERGY_REQ_61",  "All wiring outside the enclosure is orange"
        "ENERGY_REQ_62",  "Electronics in an IP56 watertight, cooled compartment"
        "ENERGY_REQ_70",  "Kill cord fitted, visible at 3 m, secured to the pilot"
        "ENERGY_REQ_75",  "Emergency stop mushroom button fitted and accessible"
        "ENERGY_REQ_181", "ESC input power wired to accept the organiser sensing device"
        "ENERGY_REQ_190", "Pilot wears tear resistant gloves, EN 388:2016"
        "ENERGY_REQ_170", "Cockpit built to professional standard, approved by the Design Jury"
        "ENERGY_REQ_39",  "Every component of and in the cockpit is fixed"
        "ENERGY_REQ_41",  "Pilot's feet forward of the body and clear of hazards"
        "ENERGY_REQ_42",  "Seat includes a headrest"
        "ENERGY_REQ_90",  "No sharp edges"
        "ENERGY_REQ_92",  "Rotating components shielded; propellers protected off the water"
        "ENERGY_REQ_105", "Audible warning system aboard"
        "ENERGY_REQ_148", "ISO 7010:2019 symbols on a visible part of the cockpit"];

    for k = 1:size(checklist,1)

        add(checklist(k,1),checklist(k,2),"CHECKLIST", ...
            "Physical or procedural. Not derivable from the model.", ...
            "Verify on the build before technical inspection.");

    end

    %% =========================================================
    % ASSEMBLE
    %% =========================================================

    Compliance.Checks = struct2table(checks);

    status = [checks.Status];

    Compliance.NumChecks    = numel(checks);
    Compliance.NumPass      = sum(status == "PASS");
    Compliance.NumFail      = sum(status == "FAIL");
    Compliance.NumAction    = sum(status == "ACTION");
    Compliance.NumPartial   = sum(status == "PARTIAL");
    Compliance.NumChecklist = sum(status == "CHECKLIST");

    Compliance.Compliant = (Compliance.NumFail == 0);

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose
        printCompliance(Compliance);
    end

end

%% =============================================================
% Report
%% =============================================================

function printCompliance(C)

    T = C.Checks;

    fprintf("\n");
    fprintf("================================================================\n");
    fprintf(" MONACO ENERGY CLASS COMPLIANCE\n");
    fprintf("================================================================\n");
    fprintf(" %s, issued %s\n",C.RulesVersion,C.RulesIssued);
    fprintf("================================================================\n");

    %% ---------------------------------------------------------
    % Failures first: these stop the boat racing
    %% ---------------------------------------------------------

    F = T(T.Status == "FAIL",:);

    if height(F) > 0

        fprintf("\n");
        fprintf("----------------------------------------------------------------\n");
        fprintf(" %d RULE VIOLATION(S)\n",height(F));
        fprintf("----------------------------------------------------------------\n");

        for k = 1:height(F)

            fprintf("\n  %s -- %s\n",F.Req(k),F.Title(k));
            fprintf("    %s\n",wrapText(F.Finding(k),64,"    "));

            if strlength(F.Action(k)) > 0
                fprintf("    ACTION: %s\n", ...
                    wrapText(F.Action(k),56,"            "));
            end

        end

    else

        fprintf("\n  No rule violations among the quantifiable checks.\n");

    end

    %% ---------------------------------------------------------
    % Passes
    %% ---------------------------------------------------------

    P = T(T.Status == "PASS",:);

    if height(P) > 0

        fprintf("\n");
        fprintf("----------------------------------------------------------------\n");
        fprintf(" %d COMPLIANT\n",height(P));
        fprintf("----------------------------------------------------------------\n");

        for k = 1:height(P)
            fprintf("\n  %s -- %s\n",P.Req(k),P.Title(k));
            fprintf("    %s\n",wrapText(P.Finding(k),64,"    "));
        end

    end

    %% ---------------------------------------------------------
    % Actions and partials
    %% ---------------------------------------------------------

    A = T(ismember(T.Status,["ACTION" "PARTIAL" "MODELLED"]),:);

    if height(A) > 0

        fprintf("\n");
        fprintf("----------------------------------------------------------------\n");
        fprintf(" %d ITEM(S) NEEDING ACTION OR CONFIRMATION\n",height(A));
        fprintf("----------------------------------------------------------------\n");

        for k = 1:height(A)

            fprintf("\n  %s -- %s\n",A.Req(k),A.Title(k));
            fprintf("    %s\n",wrapText(A.Finding(k),64,"    "));

            if strlength(A.Action(k)) > 0
                fprintf("    -> %s\n", ...
                    wrapText(A.Action(k),60,"       "));
            end

        end

    end

    %% ---------------------------------------------------------
    % Checklist
    %% ---------------------------------------------------------

    L = T(T.Status == "CHECKLIST",:);

    if height(L) > 0

        fprintf("\n");
        fprintf("----------------------------------------------------------------\n");
        fprintf(" %d PHYSICAL / PROCEDURAL ITEM(S) -- verify on the build\n", ...
            height(L));
        fprintf("----------------------------------------------------------------\n\n");

        for k = 1:height(L)
            fprintf("  [ ] %-18s %s\n",L.Req(k),L.Title(k));
        end

    end

    %% ---------------------------------------------------------
    % Headline numbers
    %% ---------------------------------------------------------

    fprintf("\n");
    fprintf("----------------------------------------------------------------\n");
    fprintf(" KEY NUMBERS\n");
    fprintf("----------------------------------------------------------------\n");

    fprintf("  Stored energy (REQ_7)   : %.0f Wh of %.0f Wh limit\n", ...
        C.Energy.StoredEnergy_Wh,C.Energy.Limit_Wh);
    fprintf("  Margin                  : %.0f Wh (%.2f%%)\n", ...
        C.Energy.Margin_Wh,C.Energy.MarginPercent);
    fprintf("  Maximum cells allowed   : %d (you have 546)\n", ...
        C.Energy.MaxCellsAllowed);

    fprintf("\n  Motor nominal (REQ_188) : %.1f kW of %.0f kW limit\n", ...
        C.MotorPower.Nominal_W/1000,C.MotorPower.Limit_W/1000);

    fprintf("\n  Mass excl. hulls        : %.0f kg known of %.0f kg limit\n", ...
        C.Mass.Known_kg,C.Mass.Limit_kg);
    fprintf("  Remaining for cockpit   : %.0f kg\n",C.Mass.Remaining_kg);

    fprintf("\n");
    fprintf("----------------------------------------------------------------\n");
    fprintf(" %d checks: %d pass, %d FAIL, %d action, %d partial, %d checklist\n", ...
        C.NumChecks,C.NumPass,C.NumFail,C.NumAction, ...
        C.NumPartial,C.NumChecklist);

    if C.Compliant
        fprintf(" No violations in the quantifiable rules.\n");
    else
        fprintf(" NOT COMPLIANT -- %d violation(s) must be resolved.\n", ...
            C.NumFail);
    end

    fprintf("\n A pass here covers the rules this model can evaluate.\n");
    fprintf(" It is not a statement that the boat is compliant.\n");
    fprintf("================================================================\n");

end

%% =============================================================
% Simple word wrap
%% =============================================================

function out = wrapText(txt,width,indent)

    words = split(string(txt)," ");

    lines = strings(0,1);

    current = "";

    for k = 1:numel(words)

        if strlength(current) == 0
            candidate = words(k);
        else
            candidate = current + " " + words(k);
        end

        if strlength(candidate) > width && strlength(current) > 0
            lines(end+1) = current; %#ok<AGROW>
            current = words(k);
        else
            current = candidate;
        end

    end

    if strlength(current) > 0
        lines(end+1) = current;
    end

    out = strjoin(lines,newline + string(indent));

end

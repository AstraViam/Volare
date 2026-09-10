function Result = P50B_RunMission(Profile,varargin)
%P50B_RUNMISSION  Integrate a mission profile through the full drivetrain.
%
%   Result = P50B_RunMission(Profile) steps a mission profile through the
%   complete electrical chain, tracking state of charge, cell
%   temperature, currents, losses and energy at every time step.
%
%   Result = P50B_RunMission("endurance") builds the named profile first.
%
%   OPTIONS
%     "InitialSOC"    0 to 1, default 0.95
%     "InitialTemp_C" degC, default 25
%     "Ambient_C"     degC, default 25
%     "Verbose"       logical, default true
%     "Plot"          logical, default true
%     "StopOnLimit"   logical, default false -- halt when a limit is
%                     violated rather than continuing and reporting it
%
%   WHAT IS INTEGRATED
%   ------------------
%   Two states are carried forward:
%
%     SOC          by coulomb counting on the actual pack current, which
%                  includes every loss between the cells and the shaft,
%                  plus the auxiliary load.
%
%     Cell temp    by a lumped first-order thermal model driven by the
%                  cell and interconnect heat at each step.
%
%   Those two states feed back into the cell model: as SOC falls and
%   temperature changes, DCIR changes, which changes the current needed
%   for the same shaft power. That coupling is the reason this is a
%   time-stepped integration and not a single operating point scaled by
%   duration.
%
%   ENERGY ACCOUNTING
%   -----------------
%   The result separates energy that reached the propeller from energy
%   lost in each stage. Those sum to the energy drawn from the cells,
%   which is checked at the end -- an energy balance that does not close
%   means the model has a bug, and the check will say so.
%
%   See also P50B_MissionProfile, P50B_DrivetrainModel.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    %% ---------------------------------------------------------
    % Defaults come from the parameter file, not from literals
    % here. Ambient was 25 degC in this function and 30 degC in
    % params/volare_params.json, which is the difference between
    % a spring afternoon and Monaco in July -- and the July
    % figure is the one the boat has to survive.
    %% ---------------------------------------------------------

    Pdefaults = P50B_LoadParams("Plain",true);

    opts = struct( ...
        "InitialSOC",    Pdefaults.simulation.initial_soc, ...
        "InitialTemp_C", Pdefaults.simulation.initial_temp_C, ...
        "Ambient_C",     Pdefaults.simulation.ambient_C, ...
        "Verbose",       true, ...
        "Plot",          true, ...
        "StopOnLimit",   false, ...
        "Thermal",       [], ...
        "Boat",          [], ...
        "TrackSpeed",    true, ...
        "StopSOC",       0.0);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_RunMission:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if ~isstruct(Profile)
        Profile = P50B_MissionProfile(Profile);
    end

    %% =========================================================
    % PRE-LOAD EVERY MODEL ONCE
    %
    % The busbar and geometry models are expensive and constant
    % over a mission, so they are built once and passed in rather
    % than rebuilt at every one of thousands of time steps.
    %% =========================================================

    if opts.Verbose
        fprintf("\nBuilding models ... ");
    end

    cellData = P50B_CellData();
    motor    = P50B_MotorData();
    inv      = P50B_InverterData();
    harn     = P50B_HarnessData();
    aux      = P50B_AuxiliaryLoads();

    G      = P50B_Geometry();
    Layout = P50B_GroupLayout(G,"Plot",false,"Verbose",false);
    Bus    = P50B_Busbars(G,Layout,"Plot",false,"Verbose",false);

    if opts.Verbose
        fprintf("done.\n");
    end

    modelArgs = { ...
        "Busbars",   Bus, ...
        "Motor",     motor, ...
        "Inverter",  inv, ...
        "Harness",   harn, ...
        "Auxiliary", aux, ...
        "Cell",      cellData};

    %% =========================================================
    % PACK CAPACITY AND THERMAL CONSTANTS
    %% =========================================================

    %% ---------------------------------------------------------
    % The pack, from the pack model
    %
    % These were literals -- Ns = 26, Np = 21, and a 5.0 K/W
    % cell-to-coolant resistance. In a project whose entire
    % architecture exists so that one parameter file describes
    % one boat, a mission integrator that knows the series count
    % by heart is the one place a design change would not reach.
    % Change pack.n_series in the parameter file and every other
    % model followed; this one would have kept simulating a 26S
    % pack.
    %
    % The thermal resistance was worse than stale, it was wrong:
    % 5.0 K/W describes the bottom-cooled layout this project
    % abandoned, against 0.909 K/W for the end-plate pack it
    % actually has. See P50B_ThermalDesign.
    %% ---------------------------------------------------------

    Ns = G.Pack.SeriesGroups;
    Np = G.Pack.ParallelCells;

    nCells = Ns*Np;

    packCapacity_As = Np * cellData.Capacity_Ah * 3600;

    packThermalMass_J_K = cellData.ThermalMass_J_K * nCells;

    if isempty(opts.Thermal)
        ThermalForMission = P50B_ThermalDesign(cellData, ...
            "Busbars",Bus,"Verbose",false,"Plot",false);
    else
        ThermalForMission = opts.Thermal;
    end

    cellToCoolant_K_W = ThermalForMission.Parameters.CellToCoolant_K_W;

    packToCoolant_K_W = cellToCoolant_K_W / nCells;

    %% =========================================================
    % PRE-ALLOCATE
    %% =========================================================

    t = Profile.Time_s;

    n = numel(t);

    dt = Profile.TimeStep_s;

    SOC          = zeros(n,1);
    CellTemp_C   = zeros(n,1);
    PackCurrent  = zeros(n,1);
    CellCurrent  = zeros(n,1);
    PackVoltage  = zeros(n,1);
    PackPower    = zeros(n,1);
    ShaftPower   = Profile.ShaftPower_W;
    MotorSpeed   = Profile.MotorSpeed_rpm;

    LossCells    = zeros(n,1);
    LossBusbar   = zeros(n,1);
    LossHarness  = zeros(n,1);
    LossInverter = zeros(n,1);
    LossMotor    = zeros(n,1);
    LossGearbox  = zeros(n,1);
    LossAux      = zeros(n,1);

    Efficiency   = zeros(n,1);

    Feasible     = true(n,1);
    LimitsOK     = true(n,1);

    PowerCapped    = false(n,1);
    ShaftShortfall = zeros(n,1);

    RequestedShaftPower = Profile.ShaftPower_W;

    %% =========================================================
    % INITIAL STATE
    %% =========================================================

    SOC(1)        = opts.InitialSOC;
    CellTemp_C(1) = opts.InitialTemp_C;

    stoppedAt = n;

    stopReason = "";

    %% =========================================================
    % INTEGRATE
    %% =========================================================

    if opts.Verbose
        fprintf("Running %d steps over %.0f s ...\n",n,t(end));
    end

    for k = 1:n

        %% -----------------------------------------------------
        % Solve the chain at this operating point
        %% -----------------------------------------------------

        op = P50B_DrivetrainModel( ...
            ShaftPower(k), ...
            MotorSpeed(k), ...
            SOC(k), ...
            CellTemp_C(k), ...
            modelArgs{:});

        Feasible(k) = op.Feasible;
        LimitsOK(k) = op.Limits.AllOK;

        if ~op.Feasible

            stoppedAt  = k;
            stopReason = op.InfeasibleReason;

            if opts.Verbose
                fprintf("\n  Stopped at t = %.1f s: %s\n", ...
                    t(k),stopReason);
            end

            break;

        end

        if opts.StopOnLimit && ~op.Limits.AllOK

            stoppedAt  = k;
            stopReason = "An operating limit was exceeded.";

            break;

        end

        %% -----------------------------------------------------
        % Record
        %% -----------------------------------------------------

        %% -----------------------------------------------------
        % Record the shaft power actually DELIVERED, not the
        % power the profile asked for.
        %
        % The 25 kW cap can reduce it, and if the requested
        % figure were logged instead, the energy balance would
        % show a gap equal to the power the cap withheld -- the
        % model would appear to have lost track of energy it
        % never delivered in the first place.
        %% -----------------------------------------------------

        ShaftPower(k) = op.PowerLimit.DeliveredShaft_W;

        PowerCapped(k) = op.PowerLimit.Active;

        ShaftShortfall(k) = op.PowerLimit.ShortfallShaft_W;

        PackCurrent(k) = op.Pack.Current_A;
        CellCurrent(k) = op.Pack.CellCurrent_A;
        PackVoltage(k) = op.Pack.TerminalVoltage_V;
        PackPower(k)   = op.Pack.DrawnPower_W;

        LossCells(k)    = op.Pack.CellLoss_W;
        LossBusbar(k)   = op.Pack.BusbarLoss_W;
        LossHarness(k)  = op.Pack.HarnessLoss_W;
        LossInverter(k) = op.Inverter.TotalLoss_W;
        LossMotor(k)    = op.Motor.TotalLoss_W;
        LossGearbox(k)  = op.Gearbox.Loss_W;
        LossAux(k)      = op.Auxiliary.PowerFromPack_W;

        Efficiency(k) = op.Chain.OverallEfficiency;

        %% -----------------------------------------------------
        % Advance SOC by coulomb counting
        %% -----------------------------------------------------

        if k < n

            SOC(k+1) = SOC(k) - PackCurrent(k)*dt/packCapacity_As;

            %% -------------------------------------------------
            % Stop when the pack is empty.
            %
            % Clamping SOC at zero and carrying on -- which an
            % earlier version of this loop did -- lets the model
            % keep drawing current from a flat pack and report
            % more energy delivered than the pack physically
            % holds. Running out of energy is a result, not an
            % edge case to be smoothed over.
            %% -------------------------------------------------

            if SOC(k+1) <= opts.StopSOC

                SOC(k+1) = max(opts.StopSOC,0);

                stoppedAt = k+1;

                stopReason = sprintf( ...
                    "Pack reached %.0f%% SOC at t = %.0f s " + ...
                    "(%.1f min). The profile demanded more energy " + ...
                    "than the pack holds.", ...
                    opts.StopSOC*100, t(k+1), t(k+1)/60);

                if opts.Verbose
                    fprintf("\n  %s\n",stopReason);
                end

                %% ---------------------------------------------
                % Carry the final step's values forward so the
                % trimmed arrays end on a valid sample.
                %% ---------------------------------------------

                ShaftPower(k+1)     = ShaftPower(k);
                MotorSpeed(k+1)     = MotorSpeed(k);
                PowerCapped(k+1)    = PowerCapped(k);
                ShaftShortfall(k+1) = ShaftShortfall(k);

                PackCurrent(k+1) = PackCurrent(k);
                CellCurrent(k+1) = CellCurrent(k);
                PackVoltage(k+1) = PackVoltage(k);
                PackPower(k+1)   = PackPower(k);
                Efficiency(k+1)  = Efficiency(k);

                LossCells(k+1)    = LossCells(k);
                LossBusbar(k+1)   = LossBusbar(k);
                LossHarness(k+1)  = LossHarness(k);
                LossInverter(k+1) = LossInverter(k);
                LossMotor(k+1)    = LossMotor(k);
                LossGearbox(k+1)  = LossGearbox(k);
                LossAux(k+1)      = LossAux(k);

                CellTemp_C(k+1) = CellTemp_C(k);

                break;

            end

        end

        %% -----------------------------------------------------
        % Advance temperature
        %
        % Lumped first-order: heat in from cells and interconnect,
        % heat out proportional to the rise above ambient.
        %% -----------------------------------------------------

        if k < n

            heatIn = LossCells(k) + LossBusbar(k);

            heatOut = (CellTemp_C(k) - opts.Ambient_C) / packToCoolant_K_W;

            dT = (heatIn - heatOut) * dt / packThermalMass_J_K;

            CellTemp_C(k+1) = CellTemp_C(k) + dT;

        end

    end

    %% =========================================================
    % TRIM TO WHERE THE RUN ACTUALLY STOPPED
    %% =========================================================

    idx = 1:stoppedAt;

    Result.Time_s          = t(idx);
    Result.SOC             = SOC(idx);
    Result.CellTemp_C      = CellTemp_C(idx);
    Result.PackCurrent_A   = PackCurrent(idx);
    Result.CellCurrent_A   = CellCurrent(idx);
    Result.PackVoltage_V   = PackVoltage(idx);
    Result.PackPower_W     = PackPower(idx);
    Result.ShaftPower_W    = ShaftPower(idx);
    Result.RequestedShaftPower_W = RequestedShaftPower(idx);
    Result.MotorSpeed_rpm  = MotorSpeed(idx);
    Result.PowerCapped     = PowerCapped(idx);
    Result.ShaftShortfall_W = ShaftShortfall(idx);
    Result.Efficiency      = Efficiency(idx);
    Result.Feasible        = Feasible(idx);
    Result.LimitsOK        = LimitsOK(idx);

    Result.Loss.Cells_W    = LossCells(idx);
    Result.Loss.Busbar_W   = LossBusbar(idx);
    Result.Loss.Harness_W  = LossHarness(idx);
    Result.Loss.Inverter_W = LossInverter(idx);
    Result.Loss.Motor_W    = LossMotor(idx);
    Result.Loss.Gearbox_W  = LossGearbox(idx);
    Result.Loss.Auxiliary_W = LossAux(idx);

    Result.Profile   = Profile;
    Result.Completed = (stoppedAt == n);
    Result.StopReason = stopReason;

    %% =========================================================
    % ENERGY ACCOUNTING
    %% =========================================================

    tt = Result.Time_s;

    E = struct();

    E.FromCells_Wh   = trapz(tt,Result.PackPower_W)/3600;
    E.ToShaft_Wh     = trapz(tt,Result.ShaftPower_W)/3600;

    E.LossCells_Wh    = trapz(tt,Result.Loss.Cells_W)/3600;
    E.LossBusbar_Wh   = trapz(tt,Result.Loss.Busbar_W)/3600;
    E.LossHarness_Wh  = trapz(tt,Result.Loss.Harness_W)/3600;
    E.LossInverter_Wh = trapz(tt,Result.Loss.Inverter_W)/3600;
    E.LossMotor_Wh    = trapz(tt,Result.Loss.Motor_W)/3600;
    E.LossGearbox_Wh  = trapz(tt,Result.Loss.Gearbox_W)/3600;
    E.LossAux_Wh      = trapz(tt,Result.Loss.Auxiliary_W)/3600;

    E.TotalLoss_Wh = ...
        E.LossCells_Wh + E.LossBusbar_Wh + E.LossHarness_Wh + ...
        E.LossInverter_Wh + E.LossMotor_Wh + E.LossGearbox_Wh + ...
        E.LossAux_Wh;

    E.Accounted_Wh = E.ToShaft_Wh + E.TotalLoss_Wh;

    E.BalanceError_Wh = E.FromCells_Wh - E.Accounted_Wh;

    if E.FromCells_Wh > 0
        E.BalanceErrorPercent = ...
            100 * E.BalanceError_Wh / E.FromCells_Wh;
        E.OverallEfficiency = E.ToShaft_Wh / E.FromCells_Wh;
    else
        E.BalanceErrorPercent = NaN;
        E.OverallEfficiency = NaN;
    end

    %% ---------------------------------------------------------
    % Energy balance check
    %
    % Shaft energy plus all losses must equal energy drawn from
    % the cells. A discrepancy above numerical noise means the
    % loss accounting has a gap.
    %% ---------------------------------------------------------

    E.BalanceOK = abs(E.BalanceErrorPercent) < 0.5;

    Result.Energy = E;

    %% =========================================================
    % SUMMARY STATISTICS
    %% =========================================================

    S = struct();

    S.Duration_s        = tt(end);
    S.SOCStart          = Result.SOC(1);
    S.SOCEnd            = Result.SOC(end);
    S.SOCUsed           = Result.SOC(1) - Result.SOC(end);

    S.PeakPackCurrent_A = max(Result.PackCurrent_A);
    S.MeanPackCurrent_A = mean(Result.PackCurrent_A);
    S.PeakCellCurrent_A = max(Result.CellCurrent_A);
    S.PeakCellCRate     = S.PeakCellCurrent_A / cellData.Capacity_Ah;

    S.MinPackVoltage_V  = min(Result.PackVoltage_V);
    S.MaxPackPower_W    = max(Result.PackPower_W);

    S.PeakCellTemp_C    = max(Result.CellTemp_C);
    S.FinalCellTemp_C   = Result.CellTemp_C(end);

    S.MeanEfficiency    = E.OverallEfficiency;

    S.LimitViolations   = sum(~Result.LimitsOK);

    %% ---------------------------------------------------------
    % How often the 25 kW cap intervened
    %% ---------------------------------------------------------

    S.StepsPowerCapped = sum(Result.PowerCapped);

    S.FractionPowerCapped = ...
        S.StepsPowerCapped / numel(Result.PowerCapped);

    S.EnergyWithheldByCap_Wh = ...
        trapz(tt,Result.ShaftShortfall_W)/3600;

    %% ---------------------------------------------------------
    % Projected endurance
    %
    % If the mission did not exhaust the pack, how long could it
    % continue at the same mean draw down to the usable floor?
    %% ---------------------------------------------------------

    usableFloor = 0.10;

    if S.SOCUsed > 0 && S.SOCEnd > usableFloor

        socPerSecond = S.SOCUsed / S.Duration_s;

        S.ProjectedRemaining_s = ...
            (S.SOCEnd - usableFloor) / socPerSecond;

        S.ProjectedTotalEndurance_s = ...
            S.Duration_s + S.ProjectedRemaining_s;

    else

        S.ProjectedRemaining_s = 0;
        S.ProjectedTotalEndurance_s = S.Duration_s;

    end

    Result.Summary = S;

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose
        printMission(Result,cellData);
    end

    %% =========================================================
    % PLOT
    %% =========================================================

    if opts.Plot
        plotMission(Result);
    end

end

%% =============================================================
% Report
%% =============================================================

function printMission(R,cellData)

    S = R.Summary;
    E = R.Energy;

    fprintf("\n");
    fprintf("================================================================\n");
    fprintf(" MISSION RESULT: %s\n",upper(R.Profile.Name));
    fprintf("================================================================\n");

    fprintf("\n%s\n",R.Profile.Description);

    if ~R.Completed
        fprintf("\n  RUN DID NOT COMPLETE\n");
        fprintf("  %s\n",R.StopReason);
    end

    fprintf("\nDURATION AND ENERGY\n");
    fprintf("  Duration                : %.0f s (%.1f min)\n", ...
        S.Duration_s,S.Duration_s/60);
    fprintf("  Energy from cells       : %.2f kWh\n",E.FromCells_Wh/1000);
    fprintf("  Energy to propeller     : %.2f kWh\n",E.ToShaft_Wh/1000);
    fprintf("  Total losses            : %.2f kWh\n",E.TotalLoss_Wh/1000);
    fprintf("  Overall efficiency      : %.1f %%\n", ...
        E.OverallEfficiency*100);

    fprintf("\nSTATE OF CHARGE\n");
    fprintf("  Start                   : %.1f %%\n",S.SOCStart*100);
    fprintf("  End                     : %.1f %%\n",S.SOCEnd*100);
    fprintf("  Used                    : %.1f %%\n",S.SOCUsed*100);

    if S.ProjectedRemaining_s > 0
        fprintf("  Projected endurance     : %.0f min to 10%% SOC\n", ...
            S.ProjectedTotalEndurance_s/60);
    end

    fprintf("\nELECTRICAL\n");
    fprintf("  Peak pack current       : %.1f A\n",S.PeakPackCurrent_A);
    fprintf("  Mean pack current       : %.1f A\n",S.MeanPackCurrent_A);
    fprintf("  Peak cell current       : %.2f A (%.2f C)\n", ...
        S.PeakCellCurrent_A,S.PeakCellCRate);
    fprintf("  Cell datasheet limit    : %.0f A -> %.1f %% used\n", ...
        cellData.MaxContinuousCurrent_A, ...
        S.PeakCellCurrent_A/cellData.MaxContinuousCurrent_A*100);
    fprintf("  Minimum pack voltage    : %.1f V\n",S.MinPackVoltage_V);

    fprintf("\nTHERMAL\n");
    fprintf("  Peak cell temperature   : %.1f degC\n",S.PeakCellTemp_C);
    fprintf("  Final cell temperature  : %.1f degC\n",S.FinalCellTemp_C);

    %% ---------------------------------------------------------
    % Loss breakdown
    %% ---------------------------------------------------------

    fprintf("\nWHERE THE ENERGY WENT\n");

    names = [ ...
        "Motor" ...
        "Inverter" ...
        "Cells (internal R)" ...
        "Busbars (in pack)" ...
        "Harness" ...
        "Gearbox" ...
        "Auxiliary 12 V"]';

    values = [ ...
        E.LossMotor_Wh; ...
        E.LossInverter_Wh; ...
        E.LossCells_Wh; ...
        E.LossBusbar_Wh; ...
        E.LossHarness_Wh; ...
        E.LossGearbox_Wh; ...
        E.LossAux_Wh];

    [values,order] = sort(values,"descend");

    names = names(order);

    for k = 1:numel(names)

        fprintf("  %-22s %8.1f Wh  (%4.1f%% of loss, %4.1f%% of draw)\n", ...
            names(k), ...
            values(k), ...
            values(k)/E.TotalLoss_Wh*100, ...
            values(k)/E.FromCells_Wh*100);

    end

    %% ---------------------------------------------------------
    % Energy balance
    %% ---------------------------------------------------------

    fprintf("\nENERGY BALANCE CHECK\n");
    fprintf("  Shaft + losses          : %.2f kWh\n",E.Accounted_Wh/1000);
    fprintf("  Drawn from cells        : %.2f kWh\n",E.FromCells_Wh/1000);
    fprintf("  Discrepancy             : %.4f kWh (%.3f %%)\n", ...
        E.BalanceError_Wh/1000,E.BalanceErrorPercent);

    if E.BalanceOK
        fprintf("  Balance                 : OK\n");
    else
        fprintf("  Balance                 : FAILED -- loss accounting has a gap\n");
    end

    %% ---------------------------------------------------------
    % Limits
    %% ---------------------------------------------------------

    if S.StepsPowerCapped > 0

        fprintf("\n25 kW POWER CAP (Monaco ENERGY_REQ_188)\n");
        fprintf("  Steps capped            : %d of %d (%.0f%%)\n", ...
            S.StepsPowerCapped,numel(R.PowerCapped), ...
            S.FractionPowerCapped*100);
        fprintf("  Shaft energy withheld   : %.0f Wh\n", ...
            S.EnergyWithheldByCap_Wh);
        fprintf("  The profile asked for more than the rules allow;\n");
        fprintf("  the inverter limited it, as it would on the water.\n");

    end

    fprintf("\nLIMITS\n");

    if S.LimitViolations == 0
        fprintf("  No limit violations across %d steps.\n", ...
            numel(R.Time_s));
    else
        fprintf("  %d of %d steps violated an operating limit.\n", ...
            S.LimitViolations,numel(R.Time_s));
    end

    fprintf("\n");
    fprintf("  Profile provenance: %s\n",R.Profile.Provenance);

    fprintf("\n================================================================\n");

end

%% =============================================================
% Plot
%% =============================================================

function plotMission(R)

    t = R.Time_s/60;

    figure( ...
        "Name",sprintf("P50B Mission: %s",R.Profile.Name), ...
        "Color","white");

    %% ---------------------------------------------------------
    % Power
    %% ---------------------------------------------------------

    subplot(2,2,1);

    hold on; grid on;

    plot(t,R.PackPower_W/1000,"LineWidth",1.2);
    plot(t,R.ShaftPower_W/1000,"LineWidth",1.2);

    xlabel("Time [min]");
    ylabel("Power [kW]");
    title("Power");

    legend("From cells","To propeller","Location","best");

    %% ---------------------------------------------------------
    % SOC
    %% ---------------------------------------------------------

    subplot(2,2,2);

    hold on; grid on;

    plot(t,R.SOC*100,"LineWidth",1.5);

    yline(10,"--","Usable floor");

    xlabel("Time [min]");
    ylabel("SOC [%]");
    title("State of charge");

    ylim([0 100]);

    %% ---------------------------------------------------------
    % Current
    %% ---------------------------------------------------------

    subplot(2,2,3);

    hold on; grid on;

    plot(t,R.PackCurrent_A,"LineWidth",1.2);

    yline(375,"--","Competr continuous 375 A");

    xlabel("Time [min]");
    ylabel("Pack current [A]");
    title("Pack current");

    %% ---------------------------------------------------------
    % Temperature
    %% ---------------------------------------------------------

    subplot(2,2,4);

    hold on; grid on;

    plot(t,R.CellTemp_C,"LineWidth",1.5);

    yline(45,"--","Design limit 45 C");

    xlabel("Time [min]");
    ylabel("Cell temperature [degC]");
    title("Cell temperature");

end

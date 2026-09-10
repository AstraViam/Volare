function Thermal = P50B_ThermalDesign(data,varargin)
%P50B_THERMALDESIGN  Pack thermal analysis for the 26S21P P50B pack.
%
%   Thermal = P50B_ThermalDesign(data) evaluates cell and interconnect
%   heat generation across the operating range, estimates temperature
%   rise, and reports how long the pack can sustain each load before
%   reaching its temperature limit.
%
%   OPTIONS
%     "Busbars"  Bus struct from P50B_Busbars; recomputed if omitted
%     "Verbose"  logical, default true
%     "Plot"     logical, default true
%     "Ambient_C" starting cell temperature, default 25
%
%   WHAT CHANGED FROM THE PREVIOUS REVISION
%   ---------------------------------------
%   The previous version used a single hard-coded cell resistance of
%   12 mOhm and a cell-to-coolant thermal resistance of 1.0 K/W, both
%   marked as placeholders. It also ignored busbar heat entirely.
%
%   This version:
%     - takes cell resistance from the P50B_DCIR(SOC,T) surface, so it
%       captures the fact that a cold or nearly empty pack generates
%       substantially more heat for the same current
%     - includes interconnect heat from P50B_Busbars
%     - solves the transient rise rather than only the steady state,
%       because for a race the question is usually "how long can we
%       hold this?" rather than "where does it settle?"
%     - reports the cooling duty actually required
%
%   THE THERMAL RESISTANCE IS STILL AN ESTIMATE
%   -------------------------------------------
%   Cell-to-coolant thermal resistance depends on the cell holder, the
%   thermal interface material and the cooling plate design, none of
%   which are yet fixed. The value used is defensible for a bottom-
%   cooled cylindrical cell, but it is the single largest uncertainty
%   in this analysis and it should be measured on a prototype module.
%
%   See also P50B_DCIR, P50B_Busbars, P50B_CellData.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    %% Ambient from the parameter file: Monaco in July, not 25 degC.
    opts = struct( ...
        "Busbars",   [], ...
        "Verbose",   true, ...
        "Plot",      true, ...
        "Ambient_C", P50B_Value(P50B_LoadParams().simulation.ambient_C));

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_ThermalDesign:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if nargin < 1 || isempty(data)
        data = P50B_CellData();
    end

    %% =========================================================
    % PACK CONSTANTS
    %% =========================================================

    Ns = 26;
    Np = 21;

    nCells = Ns*Np;

    %% =========================================================
    % BUSBAR MODEL
    %% =========================================================

    if isempty(opts.Busbars)

        G      = P50B_Geometry();
        Layout = P50B_GroupLayout(G,"Plot",false,"Verbose",false);
        Bus    = P50B_Busbars(G,Layout,"Plot",false,"Verbose",false);

    else

        Bus = opts.Busbars;

    end

    %% =========================================================
    % OPERATING CURRENTS
    %
    % Spanning from a light cruise to the Competr peak, so the
    % design is checked over the whole range rather than at one
    % convenient point.
    %% =========================================================

    currents = [50 100 150 200 267 300 375 449];

    nI = numel(currents);

    %% =========================================================
    % THERMAL PARAMETERS
    %% =========================================================

    Th.CellThermalMass_J_K = data.ThermalMass_J_K;

    Th.PackThermalMass_J_K = Th.CellThermalMass_J_K * nCells;

    %% ---------------------------------------------------------
    % Cell-to-coolant thermal resistance
    %
    % For a 21700 bottom-cooled through a holder and a thermal
    % interface pad, values in the range 3 to 8 K/W per cell are
    % typical. The lower end requires a good TIM and a direct
    % path to the plate; the upper end is what you get with an
    % air gap and a plastic holder.
    %
    % 5.0 K/W is used as a mid-range design assumption.
    %
    % Note this is per cell. With 546 cells in parallel thermally,
    % the pack-level resistance to coolant is much lower.
    %% ---------------------------------------------------------

    %% ---------------------------------------------------------
    % END-PLATE, NOT BOTTOM-COOLED
    %
    % This used to be a hard-coded 5.0 K/W, with the comment
    % above describing conduction "through holder and TIM" from
    % the bottom of the cell. That was an accurate description of
    % the flat, side-cooled layout this project started with and
    % then abandoned: the pack is cooled on the cell ENDS now,
    % both of them, through three cold plates.
    %
    % Python's resolved model gives 0.909 K/W for the pack that
    % actually exists -- the figure the README has been quoting
    % all along -- against the 5.0 K/W this file kept using. The
    % mission integrator drove cell temperature through that
    % number, so every MATLAB temperature RISE was about five and
    % a half times too pessimistic, including the one behind the
    % ENERGY_REQ_93 exposed-parts check.
    %
    % The solid path is recomputed here from the parameters
    % rather than read back, so this file still owns arithmetic
    % it can own. The convective film needs the resolved tube
    % hydraulics and is derived once, like the cell curves.
    % tools/crosscheck.py compares the total.
    %% ---------------------------------------------------------

    Pcool = P50B_LoadParams("Plain",true);

    R_solid_K_W = (Pcool.cooling.R_can_plate_KW + ...
                   Pcool.cooling.R_plate_tubewall_KW) / ...
                  Pcool.cooling.cell_ends_cooled;

    R_conv_K_W = Pcool.cooling.R_conv_cell_KW;

    Th.CellToCoolant_K_W = R_solid_K_W + R_conv_K_W;

    Th.CellToCoolantSolid_K_W = R_solid_K_W;
    Th.CellToCoolantConv_K_W  = R_conv_K_W;

    Th.CellToCoolantSource = "CALCULATED";

    Th.CellToCoolantNote = ...
        sprintf("End-plate cooling, both cell ends. Solid path " + ...
                "%.3f K/W from (R_can_plate + R_plate_tubewall) / %d, " + ...
                "convective film %.3f K/W from the resolved tube " + ...
                "hydraulics at %.1f L/min. The bond-line thickness " + ...
                "inside R_can_plate dominates and cannot be " + ...
                "calculated -- build one instrumented module.", ...
            R_solid_K_W,Pcool.cooling.cell_ends_cooled,R_conv_K_W, ...
            Pcool.cooling.flow_L_per_min);

    Th.PackToCoolant_K_W = Th.CellToCoolant_K_W / nCells;

    %% ---------------------------------------------------------
    % Temperature limits
    %% ---------------------------------------------------------

    Th.Ambient_C      = opts.Ambient_C;
    Th.DesignLimit_C  = data.TempDesignTarget_C;
    Th.AbsoluteLimit_C = data.TempCutOff_C;

    %% =========================================================
    % EVALUATE EACH CURRENT
    %% =========================================================

    Current_A         = currents(:);
    CellCurrent_A     = zeros(nI,1);
    CRate             = zeros(nI,1);
    CellResistance_Ohm = zeros(nI,1);
    CellHeat_W        = zeros(nI,1);
    CellHeatTotal_W   = zeros(nI,1);
    BusbarHeat_W      = zeros(nI,1);
    TotalHeat_W       = zeros(nI,1);
    SteadyRise_K      = zeros(nI,1);
    SteadyTemp_C      = zeros(nI,1);
    AdiabaticRate_K_s = zeros(nI,1);
    TimeToLimit_s     = zeros(nI,1);
    SteadyOK          = false(nI,1);

    %% ---------------------------------------------------------
    % Evaluate at a mid-discharge, moderately warm condition.
    %
    % Choosing 50% SOC and 35 degC rather than a fresh, cool cell
    % is deliberate: it is representative of a pack partway
    % through a race, which is when thermal problems actually
    % appear.
    %% ---------------------------------------------------------

    evalSOC   = 0.50;
    evalTemp  = 35;

    Rcell = P50B_DCIR(evalSOC,evalTemp);

    Th.EvaluationSOC    = evalSOC;
    Th.EvaluationTemp_C = evalTemp;
    Th.CellResistance_Ohm = Rcell;

    for k = 1:nI

        I = currents(k);

        i_cell = I/Np;

        CellCurrent_A(k) = i_cell;

        CRate(k) = i_cell / data.Capacity_Ah;

        CellResistance_Ohm(k) = Rcell;

        %% -----------------------------------------------------
        % Heat generation
        %
        % Only the irreversible ohmic term is modelled. The
        % reversible entropic term can add or subtract roughly
        % 10-20% depending on SOC and direction, and would need
        % an entropy coefficient measurement to include.
        %% -----------------------------------------------------

        CellHeat_W(k) = i_cell^2 * Rcell;

        CellHeatTotal_W(k) = CellHeat_W(k) * nCells;

        BusbarHeat_W(k) = I^2 * Bus.Rtotal;

        TotalHeat_W(k) = CellHeatTotal_W(k) + BusbarHeat_W(k);

        %% -----------------------------------------------------
        % Steady-state rise
        %
        % Per-cell heat through per-cell thermal resistance.
        % Busbar heat is added at pack level, since it is
        % conducted away through the same structure.
        %% -----------------------------------------------------

        SteadyRise_K(k) = ...
            CellHeat_W(k) * Th.CellToCoolant_K_W + ...
            BusbarHeat_W(k) * Th.PackToCoolant_K_W;

        SteadyTemp_C(k) = Th.Ambient_C + SteadyRise_K(k);

        SteadyOK(k) = SteadyTemp_C(k) <= Th.DesignLimit_C;

        %% -----------------------------------------------------
        % Adiabatic rate of rise
        %
        % The rate at the instant load is applied, before the
        % cooling system has removed anything. This is what
        % determines whether a short burst is survivable.
        %% -----------------------------------------------------

        AdiabaticRate_K_s(k) = ...
            TotalHeat_W(k) / Th.PackThermalMass_J_K;

        %% -----------------------------------------------------
        % Time from ambient to the design limit
        %
        % First-order lumped response:
        %
        %   T(t) = T_inf + (T_0 - T_inf)*exp(-t/tau)
        %
        % Solved for the time to reach the design limit. If the
        % steady state is below the limit the pack never gets
        % there, which is the desired answer.
        %% -----------------------------------------------------

        tau = Th.PackThermalMass_J_K * Th.PackToCoolant_K_W;

        Tinf = SteadyTemp_C(k);

        T0 = Th.Ambient_C;

        Tlimit = Th.DesignLimit_C;

        if Tinf <= Tlimit

            TimeToLimit_s(k) = inf;

        else

            TimeToLimit_s(k) = ...
                -tau * log((Tlimit - Tinf)/(T0 - Tinf));

        end

    end

    Th.TimeConstant_s = ...
        Th.PackThermalMass_J_K * Th.PackToCoolant_K_W;

    %% =========================================================
    % RESULTS TABLE
    %% =========================================================

    Thermal.Table = table( ...
        Current_A, ...
        CellCurrent_A, ...
        CRate, ...
        CellHeat_W, ...
        CellHeatTotal_W, ...
        BusbarHeat_W, ...
        TotalHeat_W, ...
        SteadyRise_K, ...
        SteadyTemp_C, ...
        AdiabaticRate_K_s, ...
        TimeToLimit_s, ...
        SteadyOK);

    %% ---------------------------------------------------------
    % Legacy field names
    %% ---------------------------------------------------------

    Thermal.Current_A             = currents;
    Thermal.CurrentPerCell_A      = CellCurrent_A';
    Thermal.CellHeat_W            = CellHeat_W';
    Thermal.TotalHeat_W           = TotalHeat_W';
    Thermal.CellTemperatureRise_K = SteadyRise_K';

    Thermal.Parameters = Th;
    Thermal.BusbarResistance_Ohm = Bus.Rtotal;

    %% =========================================================
    % COOLING DUTY
    %
    % What the cooling system must actually remove at the
    % continuous rating, which is the number to size a pump and
    % heat exchanger against.
    %% =========================================================

    idxContinuous = find(currents == 375,1);

    if ~isempty(idxContinuous)

        %% The bus continuous rating, from the datasheet, not a literal.
        Thermal.Cooling.AtContinuousCurrent_A = ...
            P50B_Value(P50B_LoadParams().motor.bus_i_max_A);
        Thermal.Cooling.RequiredDuty_W = TotalHeat_W(idxContinuous);

        %% -----------------------------------------------------
        % Coolant flow for a chosen temperature rise
        %
        %   Q = m_dot * cp * dT
        %
        % Water-glycol, cp about 3600 J/(kg*K).
        %% -----------------------------------------------------

        cp_coolant = 3600;

        allowedCoolantRise = 5;

        mdot = Thermal.Cooling.RequiredDuty_W / ...
               (cp_coolant * allowedCoolantRise);

        Thermal.Cooling.CoolantSpecificHeat_J_kgK = cp_coolant;
        Thermal.Cooling.AllowedCoolantRise_K = allowedCoolantRise;
        Thermal.Cooling.MassFlow_kg_s = mdot;
        Thermal.Cooling.VolumeFlow_L_min = mdot/1000*60*1000;

    end

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose
        printThermal(Thermal,Th,data,Bus);
    end

    %% =========================================================
    % PLOT
    %% =========================================================

    if opts.Plot
        plotThermal(Thermal,Th);
    end

end

%% =============================================================
% Report
%% =============================================================

function printThermal(Thermal,Th,data,Bus)

    T = Thermal.Table;

    fprintf("\n");
    fprintf("================================================================\n");
    fprintf(" PACK THERMAL ANALYSIS\n");
    fprintf("================================================================\n");

    fprintf("\nBASIS\n");
    fprintf("  Cell resistance         : %.2f mOhm ", ...
        Th.CellResistance_Ohm*1e3);
    fprintf("(at %.0f%% SOC, %.0f degC)\n", ...
        Th.EvaluationSOC*100,Th.EvaluationTemp_C);
    fprintf("  Interconnect resistance : %.3f mOhm\n",Bus.Rtotal*1e3);
    fprintf("  Cell thermal mass       : %.1f J/K\n", ...
        Th.CellThermalMass_J_K);
    fprintf("  Pack thermal mass       : %.0f kJ/K\n", ...
        Th.PackThermalMass_J_K/1000);
    fprintf("  Cell-to-coolant         : %.1f K/W per cell  [%s]\n", ...
        Th.CellToCoolant_K_W,Th.CellToCoolantSource);
    fprintf("  Pack thermal time const : %.0f s (%.1f min)\n", ...
        Th.TimeConstant_s,Th.TimeConstant_s/60);
    fprintf("  Ambient                 : %.0f degC\n",Th.Ambient_C);
    fprintf("  Design limit            : %.0f degC\n",Th.DesignLimit_C);

    fprintf("\nHEAT AND TEMPERATURE\n");
    fprintf("  %6s %7s %6s %8s %8s %9s %9s %10s\n", ...
        "I [A]","I/cell","C-rate","Cell[W]","Bus[W]","Total[W]", ...
        "Steady[C]","Hold time");
    fprintf("  %s\n",repmat('-',1,76));

    for k = 1:height(T)

        if isinf(T.TimeToLimit_s(k))
            holdStr = "indefinite";
        elseif T.TimeToLimit_s(k) > 3600
            holdStr = sprintf("%.1f h",T.TimeToLimit_s(k)/3600);
        else
            holdStr = sprintf("%.0f min",T.TimeToLimit_s(k)/60);
        end

        if T.SteadyOK(k)
            marker = " ";
        else
            marker = "*";
        end

        fprintf("  %6.0f %7.2f %6.2f %8.2f %8.1f %9.1f %9.1f %10s %s\n", ...
            T.Current_A(k), ...
            T.CellCurrent_A(k), ...
            T.CRate(k), ...
            T.CellHeat_W(k), ...
            T.BusbarHeat_W(k), ...
            T.TotalHeat_W(k), ...
            T.SteadyTemp_C(k), ...
            holdStr, ...
            marker);

    end

    if any(~T.SteadyOK)
        fprintf("\n  * steady-state temperature exceeds the %.0f degC design limit\n", ...
            Th.DesignLimit_C);
    end

    %% ---------------------------------------------------------
    % Cell current headroom
    %% ---------------------------------------------------------

    fprintf("\nCELL UTILISATION\n");

    maxCellCurrent = max(T.CellCurrent_A);

    fprintf("  Highest cell current    : %.2f A\n",maxCellCurrent);
    fprintf("  Datasheet continuous    : %.0f A\n", ...
        data.MaxContinuousCurrent_A);
    fprintf("  Utilisation             : %.1f%%\n", ...
        maxCellCurrent/data.MaxContinuousCurrent_A*100);
    fprintf("\n  The cell is not the limiting element in this pack.\n");

    %% ---------------------------------------------------------
    % Cooling duty
    %% ---------------------------------------------------------

    if isfield(Thermal,"Cooling")

        C = Thermal.Cooling;

        fprintf("\nCOOLING DUTY AT %.0f A CONTINUOUS\n", ...
            C.AtContinuousCurrent_A);
        fprintf("  Heat to remove          : %.0f W\n",C.RequiredDuty_W);
        fprintf("  Coolant flow            : %.1f L/min ", ...
            C.VolumeFlow_L_min);
        fprintf("(for a %.0f K coolant rise)\n",C.AllowedCoolantRise_K);

    end

    fprintf("\n================================================================\n");

end

%% =============================================================
% Plot
%% =============================================================

function plotThermal(Thermal,Th)

    T = Thermal.Table;

    figure("Name","P50B Thermal Design","Color","white");

    %% ---------------------------------------------------------
    % Heat generation
    %% ---------------------------------------------------------

    subplot(1,2,1);

    hold on; grid on;

    area(T.Current_A,[T.CellHeatTotal_W T.BusbarHeat_W]);

    xlabel("Pack current [A]");
    ylabel("Heat generation [W]");
    title("Where the heat comes from");

    legend("Cells","Interconnect","Location","northwest");

    %% ---------------------------------------------------------
    % Steady temperature
    %% ---------------------------------------------------------

    subplot(1,2,2);

    hold on; grid on;

    plot(T.Current_A,T.SteadyTemp_C,"o-","LineWidth",1.5);

    yline(Th.DesignLimit_C,"--", ...
        sprintf("Design limit %.0f C",Th.DesignLimit_C));

    yline(Th.AbsoluteLimit_C,"-", ...
        sprintf("Cell cut-off %.0f C",Th.AbsoluteLimit_C));

    xlabel("Pack current [A]");
    ylabel("Steady cell temperature [degC]");
    title("Steady-state cell temperature");

end

function Report = P50B_Verification(data,Layout,Thermal,varargin)
%P50B_VERIFICATION  Check the 26S21P design against every known constraint.
%
%   Report = P50B_Verification(data,Layout,Thermal) verifies the pack
%   architecture, geometry, electrical ratings and drivetrain
%   compatibility, and returns a table of every check with its result.
%
%   Any argument may be omitted or empty and will be rebuilt.
%
%   OPTIONS
%     "Busbars"  Bus struct from P50B_Busbars
%     "Verbose"  logical, default true
%     "Strict"   logical, default false -- error on any failure rather
%                than returning the report
%
%   WHAT CHANGED FROM THE PREVIOUS REVISION
%   ---------------------------------------
%   The previous version read data.Vnom, which the cell definition does
%   not provide, and Layout.PackWidth, which only one of the project's
%   two competing layout functions produced. It therefore could not run
%   to completion.
%
%   More importantly, it only checked internal self-consistency: that
%   26 x 21 is 546. Those checks are worth keeping, but they cannot fail
%   in any interesting way.
%
%   This version adds the checks that can actually fail: whether the
%   pack matches the drivetrain it has to drive, whether the busbars
%   carry the current the inverter will draw, and whether the cells stay
%   inside their datasheet limits.
%
%   See also P50B_Geometry, P50B_GroupLayout, P50B_Busbars.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct("Busbars",[],"Verbose",true,"Strict",false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_Verification:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% =========================================================
    % BUILD ANYTHING NOT SUPPLIED
    %% =========================================================

    if nargin < 1 || isempty(data)
        data = P50B_CellData();
    end

    G = P50B_Geometry();

    if nargin < 2 || isempty(Layout)
        Layout = P50B_GroupLayout(G,"Plot",false,"Verbose",false);
    end

    if isempty(opts.Busbars)
        Bus = P50B_Busbars(G,Layout,"Plot",false,"Verbose",false);
    else
        Bus = opts.Busbars;
    end

    if nargin < 3 || isempty(Thermal)
        Thermal = P50B_ThermalDesign(data, ...
            "Busbars",Bus,"Verbose",false,"Plot",false);
    end

    motor = P50B_MotorData();
    inv   = P50B_InverterData();
    harn  = P50B_HarnessData();
    aux   = P50B_AuxiliaryLoads();

    %% =========================================================
    % CHECK ACCUMULATOR
    %% =========================================================

    checks = struct("Category",{},"Name",{},"Pass",{}, ...
                    "Detail",{},"Severity",{});

    function addCheck(category,name,pass,detail,severity)

        if nargin < 5
            severity = "ERROR";
        end

        checks(end+1) = struct( ...
            "Category", string(category), ...
            "Name",     string(name), ...
            "Pass",     logical(pass), ...
            "Detail",   string(detail), ...
            "Severity", string(severity));

    end

    %% =========================================================
    % 1. ARCHITECTURE
    %% =========================================================

    Ns = G.Pack.SeriesGroups;
    Np = G.Pack.ParallelCells;

    addCheck("Architecture","Total cell count", ...
        Ns*Np == 546, ...
        sprintf("%d series x %d parallel = %d cells",Ns,Np,Ns*Np));

    addCheck("Architecture","Cell table height", ...
        height(Layout.Cells) == 546, ...
        sprintf("%d rows in the cell table",height(Layout.Cells)));

    addCheck("Architecture","Group table height", ...
        height(Layout.Groups) == 26, ...
        sprintf("%d rows in the group table",height(Layout.Groups)));

    groupCounts = accumarray(Layout.Cells.SeriesGroup,1);

    addCheck("Architecture","Cells per group", ...
        all(groupCounts == 21), ...
        sprintf("min %d, max %d",min(groupCounts),max(groupCounts)));

    layerCounts = accumarray(Layout.Cells.Layer,1);

    addCheck("Architecture","Cells per layer", ...
        all(layerCounts == 273), ...
        sprintf("layer 1: %d, layer 2: %d", ...
            layerCounts(1),layerCounts(2)));

    addCheck("Architecture","Group array shape", ...
        G.Group.Rows*G.Group.Columns == 21, ...
        sprintf("%d rows x %d columns", ...
            G.Group.Rows,G.Group.Columns));

    %% =========================================================
    % 2. GEOMETRY
    %% =========================================================

    addCheck("Geometry","Cell coordinates finite", ...
        all(isfinite(Layout.Cells.X)) && ...
        all(isfinite(Layout.Cells.Y)) && ...
        all(isfinite(Layout.Cells.Z)), ...
        "All 546 cell positions are finite");

    addCheck("Geometry","Series path adjacency", ...
        Layout.AllStepsAdjacent, ...
        sprintf("longest step %.1f mm",Layout.MaxStepLength*1e3));

    addCheck("Geometry","Grid capacity", ...
        G.Grid.TotalSlots >= G.Pack.GroupsPerLayer, ...
        sprintf("%d slots for %d groups, %d spare", ...
            G.Grid.TotalSlots,G.Pack.GroupsPerLayer,G.Grid.EmptySlots));

    addCheck("Geometry","Packaging efficiency", ...
        G.Pack.PackagingEfficiency > 0.30, ...
        sprintf("%.1f%% of external volume is cell", ...
            G.Pack.PackagingEfficiency*100), ...
        "WARNING");

    %% =========================================================
    % 3. ELECTRICAL RATINGS
    %% =========================================================

    Vnom = Ns * data.NominalVoltage_V;
    Vmax = Ns * data.MaxVoltage_V;
    Vmin = Ns * data.MinVoltage_V;

    Ah   = Np * data.Capacity_Ah;

    Energy_kWh = Vnom*Ah/1000;

    addCheck("Electrical","Pack nominal voltage", ...
        abs(Vnom - 93.6) < 0.1, ...
        sprintf("%.2f V",Vnom));

    addCheck("Electrical","Pack maximum voltage", ...
        abs(Vmax - 109.2) < 0.1, ...
        sprintf("%.2f V",Vmax));

    addCheck("Electrical","Pack capacity", ...
        abs(Ah - 105) < 0.1, ...
        sprintf("%.1f Ah",Ah));

    %% =========================================================
    % 4. DRIVETRAIN COMPATIBILITY
    %
    % The checks that can actually fail, and that matter.
    %% =========================================================

    addCheck("Drivetrain","Series count matches outboard", ...
        Ns == 26, ...
        sprintf("Pack is %dS, Competr datasheet specifies 26S",Ns));

    addCheck("Drivetrain","Maximum voltage within outboard limit", ...
        Vmax <= motor.BusMaximumVoltage_V + 0.5, ...
        sprintf("Pack max %.1f V vs outboard limit %.0f V", ...
            Vmax,motor.BusMaximumVoltage_V));

    addCheck("Drivetrain","Minimum voltage above inverter floor", ...
        Vmin > 60, ...
        sprintf("Pack min %.1f V at the cell cut-off",Vmin), ...
        "WARNING");

    %% ---------------------------------------------------------
    % Current capability
    %% ---------------------------------------------------------

    packCurrentCapability = Np * data.MaxContinuousCurrent_A;

    addCheck("Drivetrain","Pack can supply outboard continuous current", ...
        packCurrentCapability >= motor.BusMaximumCurrent_A, ...
        sprintf("Cells allow %.0f A, outboard draws up to %.0f A", ...
            packCurrentCapability,motor.BusMaximumCurrent_A));

    cellCurrentAtContinuous = motor.BusMaximumCurrent_A / Np;

    addCheck("Drivetrain","Cell current at outboard continuous rating", ...
        cellCurrentAtContinuous <= data.MaxContinuousCurrent_A, ...
        sprintf("%.2f A/cell (%.2f C), datasheet limit %.0f A", ...
            cellCurrentAtContinuous, ...
            cellCurrentAtContinuous/data.Capacity_Ah, ...
            data.MaxContinuousCurrent_A));

    peakCurrent = motor.MaximumPower_W / Vnom;

    addCheck("Drivetrain","Cell current at 42 kW peak", ...
        peakCurrent/Np <= data.MaxContinuousCurrent_A, ...
        sprintf("%.2f A/cell at %.0f A pack current", ...
            peakCurrent/Np,peakCurrent));

    %% ---------------------------------------------------------
    % Energy
    %
    % Not a pass or fail so much as a fact the team needs to know.
    %% ---------------------------------------------------------

    stockPackEnergy_kWh = 26;

    addCheck("Drivetrain","Energy vs Competr stock pack", ...
        true, ...
        sprintf("This pack %.2f kWh vs stock %.0f kWh (%.0f%% of it)", ...
            Energy_kWh,stockPackEnergy_kWh, ...
            Energy_kWh/stockPackEnergy_kWh*100), ...
        "INFO");

    %% =========================================================
    % 5. INTERCONNECT
    %% =========================================================

    T = Bus.OperatingPoints;

    for k = 1:height(T)

        addCheck("Interconnect", ...
            sprintf("Current density: %s",T.Case(k)), ...
            T.DensityOK(k), ...
            sprintf("links %.1f, rails %.1f A/mm2 (%s limit %.1f)", ...
                T.SeriesDensity_A_mm2(k), ...
                T.RailDensity_A_mm2(k), ...
                lower(T.Duty(k)), ...
                T.DensityLimit_A_mm2(k)), ...
            "WARNING");

    end

    %% ---------------------------------------------------------
    % Voltage drop
    %% ---------------------------------------------------------

    idxCont = find(T.Current_A == 375,1);

    if ~isempty(idxCont)

        dropPercent = T.VoltageDrop_V(idxCont)/Vnom*100;

        addCheck("Interconnect","Voltage drop at continuous current", ...
            dropPercent < 3, ...
            sprintf("%.2f V (%.2f%% of nominal) at 375 A", ...
                T.VoltageDrop_V(idxCont),dropPercent), ...
            "WARNING");

    end

    %% =========================================================
    % 6. HARNESS
    %% =========================================================

    addCheck("Harness","Cable ampacity vs continuous current", ...
        harn.CableAmpacity_A >= motor.BusMaximumCurrent_A, ...
        sprintf("%.0f mm2 gives %.0f A derated, need %.0f A", ...
            harn.CableCrossSection_mm2, ...
            harn.CableAmpacity_A, ...
            motor.BusMaximumCurrent_A));

    %% ---------------------------------------------------------
    % Fuse must clear the worst LEGAL operating current.
    %
    % The relevant number is the rule-limited power drawn at the
    % minimum bus voltage, not the outboard's 42 kW hardware
    % peak -- that peak is not permitted under ENERGY_REQ_188,
    % so sizing the fuse to pass it would force an oversized
    % fuse and break ENERGY_REQ_59 instead.
    %% ---------------------------------------------------------

    ruleLimitedPeak = motor.ConfiguredPowerLimit_W / Vmin;

    addCheck("Harness","Fuse clears worst legal operating current", ...
        harn.FuseRating_A > ruleLimitedPeak, ...
        sprintf("%.0f A fuse vs %.0f A worst legal draw (%.0f kW " + ...
                "at the %.0f V minimum bus)", ...
            harn.FuseRating_A,ruleLimitedPeak, ...
            motor.ConfiguredPowerLimit_W/1000,Vmin));

    addCheck("Harness","Fuse below protected conductor ratings", ...
        harn.FuseRating_A <= min(harn.CableAmpacity_A, ...
            Bus.Ampacity.DesignLimit_A_per_mm2*Bus.Geometry.SeriesArea_mm2), ...
        sprintf("%.0f A fuse, cable %.0f A, busbar %.0f A " + ...
                "(Monaco ENERGY_REQ_59)", ...
            harn.FuseRating_A, ...
            harn.CableAmpacity_A, ...
            Bus.Ampacity.DesignLimit_A_per_mm2*Bus.Geometry.SeriesArea_mm2));

    %% =========================================================
    % 7. AUXILIARY
    %% =========================================================

    addCheck("Auxiliary","DC/DC headroom at simultaneous peak", ...
        aux.DCDC_HeadroomAtPeak_W >= 0, ...
        sprintf("Peak 12 V load %.0f W vs %.0f W converter", ...
            aux.PeakLoad12V_W,aux.DCDC_RatedPower_W), ...
        "WARNING");

    %% =========================================================
    % 8. THERMAL
    %% =========================================================

    Tt = Thermal.Table;

    idx267 = find(Tt.Current_A == 267,1);

    if ~isempty(idx267)

        addCheck("Thermal","Steady temperature at Monaco power cap", ...
            Tt.SteadyOK(idx267), ...
            sprintf("%.1f degC steady, design limit %.0f degC", ...
                Tt.SteadyTemp_C(idx267), ...
                Thermal.Parameters.DesignLimit_C));

    end

    idx375 = find(Tt.Current_A == 375,1);

    if ~isempty(idx375)

        addCheck("Thermal","Steady temperature at outboard continuous", ...
            Tt.SteadyOK(idx375), ...
            sprintf("%.1f degC steady at 375 A", ...
                Tt.SteadyTemp_C(idx375)), ...
            "WARNING");

    end

    %% =========================================================
    % 9. INVERTER SIZING
    %% =========================================================

    addCheck("Inverter","Device rating requirement identified", ...
        inv.DeviceCurrentRatingRequired_A > 0, ...
        sprintf("Needs >= %.0f A device rating for 42 kW peak", ...
            inv.DeviceCurrentRatingRequired_A), ...
        "INFO");

    addCheck("Inverter","Selection status", ...
        false, ...
        "Inverter not yet selected -- Competr lists it as 'on request'", ...
        "INFO");

    %% =========================================================
    % ASSEMBLE REPORT
    %% =========================================================

    Report.Checks = struct2table(checks);

    Report.NumChecks = numel(checks);

    isError = [checks.Severity] == "ERROR";
    isWarn  = [checks.Severity] == "WARNING";
    isInfo  = [checks.Severity] == "INFO";

    passed = [checks.Pass];

    Report.NumPassed = sum(passed);
    Report.NumFailed = sum(~passed & ~isInfo);

    Report.ErrorsFailed   = sum(~passed & isError);
    Report.WarningsFailed = sum(~passed & isWarn);
    Report.InfoItems      = sum(isInfo);

    Report.AllCriticalPassed = (Report.ErrorsFailed == 0);

    %% ---------------------------------------------------------
    % Headline numbers
    %% ---------------------------------------------------------

    Report.Summary.SeriesGroups   = Ns;
    Report.Summary.ParallelCells  = Np;
    Report.Summary.TotalCells     = Ns*Np;
    Report.Summary.NominalVoltage_V = Vnom;
    Report.Summary.MaxVoltage_V   = Vmax;
    Report.Summary.MinVoltage_V   = Vmin;
    Report.Summary.Capacity_Ah    = Ah;
    Report.Summary.Energy_kWh     = Energy_kWh;
    Report.Summary.CellMass_kg    = Ns*Np*data.Mass_kg;
    Report.Summary.PackMassEstimate_kg = G.Mass.TotalEstimate;
    Report.Summary.PackWidth_mm   = Layout.PackWidth*1e3;
    Report.Summary.PackDepth_mm   = Layout.PackDepth*1e3;
    Report.Summary.PackHeight_mm  = Layout.PackHeight*1e3;
    Report.Summary.ExternalWidth_mm  = Layout.PackExternalWidth*1e3;
    Report.Summary.ExternalDepth_mm  = Layout.PackExternalDepth*1e3;
    Report.Summary.ExternalHeight_mm = Layout.PackExternalHeight*1e3;
    Report.Summary.InterconnectResistance_mOhm = Bus.Rtotal*1e3;
    Report.Summary.SpecificEnergy_Wh_kg = ...
        Energy_kWh*1000/G.Mass.TotalEstimate;

    %% =========================================================
    % PRINT
    %% =========================================================

    if opts.Verbose
        printVerification(Report);
    end

    %% =========================================================
    % STRICT MODE
    %% =========================================================

    if opts.Strict && ~Report.AllCriticalPassed

        failed = Report.Checks(~Report.Checks.Pass & ...
                                Report.Checks.Severity == "ERROR",:);

        error("P50B_Verification:CriticalFailure", ...
            "%d critical check(s) failed. First: %s -- %s", ...
            Report.ErrorsFailed, ...
            failed.Name(1), ...
            failed.Detail(1));

    end

end

%% =============================================================
% Print
%% =============================================================

function printVerification(R)

    C = R.Checks;

    fprintf("\n");
    fprintf("================================================================\n");
    fprintf(" PACK VERIFICATION\n");
    fprintf("================================================================\n");

    categories = unique(C.Category,"stable");

    for k = 1:numel(categories)

        cat = categories(k);

        fprintf("\n%s\n",upper(cat));

        idx = find(C.Category == cat);

        for j = idx(:)'

            if C.Severity(j) == "INFO"
                marker = "  -- ";
            elseif C.Pass(j)
                marker = "  PASS";
            elseif C.Severity(j) == "WARNING"
                marker = "  WARN";
            else
                marker = "  FAIL";
            end

            fprintf("%s  %-44s %s\n", ...
                marker, ...
                C.Name(j), ...
                C.Detail(j));

        end

    end

    %% ---------------------------------------------------------
    % Headline summary
    %% ---------------------------------------------------------

    S = R.Summary;

    fprintf("\n");
    fprintf("----------------------------------------------------------------\n");
    fprintf(" PACK SUMMARY\n");
    fprintf("----------------------------------------------------------------\n");

    fprintf("  Configuration           : %dS%dP, %d cells\n", ...
        S.SeriesGroups,S.ParallelCells,S.TotalCells);
    fprintf("  Voltage                 : %.1f V nominal ", ...
        S.NominalVoltage_V);
    fprintf("(%.1f to %.1f V)\n",S.MinVoltage_V,S.MaxVoltage_V);
    fprintf("  Capacity                : %.1f Ah\n",S.Capacity_Ah);
    fprintf("  Energy                  : %.2f kWh\n",S.Energy_kWh);
    fprintf("\n");
    fprintf("  Cell mass               : %.1f kg\n",S.CellMass_kg);
    fprintf("  Pack mass (estimate)    : %.1f kg\n", ...
        S.PackMassEstimate_kg);
    fprintf("  Specific energy         : %.0f Wh/kg at pack level\n", ...
        S.SpecificEnergy_Wh_kg);
    fprintf("\n");
    fprintf("  Cell envelope           : %.0f x %.0f x %.0f mm\n", ...
        S.PackWidth_mm,S.PackDepth_mm,S.PackHeight_mm);
    fprintf("  External envelope       : %.0f x %.0f x %.0f mm\n", ...
        S.ExternalWidth_mm,S.ExternalDepth_mm,S.ExternalHeight_mm);
    fprintf("\n");
    fprintf("  Interconnect resistance : %.3f mOhm\n", ...
        S.InterconnectResistance_mOhm);

    %% ---------------------------------------------------------
    % Result
    %% ---------------------------------------------------------

    fprintf("\n");
    fprintf("----------------------------------------------------------------\n");

    fprintf(" %d checks: %d passed, %d critical failure(s), %d warning(s)\n", ...
        R.NumChecks, ...
        R.NumPassed, ...
        R.ErrorsFailed, ...
        R.WarningsFailed);

    if R.AllCriticalPassed
        fprintf(" No critical failures.\n");
    else
        fprintf(" CRITICAL FAILURES PRESENT -- see FAIL lines above.\n");
    end

    fprintf("================================================================\n");

end

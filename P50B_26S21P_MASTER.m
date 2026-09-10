%% ==============================================================
% P50B_26S21P_MASTER.m
%
% Master build and analysis script for the Monaco Energy Boat
% Challenge battery pack and electrical drivetrain.
%
% ARCHITECTURE
%
%   Cell        Molicel INR-21700-P50B
%   Group       21 cells in parallel, 3 rows x 7 columns
%   Module      13 groups in series
%   Pack        2 modules in series -> 26S21P, 546 cells
%
%   Drivetrain  Competr counter-rotating electric outboard
%               Axial-flux PMSM, 26.9 kW nominal / 42 kW peak
%
% WHAT THIS SCRIPT DOES
%
%   1  Environment and path
%   2  Cell definition
%   3  Simscape Battery pack object
%   4  Mechanical layout
%   5  Interconnect (busbars, welds, series links)
%   6  Thermal analysis
%   7  Drivetrain operating points
%   8  Mission simulation
%   9  Verification
%  10  Parameter provenance audit
%  11  Save everything
%
% REQUIREMENTS
%   MATLAB, Simulink, Simscape, Simscape Battery
%
% To run only the fast analysis without building Simscape
% libraries, set BUILD_SIMSCAPE to false below.
%% ==============================================================

clear;
clc;
close all;

%% ==============================================================
% CONFIGURATION
%% ==============================================================

BUILD_SIMSCAPE = true;      % build the generated Simscape library
RUN_MISSION    = true;      % run the mission simulation
SHOW_PLOTS     = true;      % draw figures
SAVE_RESULTS   = true;      % write to output/

MISSION_PROFILE = "endurance";

%% ==============================================================
% 1. ENVIRONMENT
%% ==============================================================

projectRoot = fileparts(mfilename("fullpath"));

cd(projectRoot);

addpath(genpath(projectRoot));

fprintf("\n");
fprintf("################################################################\n");
fprintf("#                                                              #\n");
fprintf("#   P50B 26S21P  -  MONACO ENERGY BOAT CHALLENGE               #\n");
fprintf("#   Battery pack and electrical drivetrain model               #\n");
fprintf("#                                                              #\n");
fprintf("################################################################\n");

fprintf("\nProject root : %s\n",projectRoot);
fprintf("MATLAB       : %s\n",version("-release"));
fprintf("Run started  : %s\n",string(datetime("now")));

%% ==============================================================
% 2. CELL
%% ==============================================================

fprintf("\n[1/10] Cell definition\n");

data = P50B_CellData();

fprintf("  %s %s\n",data.Manufacturer,data.Model);
fprintf("  %.1f Ah, %.1f V nominal, %.0f A continuous\n", ...
    data.Capacity_Ah, ...
    data.NominalVoltage_V, ...
    data.MaxContinuousCurrent_A);
fprintf("  DCIR %.1f mOhm at 50%% SOC, 25 degC\n", ...
    data.DCIR_Ohm*1e3);
fprintf("  OCV curve source: %s\n",data.OCV.Source);
fprintf("  DCIR surface source: %s\n",data.DCIR.Source);

%% ==============================================================
% 3. MECHANICAL LAYOUT
%
% Built before the Simscape object because the geometry module
% is the single source of truth for pack dimensions, and the
% Simscape build should use the same clearances.
%% ==============================================================

fprintf("\n[2/10] Mechanical layout\n");

G = P50B_Geometry();

Layout = P50B_GroupLayout(G, ...
    "Plot",    SHOW_PLOTS, ...
    "Verbose", true);

if SHOW_PLOTS
    P50B_PlotCells(G,Layout.Cells);
end

%% ==============================================================
% 4. INTERCONNECT
%% ==============================================================

fprintf("\n[3/10] Interconnect analysis\n");

Bus = P50B_Busbars(G,Layout, ...
    "Plot",    SHOW_PLOTS, ...
    "Verbose", true);

%% ==============================================================
% 5. SIMSCAPE BATTERY OBJECT
%% ==============================================================

fprintf("\n[4/10] Simscape Battery pack object\n");

P21 = P50B_21P(data);

M13 = P50B_13S21P(P21);

pack = P50B_26S21P(M13);

fprintf("  Pack object built: %s\n",class(pack));

if SHOW_PLOTS

    figure("Color","white","Name","P50B Battery Builder");

    batteryChart(pack);

    title("Molicel P50B 26S21P Battery Pack");

end

%% ==============================================================
% 6. BUILD SIMSCAPE LIBRARY
%% ==============================================================

if BUILD_SIMSCAPE

    fprintf("\n[5/10] Building Simscape library\n");

    outputDir = fullfile(projectRoot,"output");

    if ~isfolder(outputDir)
        mkdir(outputDir);
    end

    %% ----------------------------------------------------------
    % Clean previous build artifacts
    %
    % buildBattery refuses to overwrite an existing library, so a
    % second run fails unless the old files are removed first.
    %% ----------------------------------------------------------

    libName = "P50B_26S21P";

    artifacts = [ ...
        fullfile(outputDir,libName + ".slx")
        fullfile(outputDir,libName + "_lib.slx")];

    for a = 1:numel(artifacts)

        [~,modelName,~] = fileparts(artifacts(a));

        if bdIsLoaded(modelName)
            close_system(modelName,0);
        end

        if isfile(artifacts(a))
            delete(artifacts(a));
        end

    end

    packageDir = fullfile(outputDir,"+" + libName);

    if isfolder(packageDir)
        rmdir(packageDir,"s");
    end

    try

        buildBattery( ...
            pack, ...
            LibraryName=libName, ...
            Directory=outputDir, ...
            MaskParameters="VariableNamesByType", ...
            MaskInitialTargets="VariableNamesByInstance", ...
            Verbose="off");

        fprintf("  Library written to output/\n");

    catch ME

        fprintf("  Library build FAILED: %s\n",ME.message);
        fprintf("  Continuing with the analytical model.\n");

    end

else

    fprintf("\n[5/10] Simscape library build skipped\n");

end

%% ==============================================================
% 7. THERMAL
%% ==============================================================

fprintf("\n[6/10] Thermal analysis\n");

Thermal = P50B_ThermalDesign(data, ...
    "Busbars", Bus, ...
    "Plot",    SHOW_PLOTS, ...
    "Verbose", true);

%% ==============================================================
% 8. DRIVETRAIN OPERATING POINTS
%% ==============================================================

fprintf("\n[7/10] Drivetrain operating points\n");

motor    = P50B_MotorData();
inverter = P50B_InverterData();
harness  = P50B_HarnessData();
auxLoads = P50B_AuxiliaryLoads();

fprintf("\n  Outboard : %s, %s\n",motor.Manufacturer,motor.MotorType);
fprintf("  Rated    : %.1f kW nominal, %.0f kW peak, %.0f Nm\n", ...
    motor.NominalPower_W/1000, ...
    motor.MaximumPower_W/1000, ...
    motor.MaximumTorque_Nm);
fprintf("  Bus      : %.0f V nominal, %.0f V max, %.0f A continuous\n", ...
    motor.BusNominalVoltage_V, ...
    motor.BusMaximumVoltage_V, ...
    motor.BusMaximumCurrent_A);

%% --------------------------------------------------------------
% Sweep shaft power across the usable range
%% --------------------------------------------------------------

sweepPower = [5e3 10e3 15e3 20e3 23e3 25e3 30e3];

fprintf("\n  Motor electrical input is hard-capped at %.0f kW\n", ...
    motor.ConfiguredPowerLimit_W/1000);
fprintf("  (Monaco ENERGY_REQ_188). Demands above it are limited,\n");
fprintf("  not delivered.\n");

fprintf("\n  %9s %9s %9s %8s %7s %8s %8s %7s\n", ...
    "Asked kW","Shaft kW","Motor kW","Pack A","Cell C","Pack V", ...
    "Chain %","Capped");
fprintf("  %s\n",repmat('-',1,78));

OpPoints = cell(numel(sweepPower),1);

for k = 1:numel(sweepPower)

    Pshaft = sweepPower(k);

    nMotor = motor.BaseSpeed_rpm * ...
        (Pshaft/motor.NominalPower_W)^(1/3);

    nMotor = max(min(nMotor,motor.MaximumSpeed_rpm),200);

    op = P50B_DrivetrainModel( ...
        Pshaft,nMotor,0.60,30, ...
        "Busbars",   Bus, ...
        "Motor",     motor, ...
        "Inverter",  inverter, ...
        "Harness",   harness, ...
        "Auxiliary", auxLoads, ...
        "Cell",      data);

    OpPoints{k} = op;

    if op.PowerLimit.Active
        flag = "YES";
    else
        flag = "-";
    end

    fprintf("  %9.1f %9.1f %9.1f %8.1f %7.2f %8.1f %8.1f %7s\n", ...
        Pshaft/1000, ...
        op.PowerLimit.DeliveredShaft_W/1000, ...
        op.Motor.InputPower_W/1000, ...
        op.Pack.Current_A, ...
        op.Pack.CellCRate, ...
        op.Pack.TerminalVoltage_V, ...
        op.Chain.OverallEfficiency*100, ...
        flag);

end

%% --------------------------------------------------------------
% Loss breakdown at the competition power cap
%% --------------------------------------------------------------

idxCap = find(sweepPower == 23e3,1);

if ~isempty(idxCap)

    fprintf("\n  LOSS BREAKDOWN JUST UNDER THE 25 kW CAP\n\n");

    B = OpPoints{idxCap}.Chain.LossBreakdown;

    for k = 1:height(B)

        fprintf("    %-28s %8.1f W  (%4.1f%%)\n", ...
            B.Stage(k), ...
            B.Loss_W(k), ...
            B.ShareOfTotalLoss(k)*100);

    end

    fprintf("\n    %-28s %8.1f W\n", ...
        "TOTAL LOSS", ...
        OpPoints{idxCap}.Chain.TotalLoss_W);

    fprintf("    %-28s %8.1f %%\n", ...
        "OVERALL CHAIN EFFICIENCY", ...
        OpPoints{idxCap}.Chain.OverallEfficiency*100);

end

%% ==============================================================
% 9. MISSION SIMULATION
%% ==============================================================

if RUN_MISSION

    fprintf("\n[8/10] Mission simulation\n");

    Profile = P50B_MissionProfile(MISSION_PROFILE);

    Mission = P50B_RunMission(Profile, ...
        "InitialSOC", 0.95, ...
        "Plot",       SHOW_PLOTS, ...
        "Verbose",    true);

else

    fprintf("\n[8/10] Mission simulation skipped\n");

    Mission = [];

end

%% ==============================================================
% 10. VERIFICATION
%% ==============================================================

fprintf("\n[9/10] Verification\n");

Report = P50B_Verification(data,Layout,Thermal, ...
    "Busbars", Bus, ...
    "Verbose", true);

%% ==============================================================
% 11. MONACO ENERGY CLASS COMPLIANCE
%% ==============================================================

fprintf("\n[10/11] Monaco Energy Class compliance\n");

Compliance = P50B_MonacoCompliance( ...
    "Cell",     data, ...
    "Motor",    motor, ...
    "Harness",  harness, ...
    "Busbars",  Bus, ...
    "Geometry", G, ...
    "Thermal",  Thermal, ...
    "Verbose",  true);

%% ==============================================================
% 12. PROVENANCE AUDIT
%% ==============================================================

fprintf("\n[11/11] Parameter provenance audit\n");

Provenance = P50B_ProvenanceReport();

%% ==============================================================
% SAVE
%% ==============================================================

if SAVE_RESULTS

    outputDir = fullfile(projectRoot,"output");

    if ~isfolder(outputDir)
        mkdir(outputDir);
    end

    save(fullfile(outputDir,"P50B_26S21P_Model.mat"), ...
        "data","G","Layout","Bus","Thermal","pack", ...
        "motor","inverter","harness","auxLoads", ...
        "Report","Provenance","OpPoints","Mission","Compliance");

    writetable(Compliance.Checks, ...
        fullfile(outputDir,"P50B_MonacoCompliance.csv"));

    writetable(Layout.Cells, ...
        fullfile(outputDir,"P50B_CellCoordinates.csv"));

    writetable(Layout.Groups, ...
        fullfile(outputDir,"P50B_GroupCoordinates.csv"));

    writetable(Bus.SeriesLinks, ...
        fullfile(outputDir,"P50B_BusbarLinks.csv"));

    writetable(Bus.OperatingPoints, ...
        fullfile(outputDir,"P50B_BusbarOperatingPoints.csv"));

    writetable(Thermal.Table, ...
        fullfile(outputDir,"P50B_ThermalTable.csv"));

    writetable(Report.Checks, ...
        fullfile(outputDir,"P50B_VerificationChecks.csv"));

    writetable(Provenance, ...
        fullfile(outputDir,"P50B_ParameterProvenance.csv"));

    fprintf("\nResults written to output/\n");

end

%% ==============================================================
% CLOSING SUMMARY
%% ==============================================================

fprintf("\n");
fprintf("################################################################\n");
fprintf("#  RUN COMPLETE\n");
fprintf("################################################################\n");

fprintf("\n  Pack        : %dS%dP, %d cells, %.2f kWh\n", ...
    Report.Summary.SeriesGroups, ...
    Report.Summary.ParallelCells, ...
    Report.Summary.TotalCells, ...
    Report.Summary.Energy_kWh);

fprintf("  Voltage     : %.1f V nominal (%.1f to %.1f V)\n", ...
    Report.Summary.NominalVoltage_V, ...
    Report.Summary.MinVoltage_V, ...
    Report.Summary.MaxVoltage_V);

fprintf("  Interconnect: %.3f mOhm\n", ...
    Report.Summary.InterconnectResistance_mOhm);

fprintf("  Verification: %d passed, %d critical failure(s)\n", ...
    Report.NumPassed, ...
    Report.ErrorsFailed);

fprintf("  Monaco rules: %d violation(s), %d item(s) to action\n", ...
    Compliance.NumFail, ...
    Compliance.NumAction);

fprintf("  Stored energy: %.0f Wh of 10000 Wh (%.2f%% margin)\n", ...
    Compliance.Energy.StoredEnergy_Wh, ...
    Compliance.Energy.MarginPercent);

if ~isempty(Mission)

    fprintf("  Mission     : %.1f min, %.1f%% SOC used, %.1f%% efficient\n", ...
        Mission.Summary.Duration_s/60, ...
        Mission.Summary.SOCUsed*100, ...
        Mission.Summary.MeanEfficiency*100);

end

nPlaceholder = sum(Provenance.Source == "PLACEHOLDER");
nAssumption  = sum(Provenance.Source == "ASSUMPTION");

fprintf("\n  Parameters  : %d total, %d assumptions, %d placeholders\n", ...
    height(Provenance),nAssumption,nPlaceholder);

if nAssumption > 0
    fprintf("\n  See docs/DATA_PROVENANCE.md for what to measure next.\n");
end

fprintf("\n");

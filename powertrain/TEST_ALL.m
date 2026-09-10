%% ============================================================
% TEST_ALL.m
%
% Bottom-up regression test for the P50B 26S21P project.
%
% Every stage is tested in dependency order, so the first
% failure points at the actual broken component rather than at
% something downstream of it.
%
% This script does not hide errors. On failure it prints the
% full MATLAB error report and stops.
%
% Run TEST_ELECTRICAL separately for the Simscape simulation
% test; this file covers the analytical model, which runs in
% seconds and needs no solver.
%% ============================================================

clear;
clc;
close all;

testStart = tic;

fprintf("\n");
fprintf("============================================================\n");
fprintf("       P50B 26S21P PROJECT TEST\n");
fprintf("============================================================\n");
fprintf("MATLAB release  : %s\n",version("-release"));
fprintf("Current folder  : %s\n",pwd);
fprintf("============================================================\n");

nStages = 14;

%% ============================================================
% 0. PROJECT ROOT AND PATH
%% ============================================================

fprintf("\n[ 0/%d] Project root and path .................. ",nStages);

projectRoot = fileparts(mfilename("fullpath"));

cd(projectRoot);

addpath(genpath(projectRoot));

if ~isfolder(projectRoot)
    error("Project root does not exist.");
end

fprintf("PASS\n");

%% ============================================================
% 1. REQUIRED TOOLBOX FUNCTIONS
%% ============================================================

fprintf("[ 1/%d] Simscape Battery availability .......... ",nStages);

requiredFunctions = { ...
    "batteryCell"
    "batteryCylindricalGeometry"
    "batteryParallelAssembly"
    "batteryModule"
    "batteryModuleAssembly"
    "batteryPack"
    "batteryChart"
    "buildBattery"};

missing = {};

for k = 1:numel(requiredFunctions)

    if isempty(which(requiredFunctions{k}))
        missing{end+1} = requiredFunctions{k}; %#ok<SAGROW>
    end

end

if ~isempty(missing)

    fprintf("FAIL\n\nMissing functions:\n");

    for k = 1:numel(missing)
        fprintf("   %s\n",missing{k});
    end

    error("Simscape Battery installation or path problem.");

end

fprintf("PASS\n");

%% ============================================================
% 2. PROJECT FILES
%% ============================================================

fprintf("[ 2/%d] Project file structure ................. ",nStages);

expectedFiles = { ...
    "08_compliance/P50B_MonacoCompliance.m"
    "00_common/P50B_Param.m"
    "00_common/P50B_Value.m"
    "00_common/P50B_Unwrap.m"
    "00_common/P50B_ProjectRoot.m"
    "00_common/P50B_ProvenanceReport.m"
    "01_cell/P50B_CellData.m"
    "01_cell/P50B_OCV.m"
    "01_cell/P50B_DCIR.m"
    "02_pack/P50B_21P.m"
    "02_pack/P50B_13S21P.m"
    "02_pack/P50B_26S21P.m"
    "03_mechanical/P50B_Geometry.m"
    "03_mechanical/P50B_GroupLayout.m"
    "03_mechanical/P50B_CellCoordinates.m"
    "03_mechanical/P50B_Busbars.m"
    "06_drivetrain/P50B_MotorData.m"
    "06_drivetrain/P50B_InverterData.m"
    "06_drivetrain/P50B_HarnessData.m"
    "06_drivetrain/P50B_AuxiliaryLoads.m"
    "06_drivetrain/P50B_DrivetrainModel.m"
    "07_simulation/P50B_MissionProfile.m"
    "07_simulation/P50B_RunMission.m"};

missingFiles = {};

for k = 1:numel(expectedFiles)

    if ~isfile(fullfile(projectRoot,expectedFiles{k}))
        missingFiles{end+1} = expectedFiles{k}; %#ok<SAGROW>
    end

end

if ~isempty(missingFiles)

    fprintf("FAIL\n\nMissing files:\n");

    for k = 1:numel(missingFiles)
        fprintf("   %s\n",missingFiles{k});
    end

    error("Project file structure is incomplete.");

end

fprintf("PASS\n");

%% ============================================================
% 3. PROVENANCE INFRASTRUCTURE
%% ============================================================

fprintf("[ 3/%d] Provenance helpers ..................... ",nStages);

try

    p = P50B_Param(1.23,"V","DATASHEET","Note","test");

    assert(p.Value == 1.23);
    assert(p.Unit == "V");
    assert(p.Source == "DATASHEET");
    assert(p.Confidence == 2);
    assert(P50B_Value(p) == 1.23);
    assert(P50B_Value(4.56) == 4.56);

    s.a = P50B_Param(1,"m","MEASURED");
    s.b = P50B_Param(2,"m","PLACEHOLDER");

    plain = P50B_Unwrap(s);

    assert(plain.a == 1 && plain.b == 2);

    %% --------------------------------------------------------
    % An invalid source tag must be rejected, otherwise the
    % whole provenance scheme can be bypassed by a typo.
    %% --------------------------------------------------------

    threw = false;

    try
        P50B_Param(1,"V","PROBABLY_FINE");
    catch
        threw = true;
    end

    assert(threw,"An invalid source tag was accepted.");

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("PROVENANCE TEST FAILED.");

end

fprintf("PASS\n");

%% ============================================================
% 4. CELL DATA
%% ============================================================

fprintf("[ 4/%d] P50B cell definition ................... ",nStages);

try

    data = P50B_CellData();

    assert(isfield(data,"Cell"));
    assert(isfield(data,"P"));

    %% --------------------------------------------------------
    % Datasheet values
    %% --------------------------------------------------------

    assert(data.Capacity_Ah == 5.0);
    assert(data.NominalVoltage_V == 3.6);
    assert(data.MaxVoltage_V == 4.2);
    assert(data.MinVoltage_V == 2.5);
    assert(data.MaxContinuousCurrent_A == 60);

    assert(abs(data.Diameter_m - 21.55e-3) < 1e-12);
    assert(abs(data.Height_m - 70.15e-3) < 1e-12);

    %% --------------------------------------------------------
    % Backward-compatibility aliases
    %
    % These are what the older scripts referenced. Their absence
    % is what made P50B_26S21P_MASTER and P50B_MechanicalLayout
    % fail at runtime.
    %% --------------------------------------------------------

    assert(isfield(data,"Vnom") && data.Vnom == data.NominalVoltage_V);
    assert(isfield(data,"Vmax") && data.Vmax == data.MaxVoltage_V);
    assert(isfield(data,"Vmin") && data.Vmin == data.MinVoltage_V);
    assert(isfield(data,"Diameter") && data.Diameter == data.Diameter_m);
    assert(isfield(data,"Height")   && data.Height   == data.Height_m);
    assert(isfield(data,"Radius")   && data.Radius   == data.Radius_m);

    assert(isa(data.Cell,"simscape.battery.builder.Cell"));

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("CELL TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        %.1f Ah, %.1f V nominal, %.0f A continuous\n", ...
    data.Capacity_Ah,data.NominalVoltage_V,data.MaxContinuousCurrent_A);

%% ============================================================
% 5. OCV AND DCIR
%% ============================================================

fprintf("[ 5/%d] OCV curve and DCIR surface ............. ",nStages);

try

    OCV = P50B_OCV();

    assert(all(diff(OCV.SOC) > 0),"SOC must be increasing.");
    assert(all(diff(OCV.V) > 0),"OCV must be monotonic.");

    %% --------------------------------------------------------
    % Endpoint sanity.
    %
    % A tolerance, not an equality: the curve now comes from
    % traced datasheet plots, so it lands near 4.2 V rather than
    % exactly on it. Demanding equality would be demanding that
    % the tracing be perfect.
    %% --------------------------------------------------------

    assert(OCV.Evaluate(1.0) > 4.10 && OCV.Evaluate(1.0) <= 4.25, ...
        "OCV at full charge is %.3f V, expected near 4.2 V.", ...
        OCV.Evaluate(1.0));

    assert(OCV.Evaluate(0.0) >= 2.4 && OCV.Evaluate(0.0) < 3.4, ...
        "OCV at empty is %.3f V, which is not physical.", ...
        OCV.Evaluate(0.0));

    %% --------------------------------------------------------
    % Round-trip through the inverse map
    %% --------------------------------------------------------

    for s = [0.2 0.5 0.8]
        v = OCV.Evaluate(s);
        sBack = OCV.InverseEvaluate(v);
        assert(abs(sBack - s) < 1e-3, ...
            "OCV inverse map is not consistent at SOC %.2f.",s);
    end

    %% --------------------------------------------------------
    % Clamping outside [0,1]
    %% --------------------------------------------------------

    assert(OCV.Evaluate(1.5) == OCV.Evaluate(1.0));
    assert(OCV.Evaluate(-0.5) == OCV.Evaluate(0.0));

    DCIR = P50B_DCIR();

    assert(all(DCIR.R_Ohm(:) > 0));

    %% --------------------------------------------------------
    % Physical trends: cold and empty must be more resistive
    %% --------------------------------------------------------

    assert(P50B_DCIR(0.5,0) > P50B_DCIR(0.5,25), ...
        "A cold cell must have higher resistance.");

    assert(P50B_DCIR(0.10,25) > P50B_DCIR(0.50,25), ...
        "A nearly empty cell must have higher resistance.");

    %% --------------------------------------------------------
    % Datasheet anchor
    %% --------------------------------------------------------

    %% --------------------------------------------------------
    % Cross-check the digitised map against the datasheet DCIR.
    %
    % These are two independent routes to the same quantity: the
    % headline 12.8 mOhm figure, and a map extracted pairwise
    % from the traced rate curves. They should agree to within
    % tracing error. If they ever diverge badly, one of them is
    % wrong and the model should stop rather than pick a side.
    %% --------------------------------------------------------

    Rdigitised = P50B_DCIR(0.5,25);

    Rdatasheet = data.DCIR_Ohm;

    disagreement = abs(Rdigitised - Rdatasheet)/Rdatasheet;

    assert(disagreement < 0.25, ...
        ["Digitised R0 (%.2f mOhm) and datasheet DCIR (%.2f mOhm) " ...
         "disagree by %.0f%%. One of them is wrong."], ...
        Rdigitised*1e3,Rdatasheet*1e3,disagreement*100);

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("CELL CHARACTERISTIC TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        OCV: %s | DCIR: %s\n",OCV.Source,DCIR.Source);

%% ============================================================
% 6. GEOMETRY
%% ============================================================

fprintf("[ 6/%d] Mechanical geometry .................... ",nStages);

try

    G = P50B_Geometry();

    assert(G.Group.Rows == 3);
    assert(G.Group.Columns == 7);
    assert(G.Group.NumberOfCells == 21);
    assert(G.Pack.SeriesGroups == 26);
    assert(G.Pack.ParallelCells == 21);
    assert(G.Pack.Layers == 2);
    assert(G.Pack.GroupsPerLayer == 13);
    assert(G.Pack.TotalCells == 546);

    %% --------------------------------------------------------
    % Geometry must agree with the cell definition
    %% --------------------------------------------------------

    assert(abs(G.Cell.Diameter - data.Diameter_m) < 1e-12, ...
        "Geometry and cell definition disagree on diameter.");

    assert(abs(G.Cell.Height - data.Height_m) < 1e-12, ...
        "Geometry and cell definition disagree on height.");

    %% --------------------------------------------------------
    % Envelope sanity
    %% --------------------------------------------------------

    assert(G.Pack.Width > 0 && G.Pack.Depth > 0 && G.Pack.Height > 0);

    assert(G.Pack.ExternalWidth > G.Pack.Width);
    assert(G.Pack.ExternalHeight > G.Pack.Height);

    assert(G.Pack.PackagingEfficiency > 0 && ...
           G.Pack.PackagingEfficiency < 1);

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("GEOMETRY TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        Envelope %.0f x %.0f x %.0f mm, %.0f%% cell by volume\n", ...
    G.Pack.ExternalWidth*1e3, ...
    G.Pack.ExternalDepth*1e3, ...
    G.Pack.ExternalHeight*1e3, ...
    G.Pack.PackagingEfficiency*100);

%% ============================================================
% 7. LAYOUT AND 546 CELLS
%% ============================================================

fprintf("[ 7/%d] Group layout and 546 cells ............. ",nStages);

try

    Layout = P50B_GroupLayout(G,"Plot",false,"Verbose",false);

    assert(height(Layout.Groups) == 26);
    assert(height(Layout.Cells) == 546);

    groupCounts = accumarray(Layout.Cells.SeriesGroup,1);
    assert(all(groupCounts == 21));

    layerCounts = accumarray(Layout.Cells.Layer,1);
    assert(all(layerCounts == 273));

    assert(all(isfinite(Layout.Cells.X)));
    assert(all(isfinite(Layout.Cells.Y)));
    assert(all(isfinite(Layout.Cells.Z)));

    %% --------------------------------------------------------
    % Unified output contract
    %
    % These fields were only produced by one of the project's
    % two former layout functions, which is why verification
    % could not run.
    %% --------------------------------------------------------

    assert(isfield(Layout,"PackWidth"));
    assert(isfield(Layout,"PackDepth"));
    assert(isfield(Layout,"PackHeight"));
    assert(isfield(Layout,"Cells"));
    assert(isfield(Layout,"Groups"));

    %% --------------------------------------------------------
    % The serpentine must keep consecutive groups adjacent
    %% --------------------------------------------------------

    assert(Layout.AllStepsAdjacent, ...
        "%d series link(s) do not join physically adjacent groups.", ...
        numel(Layout.NonAdjacentSteps));

    %% --------------------------------------------------------
    % Terminal alternation
    %% --------------------------------------------------------

    for g = 1:26

        if mod(g,2) == 1
            assert(Layout.Groups.PositiveTerminal(g) == "BOTTOM");
        else
            assert(Layout.Groups.PositiveTerminal(g) == "TOP");
        end

        assert(Layout.Groups.PositiveTerminal(g) ~= ...
               Layout.Groups.NegativeTerminal(g));

    end

    %% --------------------------------------------------------
    % Compatibility wrapper must produce the same pack
    %% --------------------------------------------------------

    LayoutCompat = P50B_MechanicalLayout(data, ...
        "Plot",false,"Verbose",false,"Write",false);

    assert(height(LayoutCompat.Cells) == 546);
    assert(isfield(LayoutCompat,"PackWidth"));

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("LAYOUT TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        Series path %.2f m, longest step %.0f mm\n", ...
    Layout.PathLength,Layout.MaxStepLength*1e3);

%% ============================================================
% 8. BUSBARS
%% ============================================================

fprintf("[ 8/%d] Busbar and interconnect model .......... ",nStages);

try

    Bus = P50B_Busbars(G,Layout,"Plot",false,"Verbose",false);

    assert(height(Bus.SeriesLinks) == 25);

    %% --------------------------------------------------------
    % All three resistance components must be present and
    % positive. The joint term is the one that was missing
    % entirely from the previous model.
    %% --------------------------------------------------------

    assert(Bus.Rjoint > 0,"Joint resistance must be included.");
    assert(Bus.Rcollector > 0);
    assert(Bus.Rseries > 0);

    assert(abs(Bus.Rtotal - ...
        (Bus.Rjoint + Bus.Rcollector + Bus.Rseries)) < 1e-12, ...
        "Resistance components do not sum to the total.");

    %% --------------------------------------------------------
    % Shares must sum to one
    %% --------------------------------------------------------

    shareSum = Bus.Share.Joints + ...
               Bus.Share.Collectors + ...
               Bus.Share.SeriesLinks;

    assert(abs(shareSum - 1) < 1e-9);

    %% --------------------------------------------------------
    % Copper resistivity must be temperature-corrected upward
    %% --------------------------------------------------------

    assert(Bus.Material.ResistivityHot > Bus.Material.Resistivity20C, ...
        "Busbar resistivity must be evaluated at temperature.");

    %% --------------------------------------------------------
    % Operating points
    %% --------------------------------------------------------

    assert(height(Bus.OperatingPoints) >= 4);

    assert(all(Bus.OperatingPoints.TotalLoss_W > 0));

    %% --------------------------------------------------------
    % Loss must scale as the square of current
    %% --------------------------------------------------------

    T = Bus.OperatingPoints;

    ratio = (T.Current_A(2)/T.Current_A(1))^2;

    assert(abs(T.TotalLoss_W(2)/T.TotalLoss_W(1) - ratio) < 1e-9, ...
        "Loss must scale with the square of current.");

    %% --------------------------------------------------------
    % Joint count
    %% --------------------------------------------------------

    assert(Bus.Joints.TotalJointCount == 546*2, ...
        "Expected two joints per cell across 546 cells.");

    %% --------------------------------------------------------
    % Legacy fields retained for older scripts
    %% --------------------------------------------------------

    assert(isfield(Bus,"PackCurrent_A"));
    assert(isfield(Bus,"TotalLoss_W"));
    assert(isfield(Bus,"Rtotal"));

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("BUSBAR TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        R = %.3f mOhm (joints %.0f%%, rails %.0f%%, links %.0f%%)\n", ...
    Bus.Rtotal*1e3, ...
    Bus.Share.Joints*100, ...
    Bus.Share.Collectors*100, ...
    Bus.Share.SeriesLinks*100);

%% ============================================================
% 9. DRIVETRAIN DATA
%% ============================================================

fprintf("[ 9/%d] Drivetrain parameter sets .............. ",nStages);

try

    motor = P50B_MotorData();
    inv   = P50B_InverterData();
    harn  = P50B_HarnessData();
    aux   = P50B_AuxiliaryLoads();

    %% --------------------------------------------------------
    % Datasheet values from the Competr document
    %% --------------------------------------------------------

    assert(motor.NominalPower_W == 26.9e3);
    assert(motor.MaximumPower_W == 42e3);
    assert(motor.MaximumTorque_Nm == 100);
    assert(motor.BusMaximumVoltage_V == 109);
    assert(motor.BusMaximumCurrent_A == 375);

    %% --------------------------------------------------------
    % The pack must be electrically compatible with the outboard
    %% --------------------------------------------------------

    packVmax = 26 * data.MaxVoltage_V;

    assert(packVmax <= motor.BusMaximumVoltage_V + 0.5, ...
        "Pack maximum voltage %.1f V exceeds the outboard limit.", ...
        packVmax);

    %% --------------------------------------------------------
    % Inverter sizing must exceed the naive nominal-voltage
    % figure, because worst case is at minimum bus voltage
    %% --------------------------------------------------------

    assert(inv.DCCurrentPeakWorstCase_A > inv.DCCurrentPeak_A, ...
        "Worst-case current must exceed the nominal-voltage figure.");

    assert(inv.DeviceCurrentRatingRequired_A > 0);

    %% --------------------------------------------------------
    % Harness
    %% --------------------------------------------------------

    assert(harn.TotalResistance_Ohm > 0);

    assert(harn.CableResistance_Ohm > 0);

    assert(harn.TotalResistance_Ohm > harn.CableResistance_Ohm, ...
        "Total harness resistance must include joints and switchgear.");

    %% --------------------------------------------------------
    % Auxiliary
    %% --------------------------------------------------------

    assert(aux.AverageLoad12V_W > 0);

    assert(aux.PeakLoad12V_W > aux.AverageLoad12V_W);

    assert(aux.AverageLoadFromPack_W > aux.AverageLoad12V_W, ...
        "Load referred to the pack must exceed the 12 V load.");

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("DRIVETRAIN DATA TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        %s, %.1f kW nom / %.0f kW peak\n", ...
    motor.MotorType,motor.NominalPower_W/1000,motor.MaximumPower_W/1000);

%% ============================================================
% 10. DRIVETRAIN CHAIN MODEL
%% ============================================================

fprintf("[10/%d] Drivetrain chain solver ................ ",nStages);

try

    modelArgs = {"Busbars",Bus,"Motor",motor,"Inverter",inv, ...
                 "Harness",harn,"Auxiliary",aux,"Cell",data};

    op = P50B_DrivetrainModel(25e3,2400,0.6,30,modelArgs{:});

    assert(op.Feasible,"25 kW must be feasible at 60%% SOC.");

    %% --------------------------------------------------------
    % Monaco ENERGY_REQ_188 is a hard cap, not a warning.
    %
    % Motor electrical input must never exceed 25 kW, whatever
    % is demanded.
    %% --------------------------------------------------------

    assert(op.Motor.InputPower_W <= motor.ConfiguredPowerLimit_W + 1, ...
        "Motor input %.0f W exceeds the %.0f W cap.", ...
        op.Motor.InputPower_W,motor.ConfiguredPowerLimit_W);

    assert(op.Limits.RulePowerOK, ...
        "The 25 kW rule power limit was not respected.");

    %% --------------------------------------------------------
    % An absurd demand must be capped, not delivered
    %% --------------------------------------------------------

    opOver = P50B_DrivetrainModel(60e3,2400,0.6,30,modelArgs{:});

    assert(opOver.PowerLimit.Active, ...
        "A 60 kW demand must trigger the power cap.");

    assert(opOver.Motor.InputPower_W <= ...
        motor.ConfiguredPowerLimit_W + 1, ...
        "Motor input %.0f W exceeds the cap under a 60 kW demand.", ...
        opOver.Motor.InputPower_W);

    assert(opOver.PowerLimit.DeliveredShaft_W < 60e3, ...
        "Delivered shaft power should have been reduced.");

    %% --------------------------------------------------------
    % Power must increase monotonically back up the chain
    %% --------------------------------------------------------

    assert(op.Motor.InputPower_W > op.Gearbox.InputPower_W);
    assert(op.Inverter.InputPower_W > op.Motor.InputPower_W);
    assert(op.Bus.DemandedPower_W > op.Inverter.InputPower_W);
    assert(op.Pack.DrawnPower_W > op.Bus.DemandedPower_W);

    %% --------------------------------------------------------
    % Efficiencies must be physical
    %% --------------------------------------------------------

    assert(op.Motor.Efficiency > 0 && op.Motor.Efficiency < 1);
    assert(op.Inverter.Efficiency > 0 && op.Inverter.Efficiency < 1);
    assert(op.Chain.OverallEfficiency > 0 && ...
           op.Chain.OverallEfficiency < 1);

    %% --------------------------------------------------------
    % Energy balance at a single operating point
    %% --------------------------------------------------------

    balance = op.Pack.DrawnPower_W - ...
              (op.Chain.ShaftPower_W + op.Chain.TotalLoss_W);

    assert(abs(balance) < 1e-6 * op.Pack.DrawnPower_W, ...
        "Operating point does not balance: %.4f W discrepancy.", ...
        balance);

    %% --------------------------------------------------------
    % Terminal voltage must sag under load, never rise
    %% --------------------------------------------------------

    assert(op.Pack.TerminalVoltage_V < op.Pack.OCV_V);
    assert(op.Pack.VoltageSag_V > 0);

    %% --------------------------------------------------------
    % Loss breakdown must sum to the total
    %% --------------------------------------------------------

    assert(abs(sum(op.Chain.LossBreakdown.Loss_W) - ...
        op.Chain.TotalLoss_W) < 1e-9);

    %% --------------------------------------------------------
    % A cold, nearly empty pack must draw more current for the
    % same shaft power than a warm, half-full one
    %% --------------------------------------------------------

    opCold = P50B_DrivetrainModel(25e3,2400,0.15,0,modelArgs{:});

    if opCold.Feasible
        assert(opCold.Pack.Current_A > op.Pack.Current_A, ...
            "A cold, low-SOC pack must draw more current.");
    end

    %% --------------------------------------------------------
    % An impossible demand must be reported, not silently
    % clamped to something plausible
    %% --------------------------------------------------------

    opImpossible = P50B_DrivetrainModel(500e3,3000,0.05,-10,modelArgs{:});

    assert(~opImpossible.Feasible, ...
        "A 500 kW demand at 5%% SOC must be flagged infeasible.");

    assert(strlength(opImpossible.InfeasibleReason) > 0);

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("DRIVETRAIN MODEL TEST FAILED.");

end

fprintf("PASS\n");
if op.PowerLimit.Active
    fprintf("        25 kW cap active: %.1f kW asked -> %.1f kW shaft\n", ...
        op.PowerLimit.RequestedShaft_W/1000, ...
        op.PowerLimit.DeliveredShaft_W/1000);
end
fprintf("        %.1f A pack, %.1f kW motor input, %.1f%% chain\n", ...
    op.Pack.Current_A, ...
    op.Motor.InputPower_W/1000, ...
    op.Chain.OverallEfficiency*100);

%% ============================================================
% 11. THERMAL AND MISSION
%% ============================================================

fprintf("[11/%d] Thermal model and mission run .......... ",nStages);

try

    Thermal = P50B_ThermalDesign(data, ...
        "Busbars",Bus,"Plot",false,"Verbose",false);

    assert(height(Thermal.Table) > 0);

    assert(all(Thermal.Table.TotalHeat_W > 0));

    %% --------------------------------------------------------
    % Heat must rise with current
    %% --------------------------------------------------------

    assert(all(diff(Thermal.Table.TotalHeat_W) > 0), ...
        "Heat generation must increase with current.");

    %% --------------------------------------------------------
    % Interconnect heat must be included
    %% --------------------------------------------------------

    assert(all(Thermal.Table.BusbarHeat_W > 0), ...
        "Interconnect heat must be part of the thermal model.");

    %% --------------------------------------------------------
    % Short mission run
    %% --------------------------------------------------------

    Profile = P50B_MissionProfile("constant", ...
        "Duration",120,"TimeStep",1,"Power",15e3);

    Mission = P50B_RunMission(Profile, ...
        "Plot",false,"Verbose",false);

    assert(Mission.Completed,"Short mission must complete.");

    assert(Mission.Summary.SOCEnd < Mission.Summary.SOCStart, ...
        "SOC must fall during a discharge.");

    assert(Mission.Energy.BalanceOK, ...
        "Mission energy balance failed: %.3f%% discrepancy.", ...
        Mission.Energy.BalanceErrorPercent);

    assert(Mission.Summary.PeakCellTemp_C >= Mission.CellTemp_C(1), ...
        "Cell temperature must not fall while discharging.");

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("THERMAL / MISSION TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        Mission balance error %.4f%%\n", ...
    Mission.Energy.BalanceErrorPercent);

%% ============================================================
% 12. HYDRODYNAMICS
%
% The hull, the contra-rotating propulsor and the dynamics.
% These arrived with the hydrodynamics team's design tool and
% they are what makes ENERGY_REQ_37 and ENERGY_REQ_32 checkable
% rather than checklist items, so they need protecting.
%% ============================================================

fprintf("[12/%d] Hull, propulsor and boat dynamics ...... ",nStages);

try

    Hull = P50B_HullModel();

    %% --------------------------------------------------------
    % The supplied curve must be reproduced exactly at every
    % point it was measured at, minus the drive-leg term the
    % model adds on top. If interpolation has drifted off the
    % data there is no point checking anything downstream.
    %% --------------------------------------------------------

    knots = P50B_HydroConstants().KnotsPerMs;

    Pq = P50B_LoadParams("Plain",true);

    vPts = Pq.hydro.resistance_speed_kn(:)';
    RPts = Pq.hydro.resistance_bare_hull_N(:)';

    legCoeff = Pq.hydro.drive_leg_drag_N_at_20kn / ...
               (Pq.hydro.resistance_max_valid_kn/knots)^2;

    for kk = 1:numel(vPts)

        vv = vPts(kk)/knots;

        expected = RPts(kk) + legCoeff*vv^2;

        assert(abs(Hull.SuppliedHydro_N(vv) - expected) < 1e-6, ...
            "The hull model does not reproduce supplied point %d " + ...
            "(%.0f kn): got %.4f N, expected %.4f N.", ...
            kk,vPts(kk),Hull.SuppliedHydro_N(vv),expected);

    end

    %% --------------------------------------------------------
    % Resistance must increase with speed. A dip would mean the
    % interpolator has overshot between points, which is exactly
    % what pchip was chosen to prevent.
    %% --------------------------------------------------------

    vSweep = (1:0.5:30)/knots;

    Rsweep = arrayfun(@(x) Hull.Resistance_N(x), vSweep);

    assert(all(diff(Rsweep) > 0), ...
        "Hull resistance is not monotonic in speed.");

    %% --------------------------------------------------------
    % The propulsor must reproduce the BEM design point. This is
    % the whole basis of the momentum-theory extension: if it
    % does not land on the solved answer, nothing either side of
    % it is worth anything.
    %% --------------------------------------------------------

    Prop = P50B_Propulsor();

    T_design = Prop.ThrustFromPower_N(Prop.DesignSpeed_ms, ...
                                      Prop.DesignShaftPower_W);

    assert(abs(T_design - Prop.DesignThrust_N) < 1.0, ...
        "The propulsor does not reproduce its own design thrust: " + ...
        "%.2f N against %.2f N.",T_design,Prop.DesignThrust_N);

    %% --------------------------------------------------------
    % Thrust at rest must be finite and positive. An earlier
    % version returned zero here -- the efficiency relation goes
    % to 0/0 at v = 0 -- and the boat could not leave the dock.
    %% --------------------------------------------------------

    T_bollard = Prop.ThrustFromPower_N(0,Prop.DesignShaftPower_W);

    assert(isfinite(T_bollard) && T_bollard > 0, ...
        "Bollard thrust must be finite and positive, got %g.",T_bollard);

    %% --------------------------------------------------------
    % Both drivetrain ceilings must actually bind.
    %% --------------------------------------------------------

    Boat = P50B_BoatDynamics("Hull",Hull,"Propeller",Prop);

    assert(Boat.ShaftPowerMax_W < ...
           P50B_Value(motor.ConfiguredPowerLimit_W), ...
        "The shaft ceiling must be BELOW the 25 kW electrical cap. " + ...
        "ENERGY_REQ_188 caps consumption, not shaft power.");

    vTop = Boat.SteadySpeed(Boat.ShaftPowerMax_W);

    [Pok,~] = Boat.TorqueLimitedPower(vTop,Boat.ShaftPowerMax_W);

    assert(Pok <= Boat.ShaftPowerMax_W + 1e-6, ...
        "The torque ceiling must never exceed the power ceiling.");

    nProp = Prop.RPSForPower(vTop,Pok*Boat.DrivelineEfficiency);

    torque = (Pok/P50B_Value(motor.GearboxEfficiency)) / ...
             (2*pi*nProp*Prop.GearRatio);

    assert(torque <= P50B_Value(motor.MaximumTorque_Nm)*1.01, ...
        "Top speed asks for %.1f Nm against a %.1f Nm motor.", ...
        torque,P50B_Value(motor.MaximumTorque_Nm));

    %% --------------------------------------------------------
    % ENERGY_REQ_37 and ENERGY_REQ_32
    %% --------------------------------------------------------

    Perf = P50B_BoatPerformance("Hull",Hull,"Propeller",Prop, ...
        "Boat",Boat,"Verbose",false);

    assert(Perf.MinimumSpeed.Achievable, ...
        "ENERGY_REQ_37: the boat cannot reach 3 knots.");

    assert(Perf.Reverse.Achievable, ...
        "ENERGY_REQ_32: no astern thrust margin.");

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("HYDRODYNAMICS TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        Top speed %.1f km/h, %.2f kW of the %.0f kW cap\n", ...
    Perf.TopSpeed_kmh, Boat.ShaftPowerMax_W/1000, ...
    P50B_Value(motor.ConfiguredPowerLimit_W)/1000);

%% ============================================================
% 13. MASS BUDGET
%% ============================================================

fprintf("[13/%d] Weight budget, ENERGY_REQ_48 ........... ",nStages);

try

    Budget = P50B_MassBudget("Verbose",false);

    assert(Budget.Pass, ...
        "ENERGY_REQ_48: %.1f kg excluding hulls, over the %.0f kg " + ...
        "limit. An overweight boat is not allowed in the water.", ...
        Budget.ExcludingHulls_kg,Budget.Limit_kg);

    %% --------------------------------------------------------
    % The floating mass the hydrodynamics runs at must match the
    % budget. These disagreed by 65 kg -- the boat was being
    % modelled without its own hulls -- and nothing noticed.
    %% --------------------------------------------------------

    assert(Budget.DisplacementConsistent, ...
        "boat.displacement_kg is %.1f kg but the budget floats " + ...
        "%.1f kg. The hydrodynamics is running at the wrong mass.", ...
        Budget.ParameterDisplacement_kg,Budget.FloatingMass_kg);

    %% --------------------------------------------------------
    % ENERGY_REQ_135: a pilot under 60 kg must produce ballast,
    % and that ballast must land in the budget.
    %% --------------------------------------------------------

    Light = P50B_MassBudget("PilotMass_kg",52,"Verbose",false);

    assert(Light.Pilot.Ballast_kg > 0, ...
        "ENERGY_REQ_135: a 52 kg pilot must require ballast.");

    assert(abs(Light.Pilot.Mass_kg + Light.Pilot.Ballast_kg - ...
               Light.Pilot.Minimum_kg) < 1e-9, ...
        "Ballast must bring the pilot exactly to the 60 kg minimum.");

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("MASS BUDGET TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        %.1f kg of %.0f kg, %.1f kg margin (%.1f%%)\n", ...
    Budget.ExcludingHulls_kg,Budget.Limit_kg, ...
    Budget.Margin_kg,Budget.MarginPercent);

%% ============================================================
% 14. VERIFICATION AND PROVENANCE
%% ============================================================

fprintf("[14/%d] Verification and provenance ............ ",nStages);

try

    Report = P50B_Verification(data,Layout,Thermal, ...
        "Busbars",Bus,"Verbose",false);

    assert(Report.NumChecks > 20, ...
        "Verification should run a meaningful number of checks.");

    assert(Report.AllCriticalPassed, ...
        "%d critical verification check(s) failed.", ...
        Report.ErrorsFailed);

    Provenance = P50B_ProvenanceReport(data,motor,inv,harn,aux);

    assert(height(Provenance) > 50, ...
        "Provenance audit should cover every tagged parameter.");

    %% --------------------------------------------------------
    % No placeholders should remain. Assumptions are acceptable
    % and expected; placeholders are not.
    %% --------------------------------------------------------

    nPlaceholder = sum(Provenance.Source == "PLACEHOLDER");

    assert(nPlaceholder == 0, ...
        "%d PLACEHOLDER parameter(s) remain in the model.", ...
        nPlaceholder);

    %% --------------------------------------------------------
    % Monaco Energy Class rules
    %
    % Every quantifiable rule must pass. Items tagged ACTION or
    % CHECKLIST are procedural and cannot be satisfied from the
    % model, so they do not fail the test -- but a genuine rule
    % violation does.
    %% --------------------------------------------------------

    Compliance = P50B_MonacoCompliance( ...
        "Cell",     data, ...
        "Motor",    motor, ...
        "Harness",  harn, ...
        "Busbars",  Bus, ...
        "Geometry", G, ...
        "Thermal",  Thermal, ...
        "Verbose",  false);

    assert(Compliance.NumFail == 0, ...
        "%d Monaco rule violation(s): %s", ...
        Compliance.NumFail, ...
        strjoin(Compliance.Checks.Req( ...
            Compliance.Checks.Status == "FAIL"),", "));

    %% --------------------------------------------------------
    % The 10 kWh energy limit is the rule most likely to be
    % broken by a well-meaning change to the pack, so it gets
    % its own explicit assertion.
    %% --------------------------------------------------------

    assert(Compliance.Energy.StoredEnergy_Wh < 10000, ...
        "Stored energy %.0f Wh exceeds the 10 kWh limit.", ...
        Compliance.Energy.StoredEnergy_Wh);

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("VERIFICATION TEST FAILED.");

end

fprintf("PASS\n");
fprintf("        %d checks passed, %d parameters audited\n", ...
    Report.NumPassed,height(Provenance));
fprintf("        Monaco rules: %d pass, %d violation(s), %d to action\n", ...
    Compliance.NumPass,Compliance.NumFail,Compliance.NumAction);

%% ============================================================
% FINAL REPORT
%% ============================================================

elapsed = toc(testStart);

fprintf("\n");
fprintf("============================================================\n");
fprintf("                  ALL TESTS PASSED\n");
fprintf("            (%.1f s)\n",elapsed);
fprintf("============================================================\n");

S = Report.Summary;

fprintf("\nARCHITECTURE\n");
fprintf("  Cell                     : %s\n",data.Model);
fprintf("  Configuration            : %dS%dP\n", ...
    S.SeriesGroups,S.ParallelCells);
fprintf("  Total cells              : %d\n",S.TotalCells);
fprintf("  Layers                   : %d x %d groups\n", ...
    G.Pack.Layers,G.Pack.GroupsPerLayer);

fprintf("\nELECTRICAL\n");
fprintf("  Nominal voltage          : %.2f V\n",S.NominalVoltage_V);
fprintf("  Voltage range            : %.2f to %.2f V\n", ...
    S.MinVoltage_V,S.MaxVoltage_V);
fprintf("  Capacity                 : %.2f Ah\n",S.Capacity_Ah);
fprintf("  Energy                   : %.3f kWh\n",S.Energy_kWh);

fprintf("\nMECHANICAL\n");
fprintf("  Cell envelope            : %.0f x %.0f x %.0f mm\n", ...
    S.PackWidth_mm,S.PackDepth_mm,S.PackHeight_mm);
fprintf("  External envelope        : %.0f x %.0f x %.0f mm\n", ...
    S.ExternalWidth_mm,S.ExternalDepth_mm,S.ExternalHeight_mm);
fprintf("  Cell mass                : %.1f kg\n",S.CellMass_kg);
fprintf("  Pack mass (estimate)     : %.1f kg\n",S.PackMassEstimate_kg);

fprintf("\nINTERCONNECT\n");
fprintf("  Total resistance         : %.3f mOhm\n", ...
    S.InterconnectResistance_mOhm);
fprintf("  Cell-to-busbar joints    : %.3f mOhm (%.0f%%)\n", ...
    Bus.Rjoint*1e3,Bus.Share.Joints*100);
fprintf("  Collector rails          : %.3f mOhm (%.0f%%)\n", ...
    Bus.Rcollector*1e3,Bus.Share.Collectors*100);
fprintf("  Series links             : %.3f mOhm (%.0f%%)\n", ...
    Bus.Rseries*1e3,Bus.Share.SeriesLinks*100);

fprintf("\nDRIVETRAIN\n");
fprintf("  Outboard                 : %s\n",motor.Manufacturer);
fprintf("  Rated power              : %.1f kW nominal, %.0f kW peak\n", ...
    motor.NominalPower_W/1000,motor.MaximumPower_W/1000);
fprintf("  Chain efficiency at 25 kW: %.1f %%\n", ...
    op.Chain.OverallEfficiency*100);

fprintf("\nPARAMETER PROVENANCE\n");

sources = ["DATASHEET" "PUBLISHED_TEST" "CALCULATED" ...
           "DESIGN_CHOICE" "ASSUMPTION" "PLACEHOLDER"];

for k = 1:numel(sources)

    n = sum(Provenance.Source == sources(k));

    if n > 0
        fprintf("  %-18s %4d\n",sources(k),n);
    end

end

%% ============================================================
% SAVE
%% ============================================================

outputDir = fullfile(projectRoot,"output");

if ~isfolder(outputDir)
    mkdir(outputDir);
end

save(fullfile(outputDir,"TEST_ALL_PASSED.mat"), ...
    "data","G","Layout","Bus","Thermal","Report","Provenance", ...
    "motor","inv","harn","aux","Mission","Compliance");

writetable(Compliance.Checks, ...
    fullfile(outputDir,"TEST_MonacoCompliance.csv"));

writetable(Layout.Cells, ...
    fullfile(outputDir,"TEST_CellCoordinates.csv"));

writetable(Layout.Groups, ...
    fullfile(outputDir,"TEST_GroupCoordinates.csv"));

writetable(Bus.SeriesLinks, ...
    fullfile(outputDir,"TEST_BusbarLinks.csv"));

writetable(Provenance, ...
    fullfile(outputDir,"TEST_ParameterProvenance.csv"));

fprintf("\nResults saved to output/.\n");
fprintf("\n============================================================\n");
fprintf(" PROJECT IS WORKING\n");
fprintf("============================================================\n\n");

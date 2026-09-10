%% ============================================================
% TEST_ELECTRICAL.m
%
% P50B 26S21P Simscape electrical test bench.
%
% Builds the generated Simscape battery library, assembles a
% minimal test circuit around the pack block, and discharges it
% at a series of currents, measuring pack voltage and current.
%
% WHAT WAS WRONG WITH THE PREVIOUS VERSION
% ----------------------------------------
% It ran a single 100 A point, then built a results table from
% six variables that were never assigned anywhere in the file:
% CommandedCurrent_A, MeasuredCurrent_A,
% MeasuredCurrentError_percent, FinalVoltage_V, AverageVoltage_V
% and Result. It also referenced nTests, which did not exist.
% The script could not reach its own summary without erroring.
%
% It also contained the same 40-line port-name printing block
% twice in a row.
%
% This version runs the full sweep it was clearly meant to run
% and populates every result it reports.
%
% SCOPE
% -----
% This is an electrical smoke test of the generated Simscape
% model, not a validated electrochemical study. It checks that
% the pack builds, connects, solves, and produces a sane voltage
% under load. Cell dynamics come from the Simscape Battery
% default equivalent circuit, not from measured P50B data.
%% ============================================================

clear;
clc;
close all;

fprintf("\n");
fprintf("============================================================\n");
fprintf("              P50B 26S21P ELECTRICAL TEST\n");
fprintf("============================================================\n");

bdclose("all");

%% ============================================================
% 1. PROJECT ROOT
%% ============================================================

thisFile      = mfilename("fullpath");
testDirectory = fileparts(thisFile);
projectRoot   = fileparts(testDirectory);

cd(projectRoot);
addpath(genpath(projectRoot));

fprintf("\nProject root:\n%s\n",projectRoot);

outputDirectory = fullfile(projectRoot,"output");

if ~isfolder(outputDirectory)
    mkdir(outputDirectory);
end

%% ============================================================
% 2. TEST CONFIGURATION
%
% Currents span the competition cap through the Competr
% continuous rating to the 42 kW peak.
%% ============================================================

testCurrents = [100 267 385];

simStopTime = 0.2;          % s

nTests = numel(testCurrents);

fprintf("\nTest currents : %s A\n", ...
    strjoin(string(testCurrents),", "));
fprintf("Simulation    : %.2f s per point\n",simStopTime);

%% ============================================================
% 3. BUILD BATTERY OBJECTS
%% ============================================================

fprintf("\n[1/6] Building battery objects .................. ");

try

    data = P50B_CellData();

    %% --------------------------------------------------------
    % Lumped resolution for the smoke test.
    %
    % "Detailed" gives all 546 cells their own states, which is
    % the right setting for studying current sharing inside a
    % parallel group -- and far too slow here. A single 0.5 s
    % solve of the detailed pack takes minutes.
    %
    % This test checks that the pack builds, connects, solves and
    % produces a sane voltage under load. None of that needs
    % per-cell resolution. Cell-to-cell imbalance is studied in
    % the Python electro-thermal model, which resolves it far
    % better than a Simscape smoke test would.
    %% --------------------------------------------------------

    P21  = P50B_21P(data,"ModelResolution","Lumped");
    M13  = P50B_13S21P(P21,"ModelResolution","Lumped");
    pack = P50B_26S21P(M13);

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("Battery object construction failed.");

end

fprintf("PASS\n");

%% ------------------------------------------------------------
% Pack parameters
%% ------------------------------------------------------------

Ns = 26;
Np = 21;

Vnom     = Ns * data.NominalVoltage_V;
Vmax     = Ns * data.MaxVoltage_V;
Vmin     = Ns * data.MinVoltage_V;
Capacity = Np * data.Capacity_Ah;

Energy_kWh = Vnom * Capacity / 1000;

fprintf("\nPACK PARAMETERS\n");
fprintf("--------------------------------------------\n");
fprintf("Configuration          : %dS%dP (%d cells)\n",Ns,Np,Ns*Np);
fprintf("Nominal voltage        : %.2f V\n",Vnom);
fprintf("Voltage range          : %.2f to %.2f V\n",Vmin,Vmax);
fprintf("Capacity               : %.2f Ah\n",Capacity);
fprintf("Nominal energy         : %.3f kWh\n",Energy_kWh);
fprintf("--------------------------------------------\n");

%% ============================================================
% 4. BUILD SIMSCAPE LIBRARY
%% ============================================================

fprintf("\n[2/6] Building Simscape battery library ........ ");

libraryName = "P50B_26S21P_Lib";

libraryFile = fullfile(outputDirectory,libraryName + ".slx");

componentLibraryFile = ...
    fullfile(outputDirectory,libraryName + "_lib.slx");

packageDirectory = fullfile(outputDirectory,"+" + libraryName);

[~,libraryModelName,~]    = fileparts(libraryFile);
[~,componentLibraryName,~] = fileparts(componentLibraryFile);

%% ------------------------------------------------------------
% Clean previous artifacts
%% ------------------------------------------------------------

if bdIsLoaded(libraryModelName)
    close_system(libraryModelName,0);
end

if bdIsLoaded(componentLibraryName)
    close_system(componentLibraryName,0);
end

if isfile(libraryFile)
    delete(libraryFile);
end

if isfile(componentLibraryFile)
    delete(componentLibraryFile);
end

if isfolder(packageDirectory)

    [status,msg] = rmdir(packageDirectory,"s");

    if ~status
        error("Could not remove %s\n%s",packageDirectory,msg);
    end

end

%% ------------------------------------------------------------
% Build
%% ------------------------------------------------------------

try

    buildBattery( ...
        pack, ...
        LibraryName=libraryName, ...
        Directory=outputDirectory, ...
        MaskParameters="NumericValues", ...
        MaskInitialTargets="NumericValues", ...
        Verbose="off");

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("buildBattery failed.");

end

if ~isfile(libraryFile)
    error("Generated pack library not found:\n%s",libraryFile);
end

if ~isfile(componentLibraryFile)
    error("Generated component library not found:\n%s", ...
        componentLibraryFile);
end

fprintf("PASS\n");

%% ============================================================
% 5. LOCATE THE GENERATED PACK BLOCK
%% ============================================================

fprintf("[3/6] Locating generated Pack block ............ ");

try

    load_system(libraryFile);

    topBlocks = find_system( ...
        libraryModelName, ...
        "SearchDepth",1, ...
        "Type","Block");

    packBlockName = "";

    %% --------------------------------------------------------
    % Prefer an exact match on the pack object's own name
    %% --------------------------------------------------------

    for k = 1:numel(topBlocks)

        [~,candidateName,~] = fileparts(topBlocks{k});

        if candidateName == string(pack.Name)
            packBlockName = candidateName;
            break;
        end

    end

    %% --------------------------------------------------------
    % Fall back to any block whose name contains "Pack"
    %% --------------------------------------------------------

    if strlength(packBlockName) == 0

        for k = 1:numel(topBlocks)

            [~,candidateName,~] = fileparts(topBlocks{k});

            if contains(candidateName,"Pack","IgnoreCase",true)
                packBlockName = candidateName;
                break;
            end

        end

    end

    if strlength(packBlockName) == 0

        fprintf("FAIL\n\n");
        fprintf("Top-level blocks found:\n");

        for k = 1:numel(topBlocks)
            fprintf("   %s\n",topBlocks{k});
        end

        error("Could not identify the generated Pack block.");

    end

    packLibraryBlock = libraryModelName + "/" + packBlockName;

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));
    error("Could not locate the generated Pack.");

end

fprintf("PASS\n");
fprintf("       Pack block: %s\n",packLibraryBlock);

%% ============================================================
% 6. CREATE THE TEST BENCH
%% ============================================================

fprintf("[4/6] Creating Simscape test bench ............. ");

modelName = "P50B_26S21P_ElectricalTest";

modelFile = fullfile(outputDirectory,modelName + ".slx");

if bdIsLoaded(modelName)
    close_system(modelName,0);
end

if isfile(modelFile)
    delete(modelFile);
end

try

    new_system(modelName);

    %% --------------------------------------------------------
    % Block paths
    %% --------------------------------------------------------

    batteryPath              = modelName + "/P50B Pack";
    currentSourcePath        = modelName + "/Discharge Current";
    currentSensorPath        = modelName + "/Pack Current Sensor";
    voltageSensorPath        = modelName + "/Pack Voltage Sensor";
    electricalReferencePath  = modelName + "/Electrical Reference";
    solverPath               = modelName + "/Solver Configuration";
    currentConverterPath     = modelName + "/Current PS-Simulink";
    voltageConverterPath     = modelName + "/Voltage PS-Simulink";
    currentToWorkspacePath   = modelName + "/Current To Workspace";
    voltageToWorkspacePath   = modelName + "/Voltage To Workspace";

    %% --------------------------------------------------------
    % Add blocks
    %% --------------------------------------------------------

    add_block(packLibraryBlock,batteryPath, ...
        "Position",[400 130 650 300]);

    add_block("fl_lib/Electrical/Electrical Sources/DC Current Source", ...
        currentSourcePath, ...
        "Position",[100 160 220 270], ...
        "i0","-100");

    add_block("fl_lib/Electrical/Electrical Sensors/Current Sensor", ...
        currentSensorPath, ...
        "Position",[275 160 335 270]);

    add_block("fl_lib/Electrical/Electrical Sensors/Voltage Sensor", ...
        voltageSensorPath, ...
        "Position",[450 340 570 400]);

    add_block("fl_lib/Electrical/Electrical Elements/Electrical Reference", ...
        electricalReferencePath, ...
        "Position",[350 430 390 470], ...
        "ShowName","off");

    add_block("nesl_utility/Solver Configuration", ...
        solverPath, ...
        "Position",[180 430 250 490]);

    %% --------------------------------------------------------
    % No PS-Simulink converters or To Workspace blocks.
    %
    % Signals are captured with Simscape logging instead, which
    % records every variable in the physical network without any
    % wiring at all. Hand-wiring converters to sensor outputs is
    % the fragile part of building a bench programmatically --
    % physical-signal port handles differ between block types and
    % releases -- and it buys nothing here.
    %% --------------------------------------------------------

    %% --------------------------------------------------------
    % Discover the generated pack's port names
    %
    % The generated block's terminal names are not guessed. They
    % are read back from the model, and the two electrical ports
    % are identified from that list.
    %--------------------------------------------------------

    batteryPorts = simscape.connectionPortProperties(batteryPath);

    portNames = string({batteryPorts.Name});

    fprintf("\n       Generated pack ports: %s\n", ...
        strjoin(portNames,", "));

    %% --------------------------------------------------------
    % Identify positive and negative terminals
    %% --------------------------------------------------------

    posCandidates = ["+" "p" "Pos" "POS" "Positive"];
    negCandidates = ["-" "n" "Neg" "NEG" "Negative"];

    packPosPort = "";
    packNegPort = "";

    for k = 1:numel(posCandidates)
        if any(portNames == posCandidates(k))
            packPosPort = posCandidates(k);
            break;
        end
    end

    for k = 1:numel(negCandidates)
        if any(portNames == negCandidates(k))
            packNegPort = negCandidates(k);
            break;
        end
    end

    if strlength(packPosPort) == 0 || strlength(packNegPort) == 0

        error("Could not identify the pack terminal ports. " + ...
              "Ports present: %s",strjoin(portNames,", "));

    end

    fprintf("       Using terminals: %s and %s\n", ...
        packPosPort,packNegPort);

    %% --------------------------------------------------------
    % Connect the electrical network
    %
    % Pack + -> current sensor -> current source -> pack -
    %% --------------------------------------------------------

    simscape.addConnection( ...
        batteryPath,packPosPort, ...
        currentSensorPath,"p","autorouting","smart");

    simscape.addConnection( ...
        currentSensorPath,"n", ...
        currentSourcePath,"p","autorouting","smart");

    simscape.addConnection( ...
        currentSourcePath,"n", ...
        batteryPath,packNegPort,"autorouting","smart");

    %% --------------------------------------------------------
    % Voltage sensor across the pack
    %% --------------------------------------------------------

    simscape.addConnection( ...
        voltageSensorPath,"p", ...
        batteryPath,packPosPort,"autorouting","smart");

    simscape.addConnection( ...
        voltageSensorPath,"n", ...
        batteryPath,packNegPort,"autorouting","smart");

    %% --------------------------------------------------------
    % Reference and solver
    %% --------------------------------------------------------

    simscape.addConnection( ...
        electricalReferencePath,"V", ...
        batteryPath,packNegPort,"autorouting","smart");

    simscape.addConnection( ...
        solverPath,"port", ...
        batteryPath,packNegPort,"autorouting","smart");

    %% --------------------------------------------------------
    % Solver settings
    %% --------------------------------------------------------

    set_param(modelName,"Solver","daessc");
    set_param(modelName,"StopTime",num2str(simStopTime));
    set_param(modelName,"MaxStep","0.001");
    set_param(modelName,"RelTol","1e-4");
    set_param(modelName,"ReturnWorkspaceOutputs","on");

    %% --------------------------------------------------------
    % Simscape logging
    %% --------------------------------------------------------

    set_param(modelName,"SimscapeLogType","all");
    set_param(modelName,"SimscapeLogName","simlog");

    save_system(modelName,modelFile);

catch ME

    fprintf("FAIL\n\n");
    disp(getReport(ME,"extended","hyperlinks","off"));

    if bdIsLoaded(modelName)
        save_system(modelName,modelFile);
        fprintf("Partial model saved to %s for inspection.\n",modelFile);
    end

    error("Simscape test bench creation failed.");

end

fprintf("       PASS\n");

%% ============================================================
% 7. RUN THE CURRENT SWEEP
%% ============================================================

fprintf("[5/6] Running current sweep .................... \n");

CommandedCurrent_A           = zeros(nTests,1);
MeasuredCurrent_A            = zeros(nTests,1);
MeasuredCurrentError_percent = zeros(nTests,1);
FinalVoltage_V               = zeros(nTests,1);
AverageVoltage_V             = zeros(nTests,1);
MinVoltage_V                 = zeros(nTests,1);
SolverTime_s                 = zeros(nTests,1);
Result                       = strings(nTests,1);
FailureReason                = strings(nTests,1);

for k = 1:nTests

    Icmd = testCurrents(k);

    CommandedCurrent_A(k) = Icmd;

    fprintf("       %6.1f A ... ",Icmd);

    try

        %% ----------------------------------------------------
        % Negative because the source discharges the pack
        %% ----------------------------------------------------

        set_param(currentSourcePath,"i0",num2str(-Icmd,17));

        tic;

        simOut = sim(modelName, ...
            "StopTime",num2str(simStopTime), ...
            "ReturnWorkspaceOutputs","on");

        SolverTime_s(k) = toc;

        %% ----------------------------------------------------
        % Extract logged signals
        %% ----------------------------------------------------

        t = simOut.tout;

        if isempty(t)
            error("Simulation returned no time vector.");
        end

        if any(~isfinite(t))
            error("Simulation time contains NaN or Inf.");
        end

        if t(end) < simStopTime*0.99
            error("Simulation stopped early at t = %.4f s.",t(end));
        end

        [Iseries,Vseries] = readSensors(simOut, ...
            currentSensorPath,voltageSensorPath);

        MeasuredCurrent_A(k) = abs(Iseries(end));
        FinalVoltage_V(k)    = Vseries(end);
        AverageVoltage_V(k)  = mean(Vseries);
        MinVoltage_V(k)      = min(Vseries);

        MeasuredCurrentError_percent(k) = ...
            100*(MeasuredCurrent_A(k) - Icmd)/Icmd;

        %% ----------------------------------------------------
        % Pass criteria
        %% ----------------------------------------------------

        currentOK = abs(MeasuredCurrentError_percent(k)) < 1.0;

        voltageOK = FinalVoltage_V(k) > Vmin && ...
                    FinalVoltage_V(k) < Vmax*1.05;

        if currentOK && voltageOK

            Result(k) = "PASS";
            fprintf("PASS  %7.2f V, %6.2f A\n", ...
                FinalVoltage_V(k),MeasuredCurrent_A(k));

        else

            Result(k) = "FAIL";

            reasons = strings(0,1);

            if ~currentOK
                reasons(end+1) = sprintf( ...
                    "current error %.2f%%", ...
                    MeasuredCurrentError_percent(k)); %#ok<SAGROW>
            end

            if ~voltageOK
                reasons(end+1) = sprintf( ...
                    "voltage %.2f V outside [%.1f, %.1f]", ...
                    FinalVoltage_V(k),Vmin,Vmax*1.05); %#ok<SAGROW>
            end

            FailureReason(k) = strjoin(reasons,"; ");

            fprintf("FAIL  %s\n",FailureReason(k));

        end

    catch ME

        Result(k)        = "ERROR";
        FailureReason(k) = string(ME.message);

        fprintf("ERROR %s\n",ME.message);

    end

end

%% ============================================================
% 8. RESULTS TABLE
%% ============================================================

fprintf("[6/6] Validating and saving ................... ");

Results = table( ...
    CommandedCurrent_A, ...
    MeasuredCurrent_A, ...
    MeasuredCurrentError_percent, ...
    FinalVoltage_V, ...
    AverageVoltage_V, ...
    MinVoltage_V, ...
    SolverTime_s, ...
    Result, ...
    FailureReason);

resultsFile = fullfile(outputDirectory,"TEST_Electrical_Results.mat");
resultsCSV  = fullfile(outputDirectory,"TEST_Electrical_Results.csv");

writetable(Results,resultsCSV);

save(resultsFile, ...
    "Results","Vnom","Vmax","Vmin","Capacity","Energy_kWh", ...
    "testCurrents");

save_system(modelName,modelFile);

fprintf("PASS\n");

%% ============================================================
% FINAL REPORT
%% ============================================================

fprintf("\n");
fprintf("============================================================\n");
fprintf("            ELECTRICAL TEST RESULTS\n");
fprintf("============================================================\n");

fprintf("\n%10s %10s %9s %10s %8s\n", ...
    "Cmd [A]","Meas [A]","Err [%]","Final [V]","Result");
fprintf("%s\n",repmat('-',1,52));

for k = 1:nTests

    fprintf("%10.1f %10.2f %9.3f %10.3f %8s\n", ...
        CommandedCurrent_A(k), ...
        MeasuredCurrent_A(k), ...
        MeasuredCurrentError_percent(k), ...
        FinalVoltage_V(k), ...
        Result(k));

end

nPass  = sum(Result == "PASS");
nFail  = sum(Result == "FAIL");
nError = sum(Result == "ERROR");

fprintf("\n%d of %d passed",nPass,nTests);

if nFail > 0
    fprintf(", %d failed",nFail);
end

if nError > 0
    fprintf(", %d errored",nError);
end

fprintf(".\n");

%% ------------------------------------------------------------
% Failure detail
%% ------------------------------------------------------------

if nFail > 0 || nError > 0

    fprintf("\nFailures:\n");

    for k = 1:nTests

        if Result(k) ~= "PASS"
            fprintf("  %.1f A : %s\n", ...
                CommandedCurrent_A(k),FailureReason(k));
        end

    end

end

fprintf("\nFiles saved:\n");
fprintf("  Model : %s\n",modelFile);
fprintf("  MAT   : %s\n",resultsFile);
fprintf("  CSV   : %s\n",resultsCSV);

fprintf("\n============================================================\n");

if nPass == nTests
    fprintf("            ELECTRICAL TEST PASSED\n");
else
    fprintf("            ELECTRICAL TEST INCOMPLETE\n");
end

fprintf("============================================================\n");

%% ============================================================
% LOCAL FUNCTIONS
%% ============================================================

function [I,V] = readSensors(simOut,currentSensorPath,voltageSensorPath)
%READSENSORS  Pull sensor outputs from the Simscape log.
%
%   Simscape logging records every variable in the physical
%   network, so the sensor readings are available without wiring
%   anything to a To Workspace block.
%
%   The log is a tree keyed by block name. Block names contain
%   spaces, which are legal in Simulink but not as MATLAB field
%   names, so the tree is walked by child name rather than by
%   dot-indexing.

    if ~isprop(simOut,"simlog") && ~isfield(simOut,"simlog")
        error("Simscape logging produced no 'simlog' output.");
    end

    simlog = simOut.simlog;

    [~,currentSensorName,~] = fileparts(currentSensorPath);
    [~,voltageSensorName,~] = fileparts(voltageSensorPath);

    Inode = findChild(simlog,currentSensorName);
    Vnode = findChild(simlog,voltageSensorName);

    I = Inode.I.series.values;
    V = Vnode.V.series.values;

    I = I(:);
    V = V(:);

    if isempty(I) || isempty(V)
        error("Sensor logs are empty.");
    end

end

function node = findChild(parent,name)
%FINDCHILD  Locate a named child in a Simscape log tree.

    ids = parent.childIds;

    for k = 1:numel(ids)

        if string(ids{k}) == string(name)
            node = parent.(ids{k});
            return;
        end

    end

    %% ---------------------------------------------------------
    % Simscape replaces spaces in block names with underscores
    % when forming log identifiers, so try that form too.
    %% ---------------------------------------------------------

    alt = replace(string(name)," ","_");

    for k = 1:numel(ids)

        if string(ids{k}) == alt
            node = parent.(ids{k});
            return;
        end

    end

    error("Could not find '%s' in the Simscape log. Available: %s", ...
        name,strjoin(string(ids),", "));

end

%% ============================================================
% P50B_BUILD.m
%
% Build the Simscape Battery objects and the generated library,
% plus the mechanical model, and save both.
%
% This is the pack-construction entry point. For the full
% analysis including drivetrain, thermal and mission, run
% P50B_26S21P_MASTER instead.
%% ============================================================

clear;
clc;
close all;

%% ============================================================
% PROJECT
%% ============================================================

run(fullfile(fileparts(fileparts(mfilename("fullpath"))),"00_setup.m"));

projectRoot = P50B_ProjectRoot();

outputDir = fullfile(projectRoot,"output");

if ~isfolder(outputDir)
    mkdir(outputDir);
end

%% ============================================================
% CELL
%% ============================================================

fprintf("\n[1/5] Cell\n");

data = P50B_CellData();

fprintf("  %s %s: %.1f Ah, %.1f V\n", ...
    data.Manufacturer,data.Model, ...
    data.Capacity_Ah,data.NominalVoltage_V);

%% ============================================================
% BATTERY OBJECTS
%% ============================================================

fprintf("\n[2/5] Battery objects\n");

P21 = P50B_21P(data);

fprintf("  21P parallel assembly built\n");

M13 = P50B_13S21P(P21);

fprintf("  13S21P module built\n");

pack = P50B_26S21P(M13);

fprintf("  26S21P pack built\n");

disp(pack);

%% ============================================================
% CHART
%% ============================================================

figure("Name","P50B 26S21P Battery Builder","Color","white");

batteryChart(pack);

title("Molicel P50B 26S21P");

%% ============================================================
% GENERATED SIMSCAPE LIBRARY
%% ============================================================

fprintf("\n[3/5] Simscape library\n");

try

    buildBattery( ...
        pack, ...
        LibraryName="P50B_26S21P", ...
        Directory=outputDir, ...
        MaskParameters="VariableNamesByType", ...
        MaskInitialTargets="VariableNamesByInstance", ...
        Verbose="on");

    fprintf("  Library written to output/\n");

catch ME

    fprintf("  Library build FAILED: %s\n",ME.message);

end

save(fullfile(outputDir,"P50B_26S21P.mat"), ...
    "data","P21","M13","pack");

%% ============================================================
% MECHANICAL MODEL
%
% P50B_GroupLayout now returns the cell coordinates as part of
% its output, so there is no separate call and no chance of the
% two disagreeing.
%% ============================================================

fprintf("\n[4/5] Mechanical model\n");

G = P50B_Geometry();

Layout = P50B_GroupLayout(G,"Plot",true,"Verbose",true);

Cells = Layout.Cells;

P50B_PlotCells(G,Cells);

%% ============================================================
% INTERCONNECT
%% ============================================================

fprintf("\n[5/5] Interconnect\n");

Bus = P50B_Busbars(G,Layout,"Plot",true,"Verbose",true);

%% ============================================================
% SAVE
%% ============================================================

save(fullfile(outputDir,"P50B_MechanicalGeometry.mat"), ...
    "G","Layout","Cells","Bus");

writetable(Cells, ...
    fullfile(outputDir,"P50B_546_CellCoordinates.csv"));

writetable(Layout.Groups, ...
    fullfile(outputDir,"P50B_26_GroupCoordinates.csv"));

writetable(Bus.SeriesLinks, ...
    fullfile(outputDir,"P50B_BusbarLinks.csv"));

fprintf("\n");
fprintf("=============================================\n");
fprintf(" BUILD COMPLETE\n");
fprintf("=============================================\n");
fprintf("  %d cells, %d groups\n",height(Cells),height(Layout.Groups));
fprintf("  Interconnect resistance: %.3f mOhm\n",Bus.Rtotal*1e3);
fprintf("  Files written to output/\n");
fprintf("=============================================\n\n");

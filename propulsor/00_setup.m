%% ============================================================
% 00_setup.m
%
% P50B 26S21P project setup.
%
% Creates the folder structure, adds everything to the MATLAB
% path, and checks that the required toolboxes are present.
%
% Run this once per MATLAB session before using the project,
% or just run P50B_26S21P_MASTER, which does it for you.
%% ============================================================

clc;
close all;

%% ============================================================
% PROJECT ROOT
%% ============================================================

projectRoot = fileparts(mfilename("fullpath"));

cd(projectRoot);

%% ============================================================
% FOLDER STRUCTURE
%% ============================================================

folders = { ...
    "00_common"      , "Shared utilities and provenance helpers"
    "01_cell"        , "Cell definition, OCV and DCIR"
    "02_pack"        , "Simscape Battery pack construction"
    "03_mechanical"  , "Geometry, layout and interconnect"
    "04_data"        , "Measured data and datasheets"
    "05_tests"       , "Test scripts"
    "06_drivetrain"  , "Motor, inverter, harness and loads"
    "07_simulation"  , "Mission profiles and simulation"
    "08_compliance"  , "Monaco rules, mass budget, export"
    "09_hydro"       , "Hull, propulsor, dynamics and gearbox"
    "docs"           , "Documentation"
    "output"         , "Generated results"};

fprintf("\n");
fprintf("================================================================\n");
fprintf(" P50B 26S21P PROJECT SETUP\n");
fprintf("================================================================\n");

fprintf("\nProject root:\n  %s\n",projectRoot);

fprintf("\nFolders:\n");

for k = 1:size(folders,1)

    folder = fullfile(projectRoot,folders{k,1});

    if ~isfolder(folder)
        mkdir(folder);
        status = "created";
    else
        status = "ok";
    end

    fprintf("  %-16s %-8s %s\n", ...
        folders{k,1},status,folders{k,2});

end

%% ============================================================
% PATH
%% ============================================================

addpath(genpath(projectRoot));

fprintf("\nProject folders added to the MATLAB path.\n");

%% ============================================================
% TOOLBOX CHECK
%
% Checked by function availability rather than by product name,
% because a product can be installed but not licensed, and it is
% the functions that actually matter.
%% ============================================================

fprintf("\nChecking the MATLAB environment:\n\n");

requiredProducts = { ...
    "Simulink"          , "simulink"
    "Simscape"          , "simscape"
    "Simscape Battery"  , "batteryCell"};

allPresent = true;

for k = 1:size(requiredProducts,1)

    name = requiredProducts{k,1};
    probe = requiredProducts{k,2};

    if isempty(which(probe))
        fprintf("  [MISSING] %s\n",name);
        allPresent = false;
    else
        fprintf("  [ok]      %s\n",name);
    end

end

%% ============================================================
% DATA FILES
%
% The project runs without these, using datasheet-anchored
% estimates. It runs better with them.
%% ============================================================

fprintf("\nMeasured data files:\n\n");

dataFiles = { ...
    "P50B_OCV_SOC.csv"    , "Measured OCV vs SOC"
    "P50B_DCIR_SOC_T.csv" , "Measured DCIR vs SOC and temperature"};

for k = 1:size(dataFiles,1)

    f = fullfile(projectRoot,"04_data",dataFiles{k,1});

    if isfile(f)
        fprintf("  [present] %-24s %s\n",dataFiles{k,1},dataFiles{k,2});
    else
        fprintf("  [absent]  %-24s %s\n",dataFiles{k,1},dataFiles{k,2});
    end

end

fprintf("\n  Absent files fall back to datasheet-anchored estimates.\n");
fprintf("  See docs/DATA_PROVENANCE.md for the format to supply.\n");

%% ============================================================
% READY
%% ============================================================

fprintf("\n");
fprintf("================================================================\n");

if allPresent
    fprintf(" Environment ready.\n");
else
    fprintf(" Environment INCOMPLETE -- some products are missing.\n");
end

fprintf("\n Next steps:\n");
fprintf("   TEST_ALL              run the regression test\n");
fprintf("   P50B_26S21P_MASTER    build and analyse everything\n");
fprintf("   P50B_ProvenanceReport audit every model parameter\n");
fprintf("================================================================\n\n");

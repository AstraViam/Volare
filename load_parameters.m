%% ============================================================
% load_parameters.m
%
% Quick reference: pack load conditions across the operating
% range, from the competition power cap to the outboard's peak.
%
% This is a printout, not a model. For the real analysis use
% P50B_DrivetrainModel, which accounts for every loss between
% the cells and the propeller.
%
% What this script tells you that the previous version did not:
% the 25 kW competition cap is nowhere near the limiting case.
% The Competr outboard is rated to draw 375 A continuously and
% up to 449 A at peak power, and the pack, busbars and harness
% all have to survive that.
%% ============================================================

data  = P50B_CellData();
motor = P50B_MotorData();

Ns = 26;
Np = 21;

Vnom = Ns * data.NominalVoltage_V;
Vmax = Ns * data.MaxVoltage_V;
Vmin = Ns * data.MinVoltage_V;

Capacity_Ah = Np * data.Capacity_Ah;

Energy_kWh = Vnom * Capacity_Ah / 1000;

%% ============================================================
% LOAD CASES
%% ============================================================

Case = [ ...
    "100 A reference"
    "Monaco 25 kW cap"
    "Competr continuous"
    "Competr 42 kW peak"
    "Competr peak at Vmin"];

Current_A = [ ...
    100
    25e3/Vnom
    motor.BusMaximumCurrent_A
    motor.MaximumPower_W/Vnom
    motor.MaximumPower_W/Vmin];

nCases = numel(Case);

CellCurrent_A = Current_A / Np;

CRate = CellCurrent_A / data.Capacity_Ah;

Power_kW = Current_A * Vnom / 1000;

CellUtilisation = CellCurrent_A / data.MaxContinuousCurrent_A;

%% ============================================================
% PRINT
%% ============================================================

fprintf("\n");
fprintf("================================================================\n");
fprintf(" P50B 26S21P PACK LOAD CONDITIONS\n");
fprintf("================================================================\n");

fprintf("\nPACK\n");
fprintf("  Configuration        : %dS%dP, %d cells\n",Ns,Np,Ns*Np);
fprintf("  Nominal voltage      : %.2f V\n",Vnom);
fprintf("  Voltage range        : %.2f to %.2f V\n",Vmin,Vmax);
fprintf("  Capacity             : %.2f Ah\n",Capacity_Ah);
fprintf("  Nominal energy       : %.3f kWh\n",Energy_kWh);

fprintf("\nCELL\n");
fprintf("  %s %s\n",data.Manufacturer,data.Model);
fprintf("  Capacity             : %.1f Ah\n",data.Capacity_Ah);
fprintf("  Continuous rating    : %.0f A (%.0f C)\n", ...
    data.MaxContinuousCurrent_A, ...
    data.MaxContinuousCurrent_A/data.Capacity_Ah);

fprintf("\nLOAD CASES\n\n");

fprintf("  %-22s %9s %9s %9s %8s %8s\n", ...
    "Case","Pack [A]","Cell [A]","Power[kW]","C-rate","Cell use");
fprintf("  %s\n",repmat('-',1,70));

for k = 1:nCases

    fprintf("  %-22s %9.1f %9.2f %9.1f %8.2f %7.0f%%\n", ...
        Case(k), ...
        Current_A(k), ...
        CellCurrent_A(k), ...
        Power_kW(k), ...
        CRate(k), ...
        CellUtilisation(k)*100);

end

%% ============================================================
% RUNTIME AT EACH LOAD
%
% Ideal coulombic runtime from a full pack down to the 10%
% usable floor, ignoring losses. Real endurance is shorter --
% run P50B_RunMission for that.
%% ============================================================

usableFraction = 0.85;      % 95% down to 10%

Runtime_min = usableFraction * Capacity_Ah ./ Current_A * 60;

fprintf("\nIDEAL RUNTIME (95%% to 10%% SOC, losses ignored)\n\n");

for k = 1:nCases

    fprintf("  %-22s %6.1f min\n",Case(k),Runtime_min(k));

end

fprintf("\n  These are coulombic upper bounds. P50B_RunMission\n");
fprintf("  accounts for drivetrain losses and gives shorter,\n");
fprintf("  realistic figures.\n");

%% ============================================================
% HEADROOM
%% ============================================================

packCapability_A = Np * data.MaxContinuousCurrent_A;

fprintf("\nHEADROOM\n");
fprintf("  Pack current capability : %.0f A (21 cells x %.0f A)\n", ...
    packCapability_A,data.MaxContinuousCurrent_A);
fprintf("  Outboard continuous     : %.0f A\n", ...
    motor.BusMaximumCurrent_A);
fprintf("  Margin                  : %.1fx\n", ...
    packCapability_A/motor.BusMaximumCurrent_A);

fprintf("\n  The cells are not the constraint. Energy is: %.2f kWh\n", ...
    Energy_kWh);
fprintf("  against a Competr stock pack of 26 kWh.\n");

fprintf("\n================================================================\n\n");

%% ============================================================
% EXPORT FOR OTHER SCRIPTS
%% ============================================================

LoadCases = table(Case,Current_A,CellCurrent_A,Power_kW,CRate, ...
    CellUtilisation,Runtime_min);

%% ------------------------------------------------------------
% Legacy variable names
%% ------------------------------------------------------------

I_100A         = 100;
I_25kW_nominal = 25e3/Vnom;
P1             = 100*Vnom;
P2             = 25e3;

%% ============================================================
% Test_BusbarSizing.m
%
% Series busbar sizing study.
%
% Sweeps busbar width and thickness against the real operating
% currents of the Competr drivetrain and reports which
% combinations satisfy both the loss budget and the current
% density limit.
%
% WHAT CHANGED FROM THE PREVIOUS VERSION
% --------------------------------------
% The previous version swept a grid, computed I-squared-R at a
% single 267 A operating point using a placeholder 0.15 m link
% length, and plotted the result. It never said which geometry
% was acceptable, and it never checked current density -- which
% is the constraint that actually rules options out.
%
% It also used the Monaco 25 kW figure alone. The outboard is
% rated to 375 A continuous, so sizing against 267 A leaves the
% busbars undersized for the hardware they are connected to.
%
% This version uses the real link lengths from the layout,
% evaluates every operating point, and reports a recommendation.
%% ============================================================

clear;
clc;
close all;

fprintf("\n");
fprintf("================================================================\n");
fprintf(" SERIES BUSBAR SIZING STUDY\n");
fprintf("================================================================\n");

%% ============================================================
% BUILD THE REAL GEOMETRY
%% ============================================================

G      = P50B_Geometry();
Layout = P50B_GroupLayout(G,"Plot",false,"Verbose",false);
motor  = P50B_MotorData();

%% ------------------------------------------------------------
% Actual series link lengths, not a placeholder
%% ------------------------------------------------------------

Bus = P50B_Busbars(G,Layout,"Plot",false,"Verbose",false);

linkLengths = Bus.SeriesLinks.LinkLength;

totalLength = sum(linkLengths);

fprintf("\nGEOMETRY FROM THE LAYOUT\n");
fprintf("  Series links            : %d\n",numel(linkLengths));
fprintf("  Shortest link           : %.1f mm\n",min(linkLengths)*1e3);
fprintf("  Longest link            : %.1f mm\n",max(linkLengths)*1e3);
fprintf("  Mean link               : %.1f mm\n",mean(linkLengths)*1e3);
fprintf("  Total conductor length  : %.3f m\n",totalLength);

%% ============================================================
% OPERATING CURRENTS
%% ============================================================

Vnom = 26*3.6;
Vmin = 26*2.5;

opNames = [ ...
    "Monaco 25 kW cap"
    "Competr continuous"
    "Competr peak at Vmin"];

opCurrents = [ ...
    25e3/Vnom
    motor.BusMaximumCurrent_A
    motor.MaximumPower_W/Vmin];

fprintf("\nOPERATING CURRENTS\n");

for k = 1:numel(opNames)
    fprintf("  %-24s %.1f A\n",opNames(k),opCurrents(k));
end

%% ============================================================
% MATERIAL
%% ============================================================

rho20 = 1.724e-8;
alpha = 3.93e-3;
Tbus  = 60;

rho = rho20 * (1 + alpha*(Tbus-20));

fprintf("\nMATERIAL\n");
fprintf("  Copper at %.0f degC       : %.4g Ohm*m\n",Tbus,rho);

%% ============================================================
% DESIGN CRITERIA
%% ============================================================

maxDensity_A_mm2 = 5.0;

maxTotalLoss_W = 50;

maxVoltageDrop_V = 1.5;

fprintf("\nDESIGN CRITERIA (at the continuous rating)\n");
fprintf("  Max current density     : %.1f A/mm^2\n",maxDensity_A_mm2);
fprintf("  Max total link loss     : %.0f W\n",maxTotalLoss_W);
fprintf("  Max total voltage drop  : %.2f V\n",maxVoltageDrop_V);

%% ============================================================
% SWEEP
%% ============================================================

widths_mm     = [10 15 20 25 30 40 50];
thicknesses_mm = [1 1.5 2 2.5 3 4];

sizingCurrent = motor.BusMaximumCurrent_A;

nW = numel(widths_mm);
nT = numel(thicknesses_mm);

rows = nW*nT;

Width_mm       = zeros(rows,1);
Thickness_mm   = zeros(rows,1);
Area_mm2       = zeros(rows,1);
Resistance_mOhm = zeros(rows,1);
Loss_W         = zeros(rows,1);
VoltageDrop_V  = zeros(rows,1);
Density_A_mm2  = zeros(rows,1);
CopperMass_kg  = zeros(rows,1);
DensityOK      = false(rows,1);
LossOK         = false(rows,1);
DropOK         = false(rows,1);
Acceptable     = false(rows,1);

copperDensity = 8960;

i = 1;

for w = widths_mm

    for t = thicknesses_mm

        A = w*1e-3 * t*1e-3;

        R = rho * totalLength / A;

        Width_mm(i)     = w;
        Thickness_mm(i) = t;
        Area_mm2(i)     = w*t;

        Resistance_mOhm(i) = R*1e3;

        Loss_W(i) = sizingCurrent^2 * R;

        VoltageDrop_V(i) = sizingCurrent * R;

        Density_A_mm2(i) = sizingCurrent / (w*t);

        CopperMass_kg(i) = totalLength * A * copperDensity;

        DensityOK(i) = Density_A_mm2(i) <= maxDensity_A_mm2;
        LossOK(i)    = Loss_W(i) <= maxTotalLoss_W;
        DropOK(i)    = VoltageDrop_V(i) <= maxVoltageDrop_V;

        Acceptable(i) = DensityOK(i) && LossOK(i) && DropOK(i);

        i = i + 1;

    end

end

T = table( ...
    Width_mm,Thickness_mm,Area_mm2, ...
    Resistance_mOhm,Loss_W,VoltageDrop_V,Density_A_mm2, ...
    CopperMass_kg,DensityOK,LossOK,DropOK,Acceptable);

%% ============================================================
% CURRENT GEOMETRY
%% ============================================================

currentW = G.Busbar.SeriesLinkWidth*1e3;
currentT = G.Busbar.SeriesLinkThickness*1e3;

idxCurrent = find(T.Width_mm == currentW & ...
                  T.Thickness_mm == currentT,1);

fprintf("\n");
fprintf("================================================================\n");
fprintf(" CURRENT DESIGN: %.0f x %.1f mm\n",currentW,currentT);
fprintf("================================================================\n");

if ~isempty(idxCurrent)

    r = T(idxCurrent,:);

    fprintf("\n  Cross-section           : %.1f mm^2\n",r.Area_mm2);
    fprintf("  Total link resistance   : %.3f mOhm\n",r.Resistance_mOhm);
    fprintf("  Copper mass             : %.3f kg\n",r.CopperMass_kg);

    fprintf("\n  At %.0f A continuous:\n",sizingCurrent);
    fprintf("    Loss                  : %.1f W   %s\n", ...
        r.Loss_W, passFail(r.LossOK));
    fprintf("    Voltage drop          : %.3f V   %s\n", ...
        r.VoltageDrop_V, passFail(r.DropOK));
    fprintf("    Current density       : %.2f A/mm^2  %s\n", ...
        r.Density_A_mm2, passFail(r.DensityOK));

    if ~r.Acceptable
        fprintf("\n  The current geometry does NOT meet all criteria\n");
        fprintf("  at the outboard's continuous rating.\n");
    else
        fprintf("\n  The current geometry meets all criteria.\n");
    end

end

%% ============================================================
% ACCEPTABLE OPTIONS, LIGHTEST FIRST
%% ============================================================

Acc = T(T.Acceptable,:);

Acc = sortrows(Acc,"CopperMass_kg","ascend");

fprintf("\n");
fprintf("================================================================\n");
fprintf(" ACCEPTABLE GEOMETRIES, LIGHTEST FIRST\n");
fprintf("================================================================\n");

if isempty(Acc)

    fprintf("\n  None of the swept geometries meet all three criteria.\n");
    fprintf("  Relax a criterion or widen the sweep.\n");

else

    fprintf("\n  %8s %10s %8s %9s %8s %9s %8s\n", ...
        "W [mm]","t [mm]","A[mm2]","R[mOhm]","Loss[W]","dV[V]","Cu[kg]");
    fprintf("  %s\n",repmat('-',1,68));

    nShow = min(10,height(Acc));

    for k = 1:nShow

        fprintf("  %8.0f %10.1f %8.1f %9.3f %8.1f %9.3f %8.3f\n", ...
            Acc.Width_mm(k), ...
            Acc.Thickness_mm(k), ...
            Acc.Area_mm2(k), ...
            Acc.Resistance_mOhm(k), ...
            Acc.Loss_W(k), ...
            Acc.VoltageDrop_V(k), ...
            Acc.CopperMass_kg(k));

    end

    fprintf("\n  RECOMMENDATION: %.0f x %.1f mm\n", ...
        Acc.Width_mm(1),Acc.Thickness_mm(1));
    fprintf("  Lightest geometry meeting loss, drop and density limits.\n");

end

%% ============================================================
% SENSITIVITY TO OPERATING POINT
%% ============================================================

fprintf("\n");
fprintf("================================================================\n");
fprintf(" WHY SIZING AGAINST 25 kW ALONE IS NOT ENOUGH\n");
fprintf("================================================================\n");

fprintf("\n  %-24s %10s %10s %12s\n", ...
    "Operating point","I [A]","Loss [W]","Density");
fprintf("  %s\n",repmat('-',1,60));

if ~isempty(idxCurrent)

    Acurrent = currentW*currentT;

    Rcurrent = rho*totalLength/(Acurrent*1e-6);

    for k = 1:numel(opNames)

        I = opCurrents(k);

        d = I/Acurrent;

        if d <= maxDensity_A_mm2
            flag = "ok";
        else
            flag = "TOO HIGH";
        end

        fprintf("  %-24s %10.1f %10.1f %7.2f %s\n", ...
            opNames(k),I,I^2*Rcurrent,d,flag);

    end

end

fprintf("\n  Sizing at the 25 kW cap alone would pass a geometry\n");
fprintf("  that is overloaded whenever the outboard draws its\n");
fprintf("  rated current.\n");

%% ============================================================
% PLOTS
%% ============================================================

figure("Name","Busbar Sizing","Color","white");

%% ------------------------------------------------------------
% Loss vs area
%% ------------------------------------------------------------

subplot(1,2,1);

hold on; grid on;

scatter(T.Area_mm2(T.Acceptable),T.Loss_W(T.Acceptable), ...
    40,"filled");

scatter(T.Area_mm2(~T.Acceptable),T.Loss_W(~T.Acceptable), ...
    30,"x");

yline(maxTotalLoss_W,"--",sprintf("Loss budget %.0f W",maxTotalLoss_W));

xlabel("Cross-sectional area [mm^2]");
ylabel("Total series link loss [W]");
title(sprintf("Loss at %.0f A",sizingCurrent));

legend("Acceptable","Rejected","Location","northeast");

%% ------------------------------------------------------------
% Density vs area
%% ------------------------------------------------------------

subplot(1,2,2);

hold on; grid on;

scatter(T.Area_mm2,T.Density_A_mm2,40,"filled");

yline(maxDensity_A_mm2,"--", ...
    sprintf("Limit %.1f A/mm^2",maxDensity_A_mm2));

if ~isempty(idxCurrent)

    plot(T.Area_mm2(idxCurrent),T.Density_A_mm2(idxCurrent), ...
        "o","MarkerSize",14,"LineWidth",2);

    text(T.Area_mm2(idxCurrent),T.Density_A_mm2(idxCurrent), ...
        "  current design","VerticalAlignment","bottom");

end

xlabel("Cross-sectional area [mm^2]");
ylabel("Current density [A/mm^2]");
title(sprintf("Current density at %.0f A",sizingCurrent));

%% ============================================================
% SAVE
%% ============================================================

outputDir = fullfile(P50B_ProjectRoot(),"output");

if ~isfolder(outputDir)
    mkdir(outputDir);
end

writetable(T,fullfile(outputDir,"TEST_BusbarSizing.csv"));

fprintf("\n  Full sweep written to output/TEST_BusbarSizing.csv\n");
fprintf("\n================================================================\n\n");

%% ============================================================
% LOCAL FUNCTIONS
%% ============================================================

function s = passFail(ok)

    if ok
        s = "ok";
    else
        s = "EXCEEDS LIMIT";
    end

end

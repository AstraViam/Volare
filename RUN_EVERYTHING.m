%% ============================================================
% RUN_EVERYTHING
%
% Every MATLAB entry point in the project, in dependency order,
% with a summary at the end.
%
% This exists because "does the project work" was previously
% answered by running five things by hand and remembering what
% each was supposed to print. Runtime is a few minutes; use
% SMOKE_TEST during development and this before a review.
%% ============================================================

clear; clc;

addpath(genpath(fileparts(mfilename("fullpath"))));

fprintf("\n");
fprintf("################################################################\n");
fprintf("#  VOLARE  --  FULL SYSTEM RUN                                 #\n");
fprintf("#  %s                                        #\n", ...
    string(datetime("now","Format","yyyy-MM-dd HH:mm")));
fprintf("################################################################\n");

S = struct();

%% ---- 1. smoke ------------------------------------------------
fprintf("\n>>> [1/8] SMOKE_TEST\n");
evalc("[S.SmokeOK,S.Smoke] = SMOKE_TEST(""Verbose"",false);");
fprintf("    %d checks, %d failed\n", ...
    height(S.Smoke),sum(S.Smoke.Status=="FAIL"));

%% ---- 2. architecture -----------------------------------------
fprintf("\n>>> [2/8] ARCHITECTURE AUDIT\n");
evalc("S.Arch = P50B_ArchitectureAudit(""Verbose"",false,""Export"",true);");
fprintf("    %d parameters, %.0f%% bound, %d suspect literals\n", ...
    S.Arch.File.Parameters,S.Arch.BindingTotals.BoundPct, ...
    S.Arch.BindingTotals.Suspect);

%% ---- 3. motor spec -------------------------------------------
fprintf("\n>>> [3/8] MOTOR SPECIFICATION AUDIT\n");
evalc("S.Motor = P50B_MotorSpecAudit(""Verbose"",false);");
fprintf("    %d finding(s); propulsor needs %.0f rpm, fits both limits: %d\n", ...
    numel(S.Motor.Findings),S.Motor.PropulsorMotorSpeed_rpm, ...
    S.Motor.PropulsorFitsBothSpeeds);

%% ---- 4. boat performance -------------------------------------
fprintf("\n>>> [4/8] BOAT PERFORMANCE\n");
evalc("S.Perf = P50B_BoatPerformance(""Verbose"",false);");
fprintf("    top %.1f km/h, ceiling %.2f kW, REQ_37 %d, REQ_32 %d\n", ...
    S.Perf.TopSpeed_kmh,S.Perf.ShaftPowerCeiling_W/1000, ...
    S.Perf.MinimumSpeed.Achievable,S.Perf.Reverse.Achievable);

%% ---- 5. gearbox study ----------------------------------------
fprintf("\n>>> [5/8] GEARBOX STUDY\n");
evalc("S.Gear = P50B_GearboxStudy(""Ratios"",[1.4 1.6079 1.8 2.0 2.2 2.4 2.8],""Verbose"",false);");
if ~isempty(S.Gear.Knee)
    fprintf("    fitted %.4f:1 -> knee %.2f:1, %+.1f km/h (%+.1f%%)\n", ...
        S.Gear.Fitted.GearRatio,S.Gear.Knee.GearRatio, ...
        S.Gear.Gain_kmh,S.Gear.Gain_pct);
end

%% ---- 6. mass budget ------------------------------------------
fprintf("\n>>> [6/8] MASS BUDGET\n");
evalc("S.Mass = P50B_MassBudget(""Verbose"",false);");
fprintf("    %.1f of %.0f kg, %.1f kg margin (%.1f%%)\n", ...
    S.Mass.ExcludingHulls_kg,S.Mass.Limit_kg, ...
    S.Mass.Margin_kg,S.Mass.MarginPercent);

%% ---- 7. compliance -------------------------------------------
fprintf("\n>>> [7/8] MONACO COMPLIANCE\n");
evalc("S.Comp = P50B_MonacoCompliance(""Verbose"",false,""Performance"",S.Perf,""MassBudget"",S.Mass);");
evalc("P50B_ExportCompliance(""Compliance"",S.Comp,""Verbose"",false);");
fprintf("    %d checks: %d pass, %d fail, %d action, %d checklist\n", ...
    S.Comp.NumChecks,S.Comp.NumPass,S.Comp.NumFail, ...
    S.Comp.NumAction,S.Comp.NumChecklist);

%% ---- 8. mission ----------------------------------------------
fprintf("\n>>> [8/8] ENDURANCE MISSION\n");
evalc("S.Mission = P50B_RunMission(""endurance"",""Verbose"",false,""Plot"",false);");
fprintf("    %.0f s, SOC %.3f->%.3f, peak %.1f C, balance %.2e%%\n", ...
    S.Mission.Summary.Duration_s,S.Mission.SOC(1),S.Mission.SOC(end), ...
    S.Mission.Summary.PeakCellTemp_C,S.Mission.Energy.BalanceErrorPercent);

%% ============================================================
% SUMMARY
%% ============================================================

fprintf("\n");
fprintf("################################################################\n");
fprintf("#  RESULTS                                                     #\n");
fprintf("################################################################\n\n");

E = S.Comp.Energy;

fprintf("  RULES THAT DECIDE WHETHER THE BOAT RACES\n");
fprintf("    ENERGY_REQ_7   stored energy   %7.0f Wh of %5.0f  (%.2f%% margin)\n", ...
    E.StoredEnergy_Wh,E.Limit_Wh,E.MarginPercent);
fprintf("    ENERGY_REQ_48  weight          %7.1f kg of %5.0f  (%.2f%% margin)\n", ...
    S.Mass.ExcludingHulls_kg,S.Mass.Limit_kg,S.Mass.MarginPercent);
fprintf("    ENERGY_REQ_188 shaft ceiling   %7.2f kW from a %.0f kW electrical cap\n", ...
    S.Perf.ShaftPowerCeiling_W/1000, ...
    S.Perf.PowerCeiling.ElectricalLimit_W/1000);
fprintf("    ENERGY_REQ_37  three knots     %7.0f W  (%.1f%% of the ceiling)\n", ...
    S.Perf.MinimumSpeed.ShaftPower_W,100*S.Perf.MinimumSpeed.FractionOfCeiling);
fprintf("    ENERGY_REQ_32  reverse         %7.0f N astern vs %.0f N\n", ...
    S.Perf.Reverse.ThrustAstern_N,S.Perf.Reverse.Resistance_N);

fprintf("\n  PERFORMANCE\n");
fprintf("    Top speed                      %7.1f km/h (%.1f knots)\n", ...
    S.Perf.TopSpeed_kmh,S.Perf.TopSpeed_knots);
if S.Perf.MotorTorqueOK
    limitedBy = "power";
else
    limitedBy = "torque";
end
fprintf("    Limited by                     %7s\n",limitedBy);
fprintf("    Motor at top speed             %7.0f rpm, %.1f Nm\n", ...
    S.Perf.TopSpeedMotorRPM,S.Perf.MotorTorqueAtTop_Nm);
if ~isempty(S.Perf.BestRange)
    fprintf("    Furthest                       %7.1f km at %.0f km/h\n", ...
        S.Perf.BestRange.Range_km,S.Perf.BestRange.Speed_kmh);
end

fprintf("\n  ARCHITECTURE\n");
fprintf("    Parameters                     %7d in %d sections\n", ...
    S.Arch.File.Parameters,S.Arch.File.Sections);
fprintf("    Traceable to a measurement     %7.0f%%\n",S.Arch.Trust.TraceablePct);
fprintf("    Resting on assumption          %7.0f%%\n",S.Arch.Trust.AssumedPct);
fprintf("    Bound to the file              %7.0f%%  (%d suspect literals)\n", ...
    S.Arch.BindingTotals.BoundPct,S.Arch.BindingTotals.Suspect);
fprintf("    Compliance evaluated           %7.0f%%  of %d checks\n", ...
    S.Arch.Compliance.EvaluatedPct,S.Arch.Compliance.Checks);
fprintf("    Cross-check coverage           %7d quantities\n", ...
    S.Arch.CrossCheck.Quantities);

fprintf("\n  OPEN\n");
if ~isempty(S.Gear.Knee)
    fprintf("    Gearbox at %.2f:1 rather than %.4f:1 is worth %+.1f km/h\n", ...
        S.Gear.Knee.GearRatio,S.Gear.Fitted.GearRatio,S.Gear.Gain_kmh);
end
fprintf("    %d motor specification finding(s) -- ask Competr\n", ...
    numel(S.Motor.Findings));
fprintf("    %d compliance item(s) to action before scrutineering\n", ...
    S.Comp.NumAction);
fprintf("    %d item(s) deferred to physical inspection\n",S.Comp.NumChecklist);

allOK = S.SmokeOK && S.Comp.NumFail == 0 && S.Mass.Pass && ...
        S.Perf.MinimumSpeed.Achievable && S.Perf.Reverse.Achievable && ...
        S.Mission.Energy.BalanceOK;

fprintf("\n################################################################\n");
if allOK
    fprintf("#  ALL SYSTEMS PASS                                            #\n");
else
    fprintf("#  SOMETHING FAILED -- read above                              #\n");
end
fprintf("################################################################\n\n");

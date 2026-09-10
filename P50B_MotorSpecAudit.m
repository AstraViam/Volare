function Audit = P50B_MotorSpecAudit(varargin)
%P50B_MOTORSPECAUDIT  Check the Competr motor specification against itself.
%
%   Audit = P50B_MotorSpecAudit() tests whether the quoted powers,
%   torque and speeds can all be true at once, and reports which
%   combinations are impossible.
%
%   OPTIONS
%     "Motor"     struct from P50B_MotorData
%     "Verbose"   logical, default true
%
%   WHY THIS EXISTS
%   ---------------
%   Power, torque and speed are not three independent specifications.
%   They are two specifications and a consequence:
%
%       P = 2 pi n Q
%
%   A datasheet that quotes all three has made a claim that can be
%   checked, and this one does not survive the check.
%
%   The Competr datasheet gives 26.9 kW nominal, 42 kW maximum and
%   100 N.m maximum torque, and states NO SPEED ANYWHERE. Two different
%   speeds are in circulation for it -- 4000 rev/min, back-solved in
%   this project from the 42 kW figure, and 2500 rev/min from the
%   hydrodynamics team's brief, which also gives 1300 rev/min nominal.
%
%   The hydrodynamics team's tool found the same thing independently
%   and reported it at the top of every run. Two models reaching the
%   same conclusion from opposite ends of the drivetrain is worth more
%   than either reaching it alone, so it is recorded here rather than
%   left in one team's report.
%
%   WHY IT MATTERS BEYOND TIDINESS
%   ------------------------------
%   The maximum speed sets the gearbox ratio, the gearbox ratio sets
%   the propeller, and the propeller sets the boat speed. With the
%   single-screw stand-in and a 2.0 ratio the model wanted 6765 rev/min
%   at the motor, which is impossible under either figure. The
%   contra-rotating propulsor the boat actually has needs 1712 rev/min,
%   which is comfortable under both. The specification question stopped
%   being urgent when the real propulsor arrived -- but it is still
%   open, and it will matter again the moment anyone reconsiders the
%   gearbox.
%
%   ENERGY_REQ_188 is unaffected either way. The rule caps electrical
%   input at 25 kW and the model enforces that by bisection regardless
%   of what speed the machine can reach.
%
%   See also P50B_MotorData, P50B_ShaftPowerCeiling, P50B_Verification.

    opts = struct("Motor",[],"Verbose",true);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_MotorSpecAudit:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if isempty(opts.Motor)
        motor = P50B_MotorData();
    else
        motor = opts.Motor;
    end

    P = P50B_LoadParams("Plain",true);

    %% =========================================================
    % THE QUOTED NUMBERS
    %% =========================================================

    Pnom_W  = P50B_Value(motor.NominalPower_W);
    Pmax_W  = P50B_Value(motor.MaximumPower_W);
    Qmax_Nm = P50B_Value(motor.MaximumTorque_Nm);

    nMax_used  = P.motor.max_speed_rpm;
    nMax_brief = P.motor.max_speed_rpm_brief;
    nNom_brief = P.motor.nominal_speed_rpm_brief;

    ruleLimit_W = P.rules.motor_power_limit_W;

    %% =========================================================
    % WHAT EACH SPEED CAN ACTUALLY DELIVER AT FULL TORQUE
    %% =========================================================

    ceilingAt = @(rpm) 2*pi*(rpm/60)*Qmax_Nm;

    speedFor  = @(W)   W / (2*pi*Qmax_Nm) * 60;

    A = struct();

    A.NominalPower_W    = Pnom_W;
    A.MaximumPower_W    = Pmax_W;
    A.MaximumTorque_Nm  = Qmax_Nm;
    A.RuleLimit_W       = ruleLimit_W;

    A.SpeedUsed_rpm     = nMax_used;
    A.SpeedBrief_rpm    = nMax_brief;
    A.NominalSpeedBrief_rpm = nNom_brief;

    A.CeilingAtUsed_W   = ceilingAt(nMax_used);
    A.CeilingAtBrief_W  = ceilingAt(nMax_brief);
    A.CeilingAtNominal_W = ceilingAt(nNom_brief);

    A.SpeedForNominal_rpm = speedFor(Pnom_W);
    A.SpeedForMaximum_rpm = speedFor(Pmax_W);
    A.SpeedForRuleLimit_rpm = speedFor(ruleLimit_W);

    %% =========================================================
    % THE FINDINGS
    %% =========================================================

    findings = strings(0,1);

    if A.CeilingAtBrief_W < Pmax_W
        findings(end+1) = sprintf( ...
            "At the brief's %.0f rpm and %.0f N.m the ceiling is " + ...
            "%.2f kW, so the datasheet's %.1f kW maximum is " + ...
            "UNREACHABLE. It would need %.0f rpm.", ...
            nMax_brief,Qmax_Nm,A.CeilingAtBrief_W/1000, ...
            Pmax_W/1000,A.SpeedForMaximum_rpm);
    end

    if A.CeilingAtBrief_W < Pnom_W
        findings(end+1) = sprintf( ...
            "At the brief's %.0f rpm the ceiling is %.2f kW, below " + ...
            "the %.1f kW NOMINAL rating. The machine could not make " + ...
            "its own continuous rating.", ...
            nMax_brief,A.CeilingAtBrief_W/1000,Pnom_W/1000);
    end

    if A.CeilingAtNominal_W < ruleLimit_W
        findings(end+1) = sprintf( ...
            "At the brief's %.0f rpm nominal speed the ceiling is " + ...
            "%.2f kW, so even the %.0f kW the rules allow cannot be " + ...
            "produced there. That needs %.0f rpm.", ...
            nNom_brief,A.CeilingAtNominal_W/1000,ruleLimit_W/1000, ...
            A.SpeedForRuleLimit_rpm);
    end

    if abs(nMax_used - nMax_brief) > 1
        findings(end+1) = sprintf( ...
            "Two maximum speeds are in circulation: %.0f rpm (this " + ...
            "model, back-solved from the %.0f kW peak) and %.0f rpm " + ...
            "(the hydrodynamics brief). The datasheet states neither.", ...
            nMax_used,Pmax_W/1000,nMax_brief);
    end

    A.Findings = findings;
    A.Consistent = isempty(findings);

    %% ---------------------------------------------------------
    % Is the drivetrain we actually have affected?
    %% ---------------------------------------------------------

    A.PropulsorMotorSpeed_rpm = ...
        P.hydro.front_rpm * P.hydro.front_gear_ratio;

    A.PropulsorFitsBothSpeeds = ...
        A.PropulsorMotorSpeed_rpm <= min(nMax_used,nMax_brief);

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose

        fprintf("\n");
        fprintf("================================================================\n");
        fprintf(" MOTOR SPECIFICATION AUDIT\n");
        fprintf("================================================================\n");

        fprintf("\nQuoted: %.1f kW nominal, %.0f kW maximum, %.0f N.m.\n", ...
            Pnom_W/1000,Pmax_W/1000,Qmax_Nm);
        fprintf("The datasheet in 04_data/ states no motor speed at all.\n");

        fprintf("\nP = 2 pi n Q gives:\n");
        fprintf("  at %4.0f rpm and %.0f N.m : %6.2f kW\n", ...
            nMax_used,Qmax_Nm,A.CeilingAtUsed_W/1000);
        fprintf("  at %4.0f rpm and %.0f N.m : %6.2f kW\n", ...
            nMax_brief,Qmax_Nm,A.CeilingAtBrief_W/1000);
        fprintf("  at %4.0f rpm and %.0f N.m : %6.2f kW\n", ...
            nNom_brief,Qmax_Nm,A.CeilingAtNominal_W/1000);
        fprintf("  %.1f kW at %.0f N.m needs %.0f rpm\n", ...
            Pnom_W/1000,Qmax_Nm,A.SpeedForNominal_rpm);
        fprintf("  %.0f kW at %.0f N.m needs %.0f rpm\n", ...
            Pmax_W/1000,Qmax_Nm,A.SpeedForMaximum_rpm);
        fprintf("  %.0f kW at %.0f N.m needs %.0f rpm  (the rule limit)\n", ...
            ruleLimit_W/1000,Qmax_Nm,A.SpeedForRuleLimit_rpm);

        if A.Consistent

            fprintf("\nNo inconsistency found.\n");

        else

            fprintf("\n%d FINDING(S):\n",numel(findings));

            for k = 1:numel(findings)
                fprintf("\n  %d. %s\n",k,wrapText(findings(k),66,"     "));
            end

        end

        fprintf("\nDOES IT MATTER FOR THIS BOAT?\n");
        fprintf("  The contra-rotating propulsor needs %.0f rpm at the " + ...
            "motor.\n",A.PropulsorMotorSpeed_rpm);

        if A.PropulsorFitsBothSpeeds
            fprintf("  That is inside BOTH figures, so the drivetrain as " + ...
                "designed is\n");
            fprintf("  feasible either way and the open question is not " + ...
                "blocking.\n");
        else
            fprintf("  That is OUTSIDE at least one figure. The " + ...
                "specification must be\n");
            fprintf("  settled before the gearbox is ordered.\n");
        end

        fprintf("\n  ENERGY_REQ_188 is unaffected: the 25 kW cap is on " + ...
            "electrical\n");
        fprintf("  input and is enforced by bisection whatever the " + ...
            "machine can turn.\n");

        fprintf("\nACTION: ask Competr for the torque-speed envelope and " + ...
            "the maximum\n");
        fprintf("continuous speed. It is the cheapest open question in " + ...
            "the project.\n");

        fprintf("================================================================\n\n");

    end

    Audit = A;

end

%% =============================================================
% Wrap a long finding so the report stays readable in a terminal
%% =============================================================

function out = wrapText(txt,width,indent)

    words = split(string(txt));

    out = "";
    line = "";

    for k = 1:numel(words)

        if strlength(line) == 0
            candidate = words(k);
        else
            candidate = line + " " + words(k);
        end

        if strlength(candidate) > width && strlength(line) > 0
            out = out + line + newline + indent;
            line = words(k);
        else
            line = candidate;
        end

    end

    out = out + line;

end

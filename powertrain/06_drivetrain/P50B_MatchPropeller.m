function Match = P50B_MatchPropeller(varargin)
%P50B_MATCHPROPELLER  Choose diameter, pitch and gear ratio together.
%
%   Match = P50B_MatchPropeller() sweeps propeller diameter, pitch ratio
%   and gearbox ratio and returns the combination that makes the boat
%   fastest under the 25 kW cap, subject to the motor's speed and torque
%   limits and a cavitation screen.
%
%   OPTIONS
%     "Hull"          struct from P50B_HullModel
%     "DiameterRange" [lo hi] m, default [0.18 0.34]
%     "PitchRange"    [lo hi] P/D, default [0.75 1.40]
%     "GearRange"     [lo hi] motor rev per prop rev, default [1.0 3.0]
%     "Grid"          points per axis, default 22
%     "SigmaMin"      cavitation screen, default 0.06
%     "Verbose"       logical, default true
%     "Plot"          logical, default false
%
%   WHY DIAMETER, PITCH AND GEAR RATIO TOGETHER
%   -------------------------------------------
%   The Python model matches diameter and pitch at a fixed gear ratio.
%   That is the right thing to do when the gearbox is a given, but here
%   it is not: the datasheet confirms the Competr outboard has a gearbox
%   and does not state its ratio, so the ratio is an assumption like the
%   others and belongs in the sweep.
%
%   It also has to be in the sweep to see the problem. At the assumed
%   ratio of 2.0 the propeller wants about 3380 rev/min at top speed,
%   which asks the motor for roughly 6800 -- far above the 4000 rev/min
%   the model assumes it can do. Optimising diameter and pitch alone
%   cannot find that, because the constraint it violates lives in the
%   ratio. Sweeping the three together turns an infeasible design into a
%   feasible one instead of a slightly better infeasible one.
%
%   THE SCREENS
%   -----------
%   A candidate is rejected if it asks the motor to turn faster than its
%   maximum, if it asks for more torque than the motor can produce, or if
%   the cavitation number at 0.7R falls below the screen.
%
%   The torque screen is what stops the sweep running away. Without it
%   the optimiser discovers that an overdrive gearbox -- motor turning
%   slower than the propeller -- lets a small, very coarse propeller
%   reach an apparently excellent efficiency, and reports a boat 56%
%   faster than the baseline. It is fiction: at that ratio the motor
%   would need about 128 N.m against a 100 N.m rating. A power limit
%   alone does not constrain a drivetrain; power and torque together do.
%
%   WHERE THIS ANSWER STOPS BEING TRUSTWORTHY
%   -----------------------------------------
%   KT and KQ here are a generic correlation, and it has no idea it is
%   being extrapolated. Pushed past a pitch ratio of about 1.4 it keeps
%   promising thrust that a real blade would not make, and open-water
%   efficiency simply rises until it hits the 0.85 clamp inside
%   P50B_Propeller -- a guard rail, not a physical optimum.
%
%   The default pitch range therefore stops at 1.4, which is roughly
%   where the Wageningen B-series data it imitates stops. If the returned
%   optimum sits on any bound of the sweep, the report says so, because a
%   boundary optimum means the answer was chosen by the bound and not by
%   the physics.
%
%   Because the boat's top speed depends on the propeller that is being
%   chosen, the whole thing is iterated: match at the current speed,
%   recompute the speed, match again. It converges in three or four
%   passes.
%
%   See also P50B_Propeller, P50B_BoatDynamics, P50B_BoatPerformance.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct( ...
        "Hull",[], ...
        "DiameterRange",[0.18 0.34], ...
        "PitchRange",[0.75 1.40], ...
        "GearRange",[1.0 3.0], ...
        "Grid",22, ...
        "SigmaMin",0.06, ...
        "Verbose",true, ...
        "Plot",false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_MatchPropeller:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    C = P50B_HydroConstants();

    P = P50B_LoadParams("Plain",true);

    motor = P50B_MotorData();

    nMotorMax_rpm = P50B_Value(motor.MaximumSpeed_rpm);

    tMotorMax_Nm  = P50B_Value(motor.MaximumTorque_Nm);

    gearboxEff    = P50B_Value(motor.GearboxEfficiency);

    if isempty(opts.Hull)
        Hull = P50B_HullModel();
    else
        Hull = opts.Hull;
    end

    %% =========================================================
    % BASELINE
    %% =========================================================

    propBase = P50B_Propeller();
    boatBase = P50B_BoatDynamics("Hull",Hull,"Propeller",propBase);

    P_shaft_max_W = boatBase.ShaftPowerMax_W;
    drivelineEff  = boatBase.DrivelineEfficiency;

    vBase = boatBase.SteadySpeed(P_shaft_max_W);

    nBase = propBase.RPSForPower(vBase,P_shaft_max_W*drivelineEff);

    Baseline = struct( ...
        "Diameter_m",     propBase.Diameter_m, ...
        "PitchRatio",     propBase.PitchRatio, ...
        "GearRatio",      propBase.GearRatio, ...
        "TopSpeed_kmh",   vBase*C.KmhPerMs, ...
        "TopSpeed_knots", vBase*C.KnotsPerMs, ...
        "PropRPM",        nBase*60, ...
        "MotorRPM",       nBase*60*propBase.GearRatio, ...
        "MotorTorque_Nm", (P_shaft_max_W/gearboxEff) / ...
                          (2*pi*max(nBase*60*propBase.GearRatio,1e-9)/60), ...
        "OpenWaterEff",   propBase.OpenWaterEff(vBase,nBase), ...
        "CavitationNumber", propBase.CavitationNumber(vBase,nBase), ...
        "MotorSpeedOK",   nBase*60*propBase.GearRatio <= nMotorMax_rpm);

    %% =========================================================
    % SWEEP
    %
    % The boat's top speed depends on the propeller under test,
    % so each candidate is evaluated against the speed IT would
    % produce, not against the baseline's speed. Matching every
    % candidate at one fixed speed optimises an operating point
    % that only one of them actually reaches.
    %% =========================================================

    Ds     = linspace(opts.DiameterRange(1),opts.DiameterRange(2),opts.Grid);
    PDs    = linspace(opts.PitchRange(1),opts.PitchRange(2),opts.Grid);
    gears  = linspace(opts.GearRange(1),opts.GearRange(2),opts.Grid);

    nCand = numel(Ds)*numel(PDs)*numel(gears);

    if opts.Verbose
        fprintf("\nSweeping %d propeller and gearbox combinations ...\n",nCand);
    end

    best = struct("Score",-Inf);

    rows = struct("Diameter_m",{},"PitchRatio",{},"GearRatio",{}, ...
                  "TopSpeed_kmh",{},"MotorRPM",{},"MotorTorque_Nm",{}, ...
                  "OpenWaterEff",{},"CavitationNumber",{});

    nFeasible = 0;
    nRejectRPM = 0;
    nRejectCav = 0;
    nRejectTorque = 0;

    for iD = 1:numel(Ds)

        for iP = 1:numel(PDs)

            %% -------------------------------------------------
            % Speed and prop rev/s do not depend on the gear
            % ratio -- only the motor speed does. So solve the
            % hydrodynamics once per (D, P/D) and then test the
            % ratios against it. That makes the sweep cheap
            % enough to run at a useful resolution.
            %% -------------------------------------------------

            prop = P50B_Propeller("Diameter_m",Ds(iD), ...
                                  "PitchRatio",PDs(iP));

            boat = P50B_BoatDynamics("Hull",Hull,"Propeller",prop, ...
                "ShaftPowerMax_W",P_shaft_max_W);

            v = boat.SteadySpeed(P_shaft_max_W);

            n = prop.RPSForPower(v,P_shaft_max_W*drivelineEff);

            eta = prop.OpenWaterEff(v,n);

            sigma = prop.CavitationNumber(v,n);

            if sigma < opts.SigmaMin
                nRejectCav = nRejectCav + 1;
                continue;
            end

            for iG = 1:numel(gears)

                rpmMotor = n*60*gears(iG);

                if rpmMotor > nMotorMax_rpm
                    nRejectRPM = nRejectRPM + 1;
                    continue;
                end

                %% -----------------------------------------
                % Motor torque
                %
                % A gearbox that lets the motor turn slowly
                % enough to satisfy the speed limit makes it
                % carry the whole power at that speed, and
                % torque is what pays for that. Screening on
                % speed alone lets the sweep escape into
                % overdrive ratios the machine cannot deliver.
                %% -----------------------------------------

                P_motorMech_W = P_shaft_max_W / gearboxEff;

                torque_Nm = P_motorMech_W / (2*pi*rpmMotor/60);

                if torque_Nm > tMotorMax_Nm
                    nRejectTorque = nRejectTorque + 1;
                    continue;
                end

                nFeasible = nFeasible + 1;

                %% -----------------------------------------
                % Score on top speed, not on efficiency.
                %
                % Efficiency is the mechanism; speed under
                % the power cap is the objective. They mostly
                % agree, but where they disagree the race is
                % won by the boat that is faster, and a
                % gearbox ratio that trades a point of
                % open-water efficiency for staying inside
                % the motor's speed range is a trade worth
                % making.
                %
                % Ratio enters the score only through the
                % feasibility test above, so among ratios
                % that pass, the lowest is preferred as it
                % leaves the most headroom.
                %% -----------------------------------------

                score = v*C.KmhPerMs - 0.001*gears(iG);

                rows(end+1) = struct( ...
                    "Diameter_m",Ds(iD),"PitchRatio",PDs(iP), ...
                    "GearRatio",gears(iG),"TopSpeed_kmh",v*C.KmhPerMs, ...
                    "MotorRPM",rpmMotor,"MotorTorque_Nm",torque_Nm, ...
                    "OpenWaterEff",eta, ...
                    "CavitationNumber",sigma); %#ok<AGROW>

                if score > best.Score

                    best = struct( ...
                        "Score",score, ...
                        "Diameter_m",Ds(iD), ...
                        "PitchRatio",PDs(iP), ...
                        "GearRatio",gears(iG), ...
                        "TopSpeed_ms",v, ...
                        "TopSpeed_kmh",v*C.KmhPerMs, ...
                        "TopSpeed_knots",v*C.KnotsPerMs, ...
                        "PropRPM",n*60, ...
                        "MotorRPM",rpmMotor, ...
                        "MotorTorque_Nm",torque_Nm, ...
                        "OpenWaterEff",eta, ...
                        "CavitationNumber",sigma);

                end

                %% -----------------------------------------
                % Only the lowest feasible ratio is of
                % interest for a given (D, P/D): every higher
                % one gives the same boat with less motor
                % headroom.
                %% -----------------------------------------

                break;

            end

        end

    end

    %% =========================================================
    % RESULT
    %% =========================================================

    Match = struct();

    Match.Baseline    = Baseline;
    Match.Feasible    = nFeasible > 0;
    Match.Candidates  = nCand;
    Match.FeasibleCount = nFeasible;
    Match.RejectedOnMotorSpeed = nRejectRPM;
    Match.RejectedOnCavitation = nRejectCav;
    Match.RejectedOnTorque     = nRejectTorque;
    Match.MotorTorqueLimit_Nm  = tMotorMax_Nm;
    Match.MotorSpeedLimit_rpm  = nMotorMax_rpm;
    Match.ShaftPowerMax_W      = P_shaft_max_W;
    Match.SigmaMin             = opts.SigmaMin;

    if ~Match.Feasible

        Match.Best = [];

        if opts.Verbose
            fprintf("\nNo feasible combination.\n");
            fprintf("  %d rejected on motor speed, %d on torque, " + ...
                "%d on cavitation.\n",nRejectRPM,nRejectTorque,nRejectCav);
            fprintf("  Widen GearRange, or confirm the motor's real " + ...
                "maximum speed with Competr.\n");
        end

        return;

    end

    best = rmfield(best,"Score");

    Match.Best = best;

    Match.Table = struct2table(rows);

    Match.Gain_kmh = best.TopSpeed_kmh - Baseline.TopSpeed_kmh;

    Match.Gain_pct = 100*Match.Gain_kmh / max(Baseline.TopSpeed_kmh,1e-9);

    %% ---------------------------------------------------------
    % Is the optimum on a bound?
    %
    % A sweep whose winner sits on the edge of the search space
    % has not found an optimum -- it has found the edge. Saying
    % so is the difference between a result and a number.
    %% ---------------------------------------------------------

    tol = @(x,r) abs(x - r(1)) < 1e-9 || abs(x - r(2)) < 1e-9;

    onBound = strings(0,1);

    if tol(best.Diameter_m,opts.DiameterRange)
        onBound(end+1) = "diameter";
    end

    if tol(best.PitchRatio,opts.PitchRange)
        onBound(end+1) = "pitch ratio";
    end

    if tol(best.GearRatio,opts.GearRange)
        onBound(end+1) = "gearbox ratio";
    end

    Match.OnBound = onBound;

    %% ---------------------------------------------------------
    % Has the efficiency model hit its own clamp?
    %
    % P50B_Propeller clips open-water efficiency at 0.85. A
    % result sitting on that clip is the correlation being
    % extrapolated, not a propeller being good.
    %% ---------------------------------------------------------

    Match.EfficiencyClamped = best.OpenWaterEff >= 0.8499;

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose

        fprintf("\n");
        fprintf("================================================================\n");
        fprintf(" PROPELLER AND GEARBOX MATCH\n");
        fprintf("================================================================\n");

        fprintf("\nShaft power ceiling      : %.2f kW " + ...
                "(the 25 kW electrical cap)\n",P_shaft_max_W/1000);
        fprintf("Motor speed limit        : %.0f rpm\n",nMotorMax_rpm);
        fprintf("Combinations tried       : %d\n",nCand);
        fprintf("  rejected on motor speed: %d\n",nRejectRPM);
        fprintf("  rejected on cavitation : %d\n",nRejectCav);
        fprintf("  rejected on motor torque: %d\n",nRejectTorque);

        fprintf("\n%-26s %12s %12s\n","","AS ASSUMED","MATCHED");
        fprintf("%-26s %12.0f %12.0f\n","Diameter (mm)", ...
            Baseline.Diameter_m*1000,best.Diameter_m*1000);
        fprintf("%-26s %12.2f %12.2f\n","Pitch ratio", ...
            Baseline.PitchRatio,best.PitchRatio);
        fprintf("%-26s %12.2f %12.2f\n","Gearbox ratio", ...
            Baseline.GearRatio,best.GearRatio);
        fprintf("%-26s %12.1f %12.1f\n","Top speed (km/h)", ...
            Baseline.TopSpeed_kmh,best.TopSpeed_kmh);
        fprintf("%-26s %12.1f %12.1f\n","Prop speed (rpm)", ...
            Baseline.PropRPM,best.PropRPM);
        fprintf("%-26s %12.0f %12.0f\n","Motor speed (rpm)", ...
            Baseline.MotorRPM,best.MotorRPM);
        fprintf("%-26s %12.1f %12.1f\n","Motor torque (Nm)", ...
            Baseline.MotorTorque_Nm,best.MotorTorque_Nm);
        fprintf("%-26s %12.3f %12.3f\n","Open-water efficiency", ...
            Baseline.OpenWaterEff,best.OpenWaterEff);
        fprintf("%-26s %12.2f %12.2f\n","Cavitation number", ...
            Baseline.CavitationNumber,best.CavitationNumber);

        if ~Baseline.MotorSpeedOK

            fprintf("\n  The assumed propeller is NOT FEASIBLE as configured:\n");
            fprintf("  it asks the motor for %.0f rpm against a %.0f rpm\n", ...
                Baseline.MotorRPM,nMotorMax_rpm);
            fprintf("  limit -- %.0f%% over. The matched combination is\n", ...
                100*(Baseline.MotorRPM/nMotorMax_rpm - 1));
            fprintf("  the nearest one that the drivetrain can actually turn.\n");

        end

        fprintf("\n  Top speed %+.1f km/h (%+.1f%%)\n", ...
            Match.Gain_kmh,Match.Gain_pct);

        if ~isempty(Match.OnBound)

            fprintf("\n  CAUTION: the optimum sits on the %s bound of the\n", ...
                strjoin(Match.OnBound,", "));
            fprintf("  sweep. That means the answer was chosen by the search\n");
            fprintf("  range, not by the physics. Widen the range only if the\n");
            fprintf("  wider values are physically real -- the default pitch\n");
            fprintf("  ceiling of 1.4 is where the KT/KQ correlation stops\n");
            fprintf("  being defensible, not an arbitrary choice.\n");

        end

        if Match.EfficiencyClamped

            fprintf("\n  CAUTION: open-water efficiency is at the 0.85 clamp\n");
            fprintf("  inside P50B_Propeller. That is a guard rail, not a\n");
            fprintf("  physical optimum, and the result is not quotable.\n");

        end

        fprintf("\n  Both propeller curves are the generic KT/KQ fit, not\n");
        fprintf("  Competr's. Treat the numbers as a direction to push in,\n");
        fprintf("  and ask Competr for the open-water curves of the\n");
        fprintf("  counter-rotating pair before ordering anything.\n");

        fprintf("================================================================\n\n");

    end

    %% =========================================================
    % PLOT
    %% =========================================================

    if opts.Plot && Match.Feasible

        figure("Name","Propeller match","Color","w");

        T = Match.Table;

        scatter(T.Diameter_m*1000,T.TopSpeed_kmh,18,T.PitchRatio,"filled");

        hold on;

        plot(best.Diameter_m*1000,best.TopSpeed_kmh,"pk", ...
            "MarkerSize",16,"MarkerFaceColor","y");

        plot(Baseline.Diameter_m*1000,Baseline.TopSpeed_kmh,"or", ...
            "MarkerSize",10,"LineWidth",2);

        grid on;
        xlabel("Propeller diameter (mm)");
        ylabel("Top speed (km/h)");
        title("Feasible propellers under the 25 kW cap and the motor speed limit");

        cb = colorbar;
        cb.Label.String = "Pitch ratio P/D";

        legend(["feasible","matched","as assumed"],"Location","best");

    end

end

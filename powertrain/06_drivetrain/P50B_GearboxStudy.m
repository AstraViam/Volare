function Study = P50B_GearboxStudy(varargin)
%P50B_GEARBOXSTUDY  What gearbox ratio lets the boat use its legal power?
%
%   Study = P50B_GearboxStudy() sweeps the gearbox ratio and reports top
%   speed, the power actually delivered, and which limit is binding.
%
%   OPTIONS
%     "Ratios"    vector of motor-rev-per-front-rotor-rev, default
%                 1.4 to 3.2
%     "Verbose"   logical, default true
%     "Plot"      logical, default false
%
%   THE FINDING THIS EXISTS TO CARRY
%   --------------------------------
%   The contra-rotating propulsor was optimised at 20 knots, where it
%   needs 9.9 kW and the motor runs at 1300 rev/min and 75.8 N.m --
%   comfortable on a 100 N.m machine. Its gearbox ratio of 1.6079 was
%   chosen for that point.
%
%   At top speed the front rotor turns about 1065 rev/min, so through
%   that ratio the motor sees only 1712 rev/min. Delivering the 22.8 kW
%   that ENERGY_REQ_188 permits at that speed would take 131 N.m, which
%   the motor does not have. The boat is therefore TORQUE limited, and
%   it can use only about two thirds of the power it is allowed.
%
%   Raising the ratio does not touch the propeller or the hull. It lets
%   the motor spin faster for the same rotor speed, which is where the
%   torque headroom comes from. The sweep finds the knee at about 2.11,
%   and it is worth roughly 6 km/h:
%
%       ratio   top speed   shaft power   motor      binding
%       1.608     41.0        15.2 kW     1496 rpm   torque
%       2.111     47.4        22.9 kW     2251 rpm   knee
%       2.300     47.5        23.1 kW     2460 rpm   power
%       3.000     47.5        23.1 kW     3207 rpm   power
%
%   Past the knee there is nothing left to win -- the rule cap binds
%   instead -- while motor speed keeps climbing towards a limit nobody
%   has confirmed. So the answer is a ratio of about 2.1 to 2.3, and not
%   more.
%
%   WHY THAT ANSWER IS ROBUST
%   -------------------------
%   The motor's maximum speed is disputed: 4000 rev/min in this model,
%   back-solved from the datasheet's 42 kW peak, against 2500 rev/min in
%   the hydrodynamics team's brief. See P50B_MotorSpecAudit. A
%   recommendation that depended on which is right would be worth
%   little. This one does not: 2251 to 2460 rev/min sits inside BOTH.
%
%   NEITHER MODEL COULD HAVE FOUND THIS ALONE
%   -----------------------------------------
%   The hydrodynamics tool has the propulsor but optimises at 20 knots,
%   where the ratio is fine. The electrical model has the rule cap and
%   the motor envelope but had no propulsor -- it modelled a single
%   screw the boat does not have. The constraint only appears when the
%   two are evaluated against each other.
%
%   CAVEAT
%   ------
%   Changing the ratio changes the rotor speed the propulsor sees at any
%   given power, which changes the point the BEM design was optimised
%   for. The right closing move is to rerun the hydrodynamics tool at
%   the new ratio, not to take the speed here as final. What this study
%   establishes is that the ratio is worth revisiting, and roughly where
%   to look.
%
%   See also P50B_BoatDynamics, P50B_Propulsor, P50B_MotorSpecAudit.

    opts = struct( ...
        "Ratios",linspace(1.4,3.2,19), ...
        "Verbose",true, ...
        "Plot",false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_GearboxStudy:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    C = P50B_HydroConstants();

    Hull = P50B_HullModel();
    Prop = P50B_Propulsor();

    motor = P50B_MotorData();

    Qmax   = P50B_Value(motor.MaximumTorque_Nm);
    etaGb  = P50B_Value(motor.GearboxEfficiency);

    P = P50B_LoadParams("Plain",true);

    nMaxUsed  = P.motor.max_speed_rpm;
    nMaxBrief = P.motor.max_speed_rpm_brief;

    ratios = opts.Ratios(:);

    n = numel(ratios);

    GearRatio     = ratios;
    TopSpeed_kmh  = zeros(n,1);
    TopSpeed_knots = zeros(n,1);
    ShaftPower_W  = zeros(n,1);
    Ceiling_W     = zeros(n,1);
    MotorRPM      = zeros(n,1);
    MotorTorque_Nm = zeros(n,1);
    LimitedBy     = strings(n,1);
    WithinBothSpeedLimits = false(n,1);

    for k = 1:n

        prop = Prop;
        prop.GearRatio = ratios(k);

        Boat = P50B_BoatDynamics("Hull",Hull,"Propeller",prop);

        v = Boat.SteadySpeed(Boat.ShaftPowerMax_W);

        [Pok,binding] = Boat.TorqueLimitedPower(v,Boat.ShaftPowerMax_W);

        nProp = prop.RPSForPower(v,Pok*Boat.DrivelineEfficiency);

        rpm = nProp*60*ratios(k);

        TopSpeed_kmh(k)   = v * C.KmhPerMs;
        TopSpeed_knots(k) = v * C.KnotsPerMs;
        ShaftPower_W(k)   = Pok;
        Ceiling_W(k)      = Boat.ShaftPowerMax_W;
        MotorRPM(k)       = rpm;
        MotorTorque_Nm(k) = (Pok/etaGb) / max(2*pi*rpm/60,1e-9);
        LimitedBy(k)      = binding;

        WithinBothSpeedLimits(k) = rpm <= min(nMaxUsed,nMaxBrief);

    end

    T = table(GearRatio,TopSpeed_kmh,TopSpeed_knots,ShaftPower_W, ...
              Ceiling_W,MotorRPM,MotorTorque_Nm,LimitedBy, ...
              WithinBothSpeedLimits);

    Study = struct();

    Study.Table = T;
    Study.MotorTorqueLimit_Nm = Qmax;
    Study.MotorSpeedUsed_rpm  = nMaxUsed;
    Study.MotorSpeedBrief_rpm = nMaxBrief;

    %% =========================================================
    % THE FITTED RATIO AND THE KNEE
    %% =========================================================

    fittedRatio = P.hydro.front_gear_ratio;

    [~,iFitted] = min(abs(ratios - fittedRatio));

    Study.Fitted = tableRow(T,iFitted);
    Study.Fitted.GearRatio = fittedRatio;

    %% ---------------------------------------------------------
    % The knee: the smallest ratio at which torque stops binding.
    %
    % Smallest, not fastest. Past the knee top speed is flat to
    % within a tenth of a km/h while motor speed keeps rising
    % towards a limit that is still disputed, so a larger ratio
    % buys nothing and spends margin.
    %% ---------------------------------------------------------

    isPowerLimited = LimitedBy == "power";

    iKnee = find(isPowerLimited,1,"first");

    if isempty(iKnee)

        Study.Knee = [];
        Study.Recommendation = sprintf( ...
            "No ratio in the swept range %.2f to %.2f frees the " + ...
            "drivetrain from its torque limit. Widen the sweep.", ...
            ratios(1),ratios(end));

    else

        Study.Knee = tableRow(T,iKnee);

        Study.Gain_kmh = T.TopSpeed_kmh(iKnee) - Study.Fitted.TopSpeed_kmh;

        Study.Gain_pct = 100*Study.Gain_kmh / ...
                         max(Study.Fitted.TopSpeed_kmh,1e-9);

        Study.Recommendation = sprintf( ...
            "Specify the gearbox at about %.2f:1 rather than %.4f:1. " + ...
            "Top speed %.1f to %.1f km/h (%+.1f%%), motor at %.0f rpm, " + ...
            "which is inside both the %.0f and %.0f rpm figures.", ...
            T.GearRatio(iKnee),fittedRatio, ...
            Study.Fitted.TopSpeed_kmh,T.TopSpeed_kmh(iKnee), ...
            Study.Gain_pct,T.MotorRPM(iKnee),nMaxBrief,nMaxUsed);

    end

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose

        fprintf("\n");
        fprintf("================================================================\n");
        fprintf(" GEARBOX RATIO STUDY\n");
        fprintf("================================================================\n");

        fprintf("\nMotor torque limit        : %.0f Nm\n",Qmax);
        fprintf("Motor speed limit         : %.0f rpm (this model) / " + ...
            "%.0f rpm (brief)\n",nMaxUsed,nMaxBrief);
        fprintf("Propulsor as designed     : %.4f:1\n",fittedRatio);

        fprintf("\n %8s %10s %10s %10s %8s  %-8s %s\n", ...
            "ratio","km/h","shaft kW","motor rpm","Nm","binding","both?");

        for k = 1:n

            if WithinBothSpeedLimits(k)
                fits = "yes";
            else
                fits = "NO";
            end

            marker = "  ";

            if abs(ratios(k) - fittedRatio) < 0.05
                marker = "<-";
            end

            fprintf("%s%8.3f %10.1f %10.2f %10.0f %8.1f  %-8s %s\n", ...
                marker,ratios(k),TopSpeed_kmh(k),ShaftPower_W(k)/1000, ...
                MotorRPM(k),MotorTorque_Nm(k),LimitedBy(k),fits);

        end

        fprintf("\n%s\n",wrapAt(Study.Recommendation,64));

        fprintf("\nThe propulsor is a fixed design optimised at 20 knots. " + ...
            "Changing the\n");
        fprintf("ratio moves the rotor speed it sees, so rerun the " + ...
            "hydrodynamics tool\n");
        fprintf("in 04_data/hydrodynamics/ at the new ratio before " + ...
            "committing to a\n");
        fprintf("gearbox. This study says the ratio is worth revisiting " + ...
            "and roughly\n");
        fprintf("where to look; it does not settle the blade design.\n");

        fprintf("================================================================\n\n");

    end

    if opts.Plot

        figure("Name","Gearbox ratio","Color","w");

        yyaxis left;
        plot(T.GearRatio,T.TopSpeed_kmh,"-o","LineWidth",1.5);
        ylabel("Top speed (km/h)");

        yyaxis right;
        plot(T.GearRatio,T.MotorRPM,"-s","LineWidth",1.2);
        hold on;
        yline(nMaxBrief,"--","brief limit");
        yline(nMaxUsed,":","datasheet-implied limit");
        ylabel("Motor speed (rpm)");

        xline(fittedRatio,"k-","as designed");
        grid on;
        xlabel("Gearbox ratio (motor rev per front-rotor rev)");
        title("Top speed and motor speed against gearbox ratio");

    end

end

%% =============================================================
% Helpers
%% =============================================================

function r = tableRow(T,i)

    r = struct();

    names = T.Properties.VariableNames;

    for k = 1:numel(names)
        r.(names{k}) = T.(names{k})(i);
    end

end

function out = wrapAt(txt,width)

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
            out = out + line + newline;
            line = words(k);
        else
            line = candidate;
        end

    end

    out = out + line;

end

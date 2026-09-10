function Profile = P50B_MissionProfile(name,varargin)
%P50B_MISSIONPROFILE  Time-series power and speed demand for a mission.
%
%   Profile = P50B_MissionProfile(NAME) returns a mission profile as a
%   time series of propeller shaft power demand and motor speed.
%
%   Available profiles:
%
%     "endurance"   Sustained cruise at the competition power cap, the
%                   case that determines how long the boat can run.
%
%     "sprint"      Short bursts at maximum power separated by low-power
%                   recovery. Stresses peak current and thermal
%                   transient rather than energy.
%
%     "slalom"      Repeated acceleration and deceleration around marks.
%                   High cycling, moderate mean power.
%
%     "constant"    Flat power, for sanity checks and sweeps. Use the
%                   "Power" option to set the level.
%
%   Profile = P50B_MissionProfile(NAME,"Duration",T) overrides the
%   default duration in seconds.
%
%   OPTIONS
%     "Duration"    seconds
%     "TimeStep"    seconds, default 0.5
%     "Power"       W, for the "constant" profile
%     "PowerCap"    W, competition power limit, default 25000
%
%   IMPORTANT -- THESE PROFILES ARE REPRESENTATIVE, NOT OFFICIAL
%   -----------------------------------------------------------
%   The shapes below are engineering constructions intended to exercise
%   the drivetrain in the ways a race does: sustained load, peak load,
%   and rapid cycling. They are NOT transcriptions of any published
%   Monaco Energy Boat Challenge event definition.
%
%   Before using a result from these profiles to make a design decision
%   or a competition claim, replace them with the actual event
%   specification: course length, permitted power, event duration and
%   the number of runs.
%
%   POWER IS AT THE PROPELLER SHAFT
%   -------------------------------
%   The profile specifies shaft power, not battery power. The drivetrain
%   model works backwards from shaft power through the gearbox, motor,
%   inverter and interconnect to find what the pack must supply, which
%   is always more. A 25 kW cap applied at the battery terminals would
%   be a different and stricter constraint -- check which one the rules
%   actually impose.
%
%   See also P50B_RunMission, P50B_DrivetrainModel.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct( ...
        "Duration", [], ...
        "TimeStep", 0.5, ...
        "Power",    15e3, ...
        "PowerCap", 25e3);

    for k = 1:2:numel(varargin)

        optName = string(varargin{k});

        if ~isfield(opts,optName)
            error("P50B_MissionProfile:UnknownOption", ...
                "Unknown option '%s'.",optName);
        end

        opts.(optName) = varargin{k+1};

    end

    if nargin < 1 || isempty(name)
        name = "endurance";
    end

    name = lower(string(name));

    motor = P50B_MotorData();

    %% =========================================================
    % POWER CAP FROM THE RULES
    %
    % Monaco ENERGY_REQ_188 caps the motor's electrical power
    % consumption at 25 kW. The profile is expressed in shaft
    % power, which is lower by the motor and gearbox
    % efficiencies, so the shaft cap is derived rather than set
    % to 25 kW directly.
    %
    % Setting the shaft cap to 25 kW would quietly demand about
    % 26.9 kW of motor input and break the rule.
    %% =========================================================

    if ~any(strcmpi(string(varargin(1:2:end)),"PowerCap"))

        opts.PowerCap = motor.ConfiguredPowerLimit_W * ...
                        motor.PeakEfficiency * ...
                        motor.GearboxEfficiency;

    end

    %% =========================================================
    % BUILD
    %% =========================================================

    switch name

        case "endurance"

            duration = defaultIfEmpty(opts.Duration,3600);

            t = (0:opts.TimeStep:duration)';

            %% -----------------------------------------------------
            % Steady cruise at the power cap, with a ramp in and a
            % ramp out. Small variation represents helm and sea
            % state rather than a perfectly flat demand.
            %% -----------------------------------------------------

            P = opts.PowerCap * ones(size(t));

            rampTime = 20;

            P = P .* min(t/rampTime,1);

            P = P .* min((duration - t)/rampTime,1);

            % Gentle variation, deterministic so runs are repeatable
            P = P .* (1 + 0.04*sin(2*pi*t/180) + 0.02*sin(2*pi*t/47));

            P = max(P,0);

            description = ...
                "Sustained cruise at the competition power cap.";

        case "sprint"

            duration = defaultIfEmpty(opts.Duration,600);

            t = (0:opts.TimeStep:duration)';

            %% -----------------------------------------------------
            % 30 s at maximum power, 90 s recovery, repeated.
            %% -----------------------------------------------------

            burstPeriod = 120;
            burstLength = 30;

            phase = mod(t,burstPeriod);

            inBurst = phase < burstLength;

            P = zeros(size(t));

            P(inBurst)  = motor.MaximumPower_W;
            P(~inBurst) = 0.15 * motor.MaximumPower_W;

            % Soften the edges: a real throttle is not a step
            P = smoothSignal(P,round(2/opts.TimeStep));

            description = ...
                "Repeated 30 s bursts at maximum power.";

        case "slalom"

            duration = defaultIfEmpty(opts.Duration,900);

            t = (0:opts.TimeStep:duration)';

            %% -----------------------------------------------------
            % Continuous acceleration and deceleration around marks,
            % roughly 12 s per gate.
            %% -----------------------------------------------------

            gatePeriod = 12;

            base = 0.55 * opts.PowerCap;

            swing = 0.45 * opts.PowerCap;

            P = base + swing*sin(2*pi*t/gatePeriod);

            % Manoeuvring adds a slower load variation
            P = P + 0.10*opts.PowerCap*sin(2*pi*t/95);

            P = max(P,0);

            description = ...
                "Repeated acceleration and deceleration around marks.";

        case "constant"

            duration = defaultIfEmpty(opts.Duration,1800);

            t = (0:opts.TimeStep:duration)';

            P = opts.Power * ones(size(t));

            description = sprintf( ...
                "Constant %.1f kW shaft power.",opts.Power/1000);

        otherwise

            error("P50B_MissionProfile:UnknownProfile", ...
                "Unknown profile '%s'. Available: endurance, " + ...
                "sprint, slalom, constant.",name);

    end

    %% =========================================================
    % MOTOR SPEED
    %
    % Propeller load follows roughly a cube law: shaft power
    % scales with the cube of speed. Inverting gives speed from
    % power demand, which is a reasonable model for a fixed-pitch
    % propeller at steady state.
    %
    %     n = n_rated * (P / P_rated)^(1/3)
    %
    % This does not capture acceleration transients, where the
    % boat is still slow while power is already high. For a
    % drivetrain electrical study that matters less than it would
    % for a hull study.
    %% =========================================================

    ratedPower = motor.NominalPower_W;

    ratedSpeed = motor.BaseSpeed_rpm;

    n = ratedSpeed * (max(P,0)/ratedPower).^(1/3);

    %% ---------------------------------------------------------
    % Idle floor
    %
    % Below a minimum speed the propeller is not driving the boat
    % and the model would divide by a near-zero speed to find
    % torque.
    %% ---------------------------------------------------------

    minSpeed = 200;

    n = max(n,minSpeed);

    n = min(n,motor.MaximumSpeed_rpm);

    %% =========================================================
    % OUTPUT
    %% =========================================================

    Profile.Name             = name;
    Profile.Description      = description;
    Profile.Time_s           = t;
    Profile.ShaftPower_W     = P;
    Profile.MotorSpeed_rpm   = n;
    Profile.TimeStep_s       = opts.TimeStep;
    Profile.Duration_s       = t(end);

    Profile.MeanPower_W      = mean(P);
    Profile.PeakPower_W      = max(P);
    Profile.ShaftEnergy_Wh   = trapz(t,P)/3600;

    Profile.PowerCap_W       = opts.PowerCap;

    Profile.Provenance = ...
        "Representative shape, NOT an official event definition. " + ...
        "Replace with the actual Monaco Energy Boat Challenge " + ...
        "course and power specification before quoting results.";

end

%% =============================================================
% Helpers
%% =============================================================

function v = defaultIfEmpty(v,d)

    if isempty(v)
        v = d;
    end

end

function y = smoothSignal(x,n)

    if n < 2
        y = x;
        return;
    end

    kernel = ones(n,1)/n;

    y = conv(x,kernel,"same");

    % conv with "same" attenuates the ends; restore them
    y(1:n)         = x(1:n);
    y(end-n+1:end) = x(end-n+1:end);

end

function [P_shaft_W,info] = P50B_ShaftPowerCeiling(motorSpeed_rpm,varargin)
%P50B_SHAFTPOWERCEILING  Largest shaft power the 25 kW rule permits.
%
%   P = P50B_ShaftPowerCeiling(RPM) returns the shaft power whose motor
%   ELECTRICAL input is exactly the ENERGY_REQ_188 limit, at motor speed
%   RPM. With no argument a representative race speed is used.
%
%   [P,info] = ... also returns the electrical input, the losses and the
%   speed the solve was done at.
%
%   OPTIONS
%     "Motor"     struct from P50B_MotorData
%     "SOC"       state of charge for the solve, default 0.6
%     "Temp_C"    cell temperature for the solve, default 35
%
%   WHY THIS IS NOT SIMPLY 25 kW
%   ----------------------------
%   ENERGY_REQ_188 caps "the total nominal power consumption of the
%   motor(s)". Consumption is electrical input. A boat set up to deliver
%   25 kW at the shaft would draw about 26.9 kW to do it and would be in
%   breach, so the shaft figure that satisfies the rule is lower than the
%   rule's number and depends on where the motor is operating.
%
%   Getting this backwards is an easy and expensive mistake: the model
%   would report a legal boat that is not legal, and the error would only
%   surface at scrutineering with a wattmeter on the DC link.
%
%   The ceiling is mildly speed dependent, because iron and windage
%   losses are. It is therefore solved at the operating point rather than
%   fixed once, and the speed used is reported so the number can never be
%   quoted without its context.
%
%   See also P50B_DrivetrainModel, P50B_BoatDynamics, P50B_MonacoCompliance.

    opts = struct("Motor",[],"SOC",0.60,"Temp_C",35);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_ShaftPowerCeiling:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if isempty(opts.Motor)
        motor = P50B_MotorData();
    else
        motor = opts.Motor;
    end

    if nargin < 1 || isempty(motorSpeed_rpm)

        %% -----------------------------------------------------
        % Representative race speed: the base speed of the
        % machine. Chosen rather than the maximum because the
        % boat spends its endurance race near continuous rating,
        % not at redline.
        %% -----------------------------------------------------

        motorSpeed_rpm = P50B_Value(motor.BaseSpeed_rpm);

    end

    %% ---------------------------------------------------------
    % Ask the drivetrain solver for far more shaft power than
    % the rule can allow and read back what it capped it to.
    % The cap logic then lives in exactly one place.
    %% ---------------------------------------------------------

    demand_W = 4 * P50B_Value(motor.ConfiguredPowerLimit_W);

    op = P50B_DrivetrainModel(demand_W,motorSpeed_rpm, ...
        opts.SOC,opts.Temp_C,"Motor",motor);

    P_shaft_W = op.PowerLimit.DeliveredShaft_W;

    info = struct( ...
        "MotorSpeed_rpm",     motorSpeed_rpm, ...
        "ElectricalLimit_W",  op.PowerLimit.Limit_W, ...
        "ShaftCeiling_W",     P_shaft_W, ...
        "MotorInput_W",       op.Motor.InputPower_W, ...
        "ShaftFraction",      P_shaft_W / op.PowerLimit.Limit_W, ...
        "SOC",                opts.SOC, ...
        "Temp_C",             opts.Temp_C);

end

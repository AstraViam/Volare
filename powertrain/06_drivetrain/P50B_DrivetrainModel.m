function op = P50B_DrivetrainModel(shaftPower_W,motorSpeed_rpm,soc,cellTemp_C,varargin)
%P50B_DRIVETRAINMODEL  Solve the full electrical chain for one operating point.
%
%   op = P50B_DrivetrainModel(P_SHAFT,N_MOTOR,SOC,T_CELL) solves the
%   complete power path backwards from a demanded propeller shaft power
%   to the resulting cell current, and returns every intermediate
%   quantity.
%
%   The chain solved, in the direction the physics actually runs:
%
%       cells -> collectors -> series links -> pack terminals
%             -> harness (cable, fuse, contactor, joints)
%             -> DC link -> inverter switches
%             -> motor windings -> shaft -> gearbox -> propeller
%
%   plus the auxiliary 12 V load tapped off the pack through the DC/DC.
%
%   INPUTS
%     P_SHAFT    Propeller shaft power demand, W. Positive = propulsion.
%     N_MOTOR    Motor speed, rpm.
%     SOC        Pack state of charge, 0 to 1.
%     T_CELL     Mean cell temperature, degC.
%
%   NAME-VALUE OPTIONS
%     Busbars      Bus struct from P50B_Busbars. Recomputed if omitted,
%                  which is slow -- pass it in when sweeping.
%     Motor        Struct from P50B_MotorData.
%     Inverter     Struct from P50B_InverterData.
%     Harness      Struct from P50B_HarnessData.
%     Auxiliary    Struct from P50B_AuxiliaryLoads.
%     Cell         Struct from P50B_CellData.
%     IncludeAux   Logical, default true.
%
%   WHY THE SOLVE IS CLOSED-FORM
%   ----------------------------
%   Pack current appears on both sides of the problem: current causes
%   voltage sag, and sag raises the current needed for a given power.
%   Rather than iterate, the terminal condition
%
%       I * (Vocv - I*Rtot) = P_bus
%
%   is solved directly as a quadratic in I. The physical root is the
%   smaller one; the larger root is the unstable high-current branch
%   that a real system never sits on.
%
%   A negative discriminant means the demanded power exceeds what the
%   pack can deliver at this SOC and temperature at all. That is a real
%   and important failure mode -- it is reported, not silently clamped.
%
%   See also P50B_MotorData, P50B_InverterData, P50B_Busbars,
%   P50B_RunMission.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct( ...
        "Busbars",             [], ...
        "Motor",               [], ...
        "Inverter",            [], ...
        "Harness",             [], ...
        "Auxiliary",           [], ...
        "Cell",                [], ...
        "IncludeAux",          true, ...
        "EnforcePowerLimit",   true);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_DrivetrainModel:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if isempty(opts.Motor);     opts.Motor     = P50B_MotorData();       end
    if isempty(opts.Inverter);  opts.Inverter  = P50B_InverterData();    end
    if isempty(opts.Harness);   opts.Harness   = P50B_HarnessData();     end
    if isempty(opts.Auxiliary); opts.Auxiliary = P50B_AuxiliaryLoads();  end
    if isempty(opts.Cell);      opts.Cell      = P50B_CellData();        end

    motor = opts.Motor;
    inv   = opts.Inverter;
    harn  = opts.Harness;
    aux   = opts.Auxiliary;
    cell  = opts.Cell;

    %% ---------------------------------------------------------
    % Busbar resistance
    %
    % Computed silently if not supplied. The full busbar model is
    % expensive, so sweeps should pass it in once.
    %% ---------------------------------------------------------

    if isempty(opts.Busbars)

        G      = P50B_Geometry();
        Layout = P50B_GroupLayout(G,"Plot",false);
        Bus    = P50B_Busbars(G,Layout,"Plot",false,"Verbose",false);

    else

        Bus = opts.Busbars;

    end

    %% =========================================================
    % PACK CONSTANTS
    %% =========================================================

    Ns = 26;
    Np = 21;

    op.Demand.ShaftPower_W    = shaftPower_W;
    op.Demand.MotorSpeed_rpm  = motorSpeed_rpm;
    op.Demand.SOC             = soc;
    op.Demand.CellTemp_C      = cellTemp_C;

    omegaMotor = motorSpeed_rpm * 2*pi/60;      % rad/s

    %% =========================================================
    % HARD POWER CAP -- MONACO ENERGY_REQ_188
    %
    % "The total nominal power consumption of the motor(s) shall
    %  not exceed 25 kW."
    %
    % This is enforced, not merely reported. The inverter is
    % configured to cap motor electrical input at the limit, so a
    % demand above it does not produce a higher-power operating
    % point -- it produces a power-limited one, which is what the
    % real boat would do.
    %
    % Motor input rises monotonically with shaft power at fixed
    % speed, so the largest permissible shaft power is found by
    % bisection.
    %% =========================================================

    powerLimit_W = motor.ConfiguredPowerLimit_W;

    requestedShaftPower_W = shaftPower_W;

    powerLimited = false;

    if opts.EnforcePowerLimit && shaftPower_W > 0

        if motorInputPower(shaftPower_W,motorSpeed_rpm,motor) > powerLimit_W

            lo = 0;
            hi = shaftPower_W;

            for iter = 1:80

                mid = 0.5*(lo + hi);

                if motorInputPower(mid,motorSpeed_rpm,motor) > powerLimit_W
                    hi = mid;
                else
                    lo = mid;
                end

            end

            shaftPower_W = lo;

            powerLimited = true;

        end

    end

    op.PowerLimit.Limit_W            = powerLimit_W;
    op.PowerLimit.Active             = powerLimited;
    op.PowerLimit.RequestedShaft_W   = requestedShaftPower_W;
    op.PowerLimit.DeliveredShaft_W   = shaftPower_W;
    op.PowerLimit.ShortfallShaft_W   = ...
        requestedShaftPower_W - shaftPower_W;

    op.Demand.ShaftPower_W = shaftPower_W;

    %% =========================================================
    % STAGE 1: GEARBOX
    %
    % Shaft power at the propeller is what produces thrust. The
    % motor must produce more, by the gearbox efficiency.
    %% =========================================================

    P_motorMech = shaftPower_W / motor.GearboxEfficiency;

    op.Gearbox.InputPower_W  = P_motorMech;
    op.Gearbox.OutputPower_W = shaftPower_W;
    op.Gearbox.Loss_W        = P_motorMech - shaftPower_W;
    op.Gearbox.Efficiency    = motor.GearboxEfficiency;

    %% =========================================================
    % STAGE 2: MOTOR
    %% =========================================================

    %% ---------------------------------------------------------
    % Torque and current
    %
    % Assumes Id = 0 control, valid below base speed for a
    % machine with little saliency. Above base speed field
    % weakening would add Id and this underestimates current.
    %% ---------------------------------------------------------

    if omegaMotor > 0
        torque_Nm = P_motorMech / omegaMotor;
    else
        torque_Nm = 0;
    end

    iq_peak = torque_Nm / ...
        (1.5 * motor.PolePairs * motor.FluxLinkage_Wb);

    Irms_phase = abs(iq_peak) / sqrt(2);

    Ipk_phase  = abs(iq_peak);

    %% ---------------------------------------------------------
    % Copper loss, at temperature
    %
    % Winding resistance is taken at the design winding
    % temperature, not at 20 degC. A hot machine is a lossier
    % machine, and using the cold value flatters the result by
    % roughly 30%.
    %% ---------------------------------------------------------

    windingTemp_C = motor.WindingTempForCalibration_C;

    Rphase_hot = motor.PhaseResistance_Ohm * ...
        (1 + motor.CopperTempCoefficient_perK * (windingTemp_C - 20));

    P_copper = 3 * Irms_phase^2 * Rphase_hot;

    %% ---------------------------------------------------------
    % Iron loss
    %
    % Hysteresis term linear in electrical frequency, eddy-current
    % term quadratic. Both are driven by frequency, not by load,
    % which is why they dominate efficiency at high speed and
    % light load.
    %% ---------------------------------------------------------

    f_elec = motor.PolePairs * motorSpeed_rpm / 60;

    P_iron = motor.IronLossCoefficient_W_per_Hz * f_elec + ...
             motor.IronLossCoefficient_W_per_Hz2 * f_elec^2;

    %% ---------------------------------------------------------
    % Windage and constant mechanical loss
    %% ---------------------------------------------------------

    P_windage = motor.WindageCoefficient_W_per_rpm3 * motorSpeed_rpm^3;

    P_mechConst = motor.MechanicalLossConstant_W;

    if motorSpeed_rpm <= 0
        P_windage   = 0;
        P_mechConst = 0;
    end

    %% ---------------------------------------------------------
    % Motor electrical input
    %% ---------------------------------------------------------

    P_motorLoss = P_copper + P_iron + P_windage + P_mechConst;

    P_ac = P_motorMech + P_motorLoss;

    op.Motor.Torque_Nm          = torque_Nm;
    op.Motor.Speed_rpm          = motorSpeed_rpm;
    op.Motor.Speed_rad_s        = omegaMotor;
    op.Motor.ElectricalFreq_Hz  = f_elec;
    op.Motor.PhaseCurrentRMS_A  = Irms_phase;
    op.Motor.PhaseCurrentPeak_A = Ipk_phase;
    op.Motor.PhaseResistance_Ohm = Rphase_hot;
    op.Motor.CopperLoss_W       = P_copper;
    op.Motor.IronLoss_W         = P_iron;
    op.Motor.WindageLoss_W      = P_windage;
    op.Motor.ConstantLoss_W     = P_mechConst;
    op.Motor.TotalLoss_W        = P_motorLoss;
    op.Motor.InputPower_W       = P_ac;
    op.Motor.OutputPower_W      = P_motorMech;

    if P_ac > 0
        op.Motor.Efficiency = P_motorMech / P_ac;
    else
        op.Motor.Efficiency = NaN;
    end

    %% =========================================================
    % STAGE 3: INVERTER
    %% =========================================================

    %% ---------------------------------------------------------
    % Conduction loss
    %
    % In a MOSFET bridge each phase current flows through exactly
    % one device of its leg at any instant, so total conduction
    % loss is 3 * Irms^2 * Rds_on regardless of duty distribution.
    %
    % Rds_on is taken hot. SiC on-resistance rises steeply with
    % junction temperature, and the cold value would understate
    % loss by around 60%.
    %---------------------------------------------------------

    Rds_hot = inv.Rds_on_Ohm * inv.Rds_on_TempCoefficient;

    P_conduction = 3 * Irms_phase^2 * Rds_hot + ...
                   3 * Irms_phase * inv.Vce0_V;

    %% ---------------------------------------------------------
    % Switching loss
    %
    % Datasheet switching energies are quoted at one reference
    % voltage and current. They scale roughly linearly with both.
    %
    % Over a fundamental period each device switches at f_sw but
    % the current at each event varies sinusoidally; the mean of
    % the rectified sinusoid gives the Ipk/pi factor.
    %
    % At a 93.6 V bus against a 400 V reference this term is
    % scaled down by about 4.3x, which is why a low-voltage
    % traction drive is conduction-dominated rather than
    % switching-dominated.
    %% ---------------------------------------------------------

    Esw_total = inv.Eon_J + inv.Eoff_J + inv.Erec_J;

    voltageScale = inv.BusVoltageNominal_V / ...
                   inv.SwitchingReferenceVoltage_V;

    currentScale = (Ipk_phase/pi) / inv.SwitchingReferenceCurrent_A;

    P_switching = 6 * inv.SwitchingFrequency_Hz * Esw_total * ...
                  voltageScale * currentScale;

    %% ---------------------------------------------------------
    % Dead-time body-diode conduction
    %% ---------------------------------------------------------

    P_deadtime = 6 * inv.SwitchingFrequency_Hz * inv.DeadTime_s * ...
                 inv.DiodeVf_V * (Ipk_phase/pi);

    %% ---------------------------------------------------------
    % DC link capacitor self-heating
    %% ---------------------------------------------------------

    I_ripple = Irms_phase * inv.DCLinkRippleCoefficient;

    P_dclink = I_ripple^2 * inv.DCLinkESR_Ohm;

    %% ---------------------------------------------------------
    % Gate drive and control
    %% ---------------------------------------------------------

    P_invAux = inv.GateDriverPower_W + inv.ControlPower_W;

    %% ---------------------------------------------------------
    % Inverter DC input
    %% ---------------------------------------------------------

    P_invLoss = P_conduction + P_switching + P_deadtime + ...
                P_dclink + P_invAux;

    P_dc = P_ac + P_invLoss;

    op.Inverter.ConductionLoss_W  = P_conduction;
    op.Inverter.SwitchingLoss_W   = P_switching;
    op.Inverter.DeadTimeLoss_W    = P_deadtime;
    op.Inverter.DCLinkLoss_W      = P_dclink;
    op.Inverter.AuxiliaryPower_W  = P_invAux;
    op.Inverter.TotalLoss_W       = P_invLoss;
    op.Inverter.InputPower_W      = P_dc;
    op.Inverter.OutputPower_W     = P_ac;
    op.Inverter.RippleCurrentRMS_A = I_ripple;
    op.Inverter.Rds_on_Hot_Ohm    = Rds_hot;

    if P_dc > 0
        op.Inverter.Efficiency = P_ac / P_dc;
    else
        op.Inverter.Efficiency = NaN;
    end

    %% =========================================================
    % STAGE 4: AUXILIARY LOAD
    %% =========================================================

    if opts.IncludeAux
        P_aux = aux.AverageLoadFromPack_W;
    else
        P_aux = 0;
    end

    op.Auxiliary.PowerFromPack_W = P_aux;

    %% =========================================================
    % STAGE 5: BUS POWER DEMANDED AT THE PACK TERMINALS
    %% =========================================================

    P_bus = P_dc + P_aux;

    op.Bus.DemandedPower_W = P_bus;

    %% =========================================================
    % STAGE 6: PACK, BUSBARS AND HARNESS
    %% =========================================================

    %% ---------------------------------------------------------
    % Open-circuit voltage at this SOC
    %% ---------------------------------------------------------

    Vcell_ocv = P50B_OCV(soc);

    Vpack_ocv = Ns * Vcell_ocv;

    %% ---------------------------------------------------------
    % Cell resistance at this SOC and temperature
    %
    % 26 in series, 21 in parallel.
    %% ---------------------------------------------------------

    Rcell = P50B_DCIR(soc,cellTemp_C);

    Rpack_cells = Ns * Rcell / Np;

    %% ---------------------------------------------------------
    % Total series resistance seen by the load
    %% ---------------------------------------------------------

    Rbusbar = Bus.Rtotal;

    Rharness = harn.TotalResistance_Ohm;

    Rtotal = Rpack_cells + Rbusbar + Rharness;

    %% ---------------------------------------------------------
    % Solve  I*(Vocv - I*Rtotal) = P_bus  for I
    %
    %     Rtotal*I^2 - Vocv*I + P_bus = 0
    %% ---------------------------------------------------------

    discriminant = Vpack_ocv^2 - 4*Rtotal*P_bus;

    P_maxDeliverable = Vpack_ocv^2 / (4*Rtotal);

    if discriminant < 0

        %% -----------------------------------------------------
        % Demanded power is beyond the pack's capability at this
        % SOC and temperature. Report it rather than clamp.
        %% -----------------------------------------------------

        op.Feasible = false;

        op.InfeasibleReason = sprintf( ...
            "Demanded bus power %.0f W exceeds the maximum " + ...
            "deliverable %.0f W at SOC %.2f and %.0f degC. " + ...
            "Pack OCV %.1f V, total series resistance %.2f mOhm.", ...
            P_bus, P_maxDeliverable, soc, cellTemp_C, ...
            Vpack_ocv, Rtotal*1e3);

        Ipack = NaN;

    else

        op.Feasible = true;

        op.InfeasibleReason = "";

        % Smaller root: the physical, stable operating branch
        Ipack = (Vpack_ocv - sqrt(discriminant)) / (2*Rtotal);

    end

    %% ---------------------------------------------------------
    % Resulting voltages and losses
    %% ---------------------------------------------------------

    Vpack_terminal = Vpack_ocv - Ipack*Rtotal;

    Icell = Ipack / Np;

    P_cellLoss    = Ipack^2 * Rpack_cells;
    P_busbarLoss  = Ipack^2 * Rbusbar;
    P_harnessLoss = Ipack^2 * Rharness;

    op.Pack.OCV_V                 = Vpack_ocv;
    op.Pack.CellOCV_V             = Vcell_ocv;
    op.Pack.TerminalVoltage_V     = Vpack_terminal;
    op.Pack.Current_A             = Ipack;
    op.Pack.CellCurrent_A         = Icell;
    op.Pack.CellCRate             = Icell / cell.Capacity_Ah;
    op.Pack.CellResistance_Ohm    = Rcell;
    op.Pack.InternalResistance_Ohm = Rpack_cells;
    op.Pack.BusbarResistance_Ohm  = Rbusbar;
    op.Pack.HarnessResistance_Ohm = Rharness;
    op.Pack.TotalResistance_Ohm   = Rtotal;
    op.Pack.CellLoss_W            = P_cellLoss;
    op.Pack.BusbarLoss_W          = P_busbarLoss;
    op.Pack.HarnessLoss_W         = P_harnessLoss;
    op.Pack.DrawnPower_W          = Vpack_ocv * Ipack;
    op.Pack.MaxDeliverablePower_W = P_maxDeliverable;
    op.Pack.VoltageSag_V          = Vpack_ocv - Vpack_terminal;
    op.Pack.CellHeatPerCell_W     = Icell^2 * Rcell;

    %% =========================================================
    % OVERALL CHAIN
    %% =========================================================

    P_source = op.Pack.DrawnPower_W;

    op.Chain.SourcePower_W = P_source;
    op.Chain.ShaftPower_W  = shaftPower_W;

    op.Chain.TotalLoss_W = ...
        P_cellLoss + P_busbarLoss + P_harnessLoss + ...
        P_invLoss + P_motorLoss + op.Gearbox.Loss_W + P_aux;

    if P_source > 0
        op.Chain.OverallEfficiency = shaftPower_W / P_source;
    else
        op.Chain.OverallEfficiency = NaN;
    end

    %% ---------------------------------------------------------
    % Loss breakdown, largest contributor first
    %
    % This is the output that actually tells you where to spend
    % engineering effort.
    %% ---------------------------------------------------------

    lossNames = [ ...
        "Cells (internal)" ...
        "Busbars (in pack)" ...
        "Harness (pack to inverter)" ...
        "Inverter" ...
        "Motor" ...
        "Gearbox" ...
        "Auxiliary (12 V)"]';

    lossValues = [ ...
        P_cellLoss; ...
        P_busbarLoss; ...
        P_harnessLoss; ...
        P_invLoss; ...
        P_motorLoss; ...
        op.Gearbox.Loss_W; ...
        P_aux];

    if op.Chain.TotalLoss_W > 0
        lossShare = lossValues / op.Chain.TotalLoss_W;
    else
        lossShare = nan(size(lossValues));
    end

    Breakdown = table( ...
        lossNames, ...
        lossValues, ...
        lossShare, ...
        'VariableNames',{'Stage','Loss_W','ShareOfTotalLoss'});

    op.Chain.LossBreakdown = sortrows(Breakdown,"Loss_W","descend");

    %% =========================================================
    % LIMIT CHECKS
    %
    % Every one of these is a real constraint from a datasheet or
    % a design decision. Reporting them alongside the operating
    % point means a violation cannot be missed.
    %% =========================================================

    op.Limits.CellCurrentLimit_A = cell.MaxContinuousCurrent_A;

    op.Limits.CellCurrentOK = ...
        abs(Icell) <= cell.MaxContinuousCurrent_A;

    op.Limits.CellCurrentUtilisation = ...
        abs(Icell) / cell.MaxContinuousCurrent_A;

    op.Limits.BusCurrentLimit_A = motor.BusMaximumCurrent_A;

    op.Limits.BusCurrentOK = ...
        abs(Ipack) <= motor.BusMaximumCurrent_A;

    op.Limits.BusCurrentUtilisation = ...
        abs(Ipack) / motor.BusMaximumCurrent_A;

    op.Limits.HarnessAmpacity_A = harn.CableAmpacity_A;

    op.Limits.HarnessAmpacityOK = ...
        abs(Ipack) <= harn.CableAmpacity_A;

    op.Limits.PackVoltageMin_V = Ns * cell.MinVoltage_V;

    op.Limits.PackVoltageOK = ...
        Vpack_terminal >= Ns * cell.MinVoltage_V;

    op.Limits.MotorPowerLimit_W = motor.MaximumPower_W;

    op.Limits.MotorPowerOK = ...
        P_motorMech <= motor.MaximumPower_W;

    %% ---------------------------------------------------------
    % Monaco ENERGY_REQ_188
    %
    % "The total nominal power consumption of the motor(s) shall
    %  not exceed 25 kW."
    %
    % Read as the electrical power the motor consumes, which is
    % the inverter's AC output, not the shaft output. Shaft power
    % is always lower, so checking the shaft would let the boat
    % consume more than the rule allows and still look compliant.
    %% ---------------------------------------------------------

    op.Limits.RulePowerLimit_W = motor.ConfiguredPowerLimit_W;

    op.Limits.MotorInputPower_W = P_ac;

    op.Limits.RulePowerOK = ...
        P_ac <= motor.ConfiguredPowerLimit_W;

    op.Limits.RulePowerUtilisation = ...
        P_ac / motor.ConfiguredPowerLimit_W;

    op.Limits.MotorTorqueLimit_Nm = motor.MaximumTorque_Nm;

    op.Limits.MotorTorqueOK = ...
        abs(torque_Nm) <= motor.MaximumTorque_Nm;

    op.Limits.AllOK = ...
        op.Feasible && ...
        op.Limits.CellCurrentOK && ...
        op.Limits.BusCurrentOK && ...
        op.Limits.HarnessAmpacityOK && ...
        op.Limits.PackVoltageOK && ...
        op.Limits.MotorPowerOK && ...
        op.Limits.MotorTorqueOK && ...
        op.Limits.RulePowerOK;

end

%% =============================================================
% Motor electrical input power
%
% Duplicates the motor stage of the main solve so that the power
% cap can be searched for without running the whole chain. Kept
% in one place here and called from both, so the two cannot
% drift apart.
%% =============================================================

function P_ac = motorInputPower(shaftPower_W,motorSpeed_rpm,motor)

    omegaMotor = motorSpeed_rpm * 2*pi/60;

    P_motorMech = shaftPower_W / motor.GearboxEfficiency;

    if omegaMotor > 0
        torque_Nm = P_motorMech / omegaMotor;
    else
        torque_Nm = 0;
    end

    iq_peak = torque_Nm / ...
        (1.5 * motor.PolePairs * motor.FluxLinkage_Wb);

    Irms_phase = abs(iq_peak) / sqrt(2);

    windingTemp_C = motor.WindingTempForCalibration_C;

    Rphase_hot = motor.PhaseResistance_Ohm * ...
        (1 + motor.CopperTempCoefficient_perK * (windingTemp_C - 20));

    P_copper = 3 * Irms_phase^2 * Rphase_hot;

    f_elec = motor.PolePairs * motorSpeed_rpm / 60;

    P_iron = motor.IronLossCoefficient_W_per_Hz * f_elec + ...
             motor.IronLossCoefficient_W_per_Hz2 * f_elec^2;

    if motorSpeed_rpm > 0
        P_windage   = motor.WindageCoefficient_W_per_rpm3 * motorSpeed_rpm^3;
        P_mechConst = motor.MechanicalLossConstant_W;
    else
        P_windage   = 0;
        P_mechConst = 0;
    end

    P_ac = P_motorMech + P_copper + P_iron + P_windage + P_mechConst;

end

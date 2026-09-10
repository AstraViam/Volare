function motor = P50B_MotorData()
%P50B_MOTORDATA  Competr electric outboard traction motor parameters.
%
%   motor = P50B_MotorData() returns the parameter set for the axial-flux
%   PMSM inside the Competr counter-rotating electric outboard, as fitted
%   to this project's 26S21P P50B pack.
%
%   Structure follows the project convention:
%
%     motor.<Name>    bare numeric values
%     motor.P.<Name>  the same values with unit, source and note
%
%   SOURCE
%   ------
%   Values tagged DATASHEET come from the Competr technical datasheet
%   (New_Datasheet Competr_0625.pdf, rev 06/25) held in 04_data/.
%
%   The datasheet is a system-level document. It specifies what comes out
%   of the outboard -- power, torque, voltage, current -- but not the
%   machine's internal electrical parameters (Ld, Lq, flux linkage, pole
%   pairs, phase resistance). Those are needed for any dq-frame or loss
%   model, so they are estimated here and tagged ASSUMPTION. They are the
%   highest-value numbers to obtain from Competr.
%
%   PACK COMPATIBILITY NOTE
%   -----------------------
%   The datasheet specifies a 26S battery, and the maximum battery
%   voltage of 109 V corresponds exactly to 26 x 4.2 V. The P50B 26S21P
%   pack is therefore a correct series count for this drivetrain.
%
%   Two differences from the Competr stock pack are worth being explicit
%   about, because they change what this outboard can do:
%
%     Energy.  Stock pack is 26 kWh. The P50B 26S21P is 9.83 kWh
%              nominal, about 2.6x smaller. This is an endurance
%              limit, not a capability limit.
%
%     Voltage. Competr quotes 96 V nominal, implying ~3.69 V/cell.
%              The P50B nominal is 3.6 V/cell, giving 93.6 V. This is
%              a 2.5% lower nominal bus voltage, which raises current
%              slightly for the same power.
%
%   See also P50B_InverterData, P50B_DrivetrainModel, P50B_Param.

    %% =========================================================
    % IDENTIFICATION
    %% =========================================================

    %% =========================================================
    % CACHE
    %
    % Pure function of params/volare_params.json. Rebuilding it on
    % every call is waste, and the drivetrain solver calls it once
    % per mission time step when the caller does not pass it in.
    %% =========================================================

    persistent cached cachedStamp

    jsonFile = fullfile(P50B_ProjectRoot(),"params","volare_params.json");

    stamp = "";
    if isfile(jsonFile)
        dd = dir(jsonFile);
        stamp = string(dd.datenum);
    end

    if ~isempty(cached) && isequal(cachedStamp,stamp)
        motor = cached;
        return;
    end

    motor.Manufacturer = "Competr";
    motor.Product      = "Electric outboard powertrain";
    motor.MotorType    = "Axial flux PMSM, water cooled";
    motor.Datasheet    = "New_Datasheet Competr_0625.pdf";

    %% =========================================================
    % RATED PERFORMANCE -- DATASHEET
    %% =========================================================

    P.NominalPower_W = P50B_FromFile("motor.power_nominal_W");

    P.MaximumPower_W = P50B_FromFile("motor.power_max_W");

    P.MaximumTorque_Nm = P50B_FromFile("motor.torque_max_Nm");

    %% ---------------------------------------------------------
    % CONFIGURED POWER LIMIT -- MONACO ENERGY_REQ_188
    %
    % "The total nominal power consumption of the motor(s) shall
    %  not exceed 25 kW."  (Technical Rules 2026.1, new for 2026)
    %
    % The Competr outboard's own nominal rating is 26.9 kW, which
    % is 1.9 kW over that limit, and its peak is 42 kW. The
    % hardware is therefore not compliant as delivered.
    %
    % The drivetrain must be power-limited in the inverter
    % configuration. This parameter is that limit, and every
    % model in this project enforces it, so the results describe
    % a boat that could actually race rather than one that would
    % be rejected at scrutineering.
    %
    % The limit has to be demonstrable to the Technical
    % Committee, not merely asserted. Get it in writing from
    % Competr and be able to show it in the inverter settings.
    %% ---------------------------------------------------------

    P.ConfiguredPowerLimit_W = P50B_FromFile("motor.configured_power_limit_W");

    P.HardwareExceedsRuleLimit = P50B_Param(true,"-","CALCULATED", ...
        "Note","Competr nominal 26.9 kW is above the 25 kW rule " + ...
               "limit, so the derate is mandatory, not optional.");

    P.Mass_kg = P50B_FromFile("motor.mass_kg");

    P.Length_m = P50B_FromFile("motor.length_m");
    P.Width_m  = P50B_FromFile("motor.width_m");
    P.Depth_m  = P50B_FromFile("motor.depth_m");

    P.ShaftLength_m = P50B_FromFile("motor.shaft_length_m");

    %% =========================================================
    % BUS INTERFACE -- DATASHEET
    %
    % These are the numbers the pack and busbars must satisfy.
    %% =========================================================

    P.BusNominalVoltage_V = P50B_FromFile("motor.bus_v_nominal_V");

    P.BusMaximumVoltage_V = P50B_FromFile("motor.bus_v_max_V");

    P.BusMaximumCurrent_A = P50B_FromFile("motor.bus_i_max_A");

    %% =========================================================
    % SPEED
    %
    % The datasheet gives power and torque but not rated speed.
    % Base speed follows from them if the machine is torque-limited
    % up to the corner point, which is the normal design intent:
    %
    %     omega_base = P_nominal / T_max
    %
    % This is a derived estimate, not a datasheet value, and it
    % assumes the 26.9 kW and 100 Nm ratings meet at the corner.
    %% =========================================================

    omegaBase = P.NominalPower_W.Value / P.MaximumTorque_Nm.Value;

    P.BaseSpeed_rad_s = P50B_Param(omegaBase,"rad/s","CALCULATED", ...
        "Note","NominalPower / MaximumTorque. Assumes the two " + ...
               "ratings meet at the corner point. Confirm with Competr.");

    P.BaseSpeed_rpm = P50B_Param(omegaBase*60/(2*pi),"rpm","CALCULATED");

    P.MaximumSpeed_rpm = P50B_FromFile("motor.max_speed_rpm");

    %% =========================================================
    % ELECTRICAL MACHINE PARAMETERS
    %
    % None of these are in the datasheet. They are estimated so
    % that a dq-frame model can run at all, and every one of them
    % is tagged ASSUMPTION.
    %
    % Ask Competr for: pole pairs, Ld, Lq, permanent-magnet flux
    % linkage, phase resistance at 20 degC, and the efficiency map.
    % That single request would move most of this block to
    % DATASHEET and materially improve every loss number downstream.
    %% =========================================================

    P.PolePairs = P50B_FromFile("motor.pole_pairs");

    %% ---------------------------------------------------------
    % Phase resistance is NOT assumed directly.
    %
    % It is back-solved further down from the peak-efficiency
    % target, so that copper loss, iron loss and the efficiency
    % figure are mutually consistent instead of three independent
    % guesses that contradict each other.
    %
    % Assuming a resistance and separately declaring an
    % efficiency is how a model ends up quietly reporting 89%
    % while its own datasheet field claims 95.5%.
    %% ---------------------------------------------------------

    P.CopperTempCoefficient_perK = P50B_FromFile("motor.cu_tempco_per_K");

    P.Ld_H = P50B_FromFile("motor.Ld_H");

    P.Lq_H = P50B_FromFile("motor.Lq_H");

    %% ---------------------------------------------------------
    % Permanent-magnet flux linkage
    %
    % Derived from the torque rating rather than assumed outright,
    % using the non-salient torque relation:
    %
    %     T = 1.5 * p * lambda * Iq
    %
    % evaluated at the rated peak phase current estimated below.
    % This keeps flux linkage, torque and current mutually
    % consistent instead of three independent guesses.
    %% ---------------------------------------------------------

    P.RatedPhaseCurrentPeak_A = P50B_FromFile("motor.rated_phase_current_peak_A");

    lambda = P.MaximumTorque_Nm.Value / ...
        (1.5 * P.PolePairs.Value * P.RatedPhaseCurrentPeak_A.Value);

    P.FluxLinkage_Wb = P50B_Param(lambda,"Wb","CALCULATED", ...
        "Note","Back-calculated from T = 1.5*p*lambda*Iq at rated " + ...
               "torque and assumed rated current. Inherits the " + ...
               "uncertainty of both.");

    %% ---------------------------------------------------------
    % Back-EMF constant
    %
    % Line-to-line RMS back-EMF per mechanical rad/s. Useful as a
    % sanity check: at maximum speed the back-EMF must stay below
    % the available bus voltage, or the machine needs field
    % weakening.
    %% ---------------------------------------------------------

    P.BackEMFConstant_Vs_rad = P50B_Param( ...
        sqrt(3) * P.PolePairs.Value * lambda / sqrt(2), ...
        "V*s/rad","CALCULATED", ...
        "Note","Line-to-line RMS per mechanical rad/s.");

    %% =========================================================
    % LOSS MODEL COEFFICIENTS
    %
    % Loss is split into the three physical mechanisms so that
    % each scales correctly with operating point, rather than
    % applying one flat efficiency number:
    %
    %   Copper   proportional to current squared
    %   Iron     rises with electrical frequency
    %   Windage  rises steeply with speed
    %
    % The coefficients are fitted so that peak efficiency lands at
    % a value typical for a water-cooled axial-flux PMSM.
    %% =========================================================

    P.PeakEfficiency = P50B_FromFile("motor.peak_efficiency");

    P.IronLossCoefficient_W_per_Hz = P50B_FromFile("motor.iron_loss_k1_W_per_Hz");

    P.IronLossCoefficient_W_per_Hz2 = P50B_FromFile("motor.iron_loss_k2_W_per_Hz2");

    P.WindageCoefficient_W_per_rpm3 = P50B_FromFile("motor.windage_k_W_per_rpm3");

    P.MechanicalLossConstant_W = P50B_FromFile("motor.mech_loss_const_W");

    %% ---------------------------------------------------------
    % Phase resistance, back-solved from the efficiency target
    %
    % At the nominal operating point the total loss budget is
    %
    %     P_loss = P_nominal * (1/eta - 1)
    %
    % Iron, windage and constant losses are subtracted from that
    % budget; whatever remains is the copper allowance, and the
    % phase resistance follows from
    %
    %     P_copper = 3 * Irms^2 * R_hot
    %
    % The result is stated at 20 degC, since that is how a
    % datasheet would quote it, by dividing out the temperature
    % rise to the assumed winding temperature.
    %% ---------------------------------------------------------

    nRated = P.BaseSpeed_rpm.Value;

    fRated = P.PolePairs.Value * nRated / 60;

    ironRated = ...
        P.IronLossCoefficient_W_per_Hz.Value * fRated + ...
        P.IronLossCoefficient_W_per_Hz2.Value * fRated^2;

    windageRated = ...
        P.WindageCoefficient_W_per_rpm3.Value * nRated^3;

    lossBudget = P.NominalPower_W.Value * ...
        (1/P.PeakEfficiency.Value - 1);

    copperBudget = lossBudget - ironRated - windageRated - ...
        P.MechanicalLossConstant_W.Value;

    %% ---------------------------------------------------------
    % Guard: if the speed-dependent losses already exceed the
    % budget the efficiency target is unreachable with these
    % coefficients, and silently returning a negative resistance
    % would be far worse than saying so.
    %% ---------------------------------------------------------

    if copperBudget <= 0

        error("P50B_MotorData:InconsistentLossModel", ...
            "Iron, windage and constant losses (%.0f W) already " + ...
            "exceed the %.0f W budget implied by a %.1f%% peak " + ...
            "efficiency. Lower the loss coefficients or the " + ...
            "efficiency target.", ...
            ironRated + windageRated + P.MechanicalLossConstant_W.Value, ...
            lossBudget, P.PeakEfficiency.Value*100);

    end

    IrmsRated = P.RatedPhaseCurrentPeak_A.Value / sqrt(2);

    RphaseHot = copperBudget / (3 * IrmsRated^2);

    windingTempAssumed = 100;

    Rphase20 = RphaseHot / ...
        (1 + P.CopperTempCoefficient_perK.Value * ...
             (windingTempAssumed - 20));

    P.PhaseResistance_Ohm = P50B_Param(Rphase20,"Ohm","CALCULATED", ...
        "Note","Per phase at 20 degC, back-solved so the loss model " + ...
               "reproduces the assumed peak efficiency at the " + ...
               "nominal operating point. Replace with the measured " + ...
               "value if Competr supplies one.");

    P.WindingTempForCalibration_C = P50B_FromFile("motor.winding_temp_calib_C");

    P.CopperLossAtRated_W = ...
        P50B_Param(copperBudget,"W","CALCULATED");

    P.IronLossAtRated_W = ...
        P50B_Param(ironRated,"W","CALCULATED");

    %% =========================================================
    % THERMAL
    %% =========================================================

    P.CoolingType = P50B_FromFile("motor.type");

    P.WindingTempMax_C = P50B_FromFile("motor.T_winding_max_C");

    P.CoolantInletTempMax_C = P50B_FromFile("motor.coolant_inlet_max_C");

    P.ThermalResistanceWindingToCoolant_K_W = P50B_FromFile("motor.R_wind_coolant_KW");

    %% =========================================================
    % DRIVE TRAIN MECHANICAL
    %% =========================================================

    P.PropellerType = P50B_FromFile("motor.propeller_type");

    P.GearboxRatio = P50B_FromFile("motor.gearbox_ratio");

    P.GearboxEfficiency = P50B_FromFile("motor.gearbox_efficiency");

    %% =========================================================
    % PUBLISH BOTH LAYERS
    %% =========================================================

    motor.P = P;

    plain = P50B_Unwrap(P);

    fn = fieldnames(plain);

    for k = 1:numel(fn)
        motor.(fn{k}) = plain.(fn{k});
    end

    %% =========================================================
    % STORE
    %% =========================================================

    cached      = motor;
    cachedStamp = stamp;

end

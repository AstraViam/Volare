function inv = P50B_InverterData()
%P50B_INVERTERDATA  Three-phase traction inverter parameters and sizing.
%
%   inv = P50B_InverterData() returns the parameter set for the inverter
%   driving the Competr outboard from the 26S21P P50B pack.
%
%   WHY THIS FILE COMPUTES A REQUIREMENT, NOT JUST A SPEC
%   ----------------------------------------------------
%   The Competr datasheet does not specify an inverter. Section 5,
%   "Recommended parts", lists the inverter as:
%
%       Inverter | On request | Higher current rating required to
%                              reach full output power
%
%   That note is the single most consequential open item in the
%   drivetrain, so this file treats inverter selection as a sizing
%   problem rather than a lookup. It derives the current, voltage and
%   thermal ratings a candidate device must meet, then models a
%   representative device against them.
%
%   The device parameters tagged ASSUMPTION describe a plausible
%   650 V / 600 A automotive SiC or IGBT module. Replace them once a
%   real part is chosen; the sizing requirements above them do not
%   change, because they follow from the motor and the pack.
%
%   See also P50B_MotorData, P50B_DrivetrainModel, P50B_Param.

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
        inv = cached;
        return;
    end

    motor = P50B_MotorData();

    %% =========================================================
    % IDENTIFICATION
    %% =========================================================

    inv.Manufacturer = "Not yet selected";
    inv.Product      = "3-phase 2-level voltage-source inverter";
    inv.Topology     = "Six-switch bridge, SVPWM";

    inv.SelectionStatus = ...
        "OPEN -- Competr datasheet lists inverter as 'on request'.";

    %% =========================================================
    % BUS CONDITIONS IMPOSED BY THE PACK
    %
    % These are hard facts about the P50B 26S21P pack. Any
    % candidate inverter must tolerate them.
    %% =========================================================

    P.BusVoltageMax_V = P50B_Param(26*4.2,"V","CALCULATED", ...
        "Note","26S at 4.2 V/cell. Matches the Competr 109 V figure.");

    P.BusVoltageNominal_V = P50B_Param(26*3.6,"V","CALCULATED", ...
        "Note","26S at 3.6 V/cell nominal.");

    P.BusVoltageMin_V = P50B_Param(26*2.5,"V","CALCULATED", ...
        "Note","26S at the 2.5 V cut-off. The inverter must still " + ...
               "commutate here, and current for a given power is " + ...
               "highest at this point.");

    %% ---------------------------------------------------------
    % Device blocking voltage
    %
    % Bus maximum plus switching overshoot, then a design margin.
    % 109 V bus does not justify a 650 V device on voltage alone,
    % but automotive modules at the required current rating are
    % commonly 650 V parts, so that is what gets specified.
    %% ---------------------------------------------------------

    P.OvershootFactor = P50B_FromFile("inverter.overshoot_factor");

    P.BlockingVoltageRequired_V = P50B_Param( ...
        P.BusVoltageMax_V.Value * P.OvershootFactor.Value, ...
        "V","CALCULATED", ...
        "Note","Minimum device blocking voltage.");

    %% =========================================================
    % CURRENT REQUIREMENT
    %
    % This is the calculation the Competr note is pointing at.
    %
    % The worst case for inverter current is maximum power at
    % minimum bus voltage, because phase current scales as
    % P / V. Sizing at nominal voltage understates the
    % requirement and is the usual way this gets got wrong.
    %% =========================================================

    P.ModulationIndexMax = P50B_Param(1.0/sqrt(3),"-","CALCULATED", ...
        "Note","SVPWM peak phase voltage = Vdc/sqrt(3).");

    P.PowerFactor = P50B_FromFile("inverter.power_factor");

    %% ---------------------------------------------------------
    % Continuous rating, from the Competr 375 A bus limit
    %% ---------------------------------------------------------

    P.DCCurrentContinuous_A = P50B_FromFile("motor.bus_i_max_A");

    %% ---------------------------------------------------------
    % Peak rating, from the 42 kW maximum power figure
    %% ---------------------------------------------------------

    P.PowerLimit_W = P50B_FromFile("motor.configured_power_limit_W");

    P.DCCurrentPeak_A = P50B_Param( ...
        motor.ConfiguredPowerLimit_W / P.BusVoltageNominal_V.Value, ...
        "A","CALCULATED", ...
        "Note","25 kW rule limit at 93.6 V nominal bus.");

    P.DCCurrentPeakWorstCase_A = P50B_Param( ...
        motor.ConfiguredPowerLimit_W / P.BusVoltageMin_V.Value, ...
        "A","CALCULATED", ...
        "Note","25 kW rule limit at the 65 V minimum bus. This is " + ...
               "the number that sizes the DC link, the busbars and " + ...
               "the fuse -- higher than the 267 A the cap implies at " + ...
               "nominal voltage, because current rises as the pack " + ...
               "empties.");

    P.HardwarePeakIfUncapped_A = P50B_Param( ...
        motor.MaximumPower_W / P.BusVoltageMin_V.Value, ...
        "A","CALCULATED", ...
        "Note","What the outboard could draw at 42 kW and minimum " + ...
               "bus if the cap failed. Not an operating point; " + ...
               "relevant only to fault analysis and fuse clearing.");

    %% ---------------------------------------------------------
    % Phase current
    %
    % For a balanced three-phase load:
    %
    %     P_ac = sqrt(3) * V_ll_rms * I_rms * pf
    %
    % with V_ll_rms = Vdc / sqrt(2) at full SVPWM modulation.
    %% ---------------------------------------------------------

    inverterEfficiencyGuess = 0.97;

    Pac_peak = motor.ConfiguredPowerLimit_W;

    Vll_rms_nominal = P.BusVoltageNominal_V.Value / sqrt(2);

    Irms_peak = Pac_peak / ...
        (sqrt(3) * Vll_rms_nominal * P.PowerFactor.Value * ...
         inverterEfficiencyGuess);

    P.PhaseCurrentRMSPeak_A = P50B_Param(Irms_peak,"A","CALCULATED", ...
        "Note","RMS phase current at the 25 kW cap, nominal bus.");

    P.PhaseCurrentPeakPeak_A = P50B_Param( ...
        Irms_peak*sqrt(2),"A","CALCULATED", ...
        "Note","Peak of the phase current sinusoid. This is what " + ...
               "the device datasheet Ic pulsed rating must cover.");

    %% ---------------------------------------------------------
    % Recommended device rating with margin
    %% ---------------------------------------------------------

    P.CurrentDesignMargin = P50B_FromFile("inverter.current_design_margin");

    P.DeviceCurrentRatingRequired_A = P50B_Param( ...
        Irms_peak*sqrt(2)*P.CurrentDesignMargin.Value, ...
        "A","CALCULATED", ...
        "Note","Minimum device current rating to quote to suppliers, " + ...
               "sized against the 25 kW cap. Capping the inverter is " + ...
               "not only a rules requirement -- it also roughly halves " + ...
               "the device rating the drive needs.");

    %% =========================================================
    % SWITCHING
    %% =========================================================

    P.SwitchingFrequency_Hz = P50B_FromFile("inverter.f_switching_Hz");

    P.DeadTime_s = P50B_FromFile("inverter.dead_time_s");

    P.DeviceTechnology = P50B_FromFile("inverter.technology");

    %% =========================================================
    % DEVICE LOSS PARAMETERS
    %
    % Conduction loss is modelled as a fixed threshold plus a
    % resistive term:
    %
    %     V_on(I) = Vce0 + Rce * I
    %
    % For a SiC MOSFET the threshold is essentially zero and the
    % behaviour is purely resistive, which is why it is preferred
    % at this current level.
    %
    % Switching loss is modelled from the datasheet switching
    % energies, scaled linearly with current and bus voltage from
    % their reference test conditions.
    %% =========================================================

    P.Vce0_V = P50B_FromFile("inverter.Vce0_V");

    P.Rds_on_Ohm = P50B_FromFile("inverter.Rds_on_ohm");

    P.Rds_on_TempCoefficient = P50B_FromFile("inverter.Rds_on_tempco");

    P.DiodeVf_V = P50B_FromFile("inverter.diode_Vf_V");

    P.Eon_J = P50B_FromFile("inverter.Eon_J");

    P.Eoff_J = P50B_FromFile("inverter.Eoff_J");

    P.Erec_J = P50B_FromFile("inverter.Erec_J");

    P.SwitchingReferenceVoltage_V = P50B_FromFile("inverter.E_ref_voltage_V");

    P.SwitchingReferenceCurrent_A = P50B_FromFile("inverter.E_ref_current_A");

    %% =========================================================
    % DC LINK
    %
    % The DC-link capacitor absorbs the difference between the
    % smooth pack current and the pulsed inverter current. It is
    % sized by RMS ripple current, not by capacitance.
    %% =========================================================

    P.DCLinkCapacitance_F = P50B_FromFile("inverter.dc_link_C_F");

    P.DCLinkESR_Ohm = P50B_FromFile("inverter.dc_link_ESR_ohm");

    %% ---------------------------------------------------------
    % Worst-case DC-link ripple current
    %
    % For a three-phase inverter the DC-link RMS ripple peaks at
    % roughly half the phase RMS current, near modulation index
    % 0.61 with unity power factor. Using 0.5 as the coefficient
    % is the standard conservative approximation.
    %% ---------------------------------------------------------

    P.DCLinkRippleCoefficient = P50B_FromFile("inverter.dc_link_ripple_coeff");

    P.DCLinkRippleCurrentRMS_A = P50B_Param( ...
        Irms_peak * 0.5, ...
        "A","CALCULATED", ...
        "Note","Capacitor must be rated for at least this RMS " + ...
               "ripple at the switching frequency and at " + ...
               "operating temperature.");

    %% =========================================================
    % AUXILIARY AND CONTROL
    %% =========================================================

    P.GateDriverPower_W = P50B_FromFile("inverter.gate_driver_W");

    P.ControlPower_W = P50B_FromFile("inverter.control_W");

    %% =========================================================
    % THERMAL
    %% =========================================================

    P.JunctionTempMax_C = P50B_FromFile("inverter.T_junction_max_C");

    P.JunctionTempDesign_C = P50B_FromFile("inverter.T_junction_max_C");

    P.ThermalResistanceJunctionToCase_K_W = P50B_FromFile("inverter.R_junc_hs_KW");

    P.ThermalResistanceCaseToCoolant_K_W = P50B_FromFile("inverter.R_hs_coolant_KW");

    P.CoolantInletTemp_C = P50B_FromFile("inverter.coolant_inlet_C");

    %% =========================================================
    % SENSOR INTERFACE -- DATASHEET
    %
    % Recorded because it constrains the inverter selection: the
    % chosen unit must speak SSI to the Competr encoder and read
    % an analog PTC, or an interface board is required.
    %% =========================================================

    P.PositionSensorType = P50B_FromFile("motor.position_sensor");

    P.MotorTempSensorType = P50B_FromFile("motor.temp_sensor");

    %% =========================================================
    % PUBLISH BOTH LAYERS
    %% =========================================================

    inv.P = P;

    plain = P50B_Unwrap(P);

    fn = fieldnames(plain);

    for k = 1:numel(fn)
        inv.(fn{k}) = plain.(fn{k});
    end

    %% =========================================================
    % STORE
    %% =========================================================

    cached      = inv;
    cachedStamp = stamp;

end

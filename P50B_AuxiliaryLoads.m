function aux = P50B_AuxiliaryLoads()
%P50B_AUXILIARYLOADS  12 V hotel and actuator loads drawn from the pack.
%
%   aux = P50B_AuxiliaryLoads() returns the low-voltage load model for
%   the Competr control unit, hydraulic actuators and pumps, all of which
%   are ultimately supplied from the traction pack through the 1 kW
%   DC/DC converter.
%
%   WHY AUXILIARY LOAD BELONGS IN AN ENERGY MODEL
%   ---------------------------------------------
%   In a Monaco-style endurance run the propulsion load is intermittent,
%   but the auxiliary load is not. Control electronics, the cooling pump
%   and the bilge pump run continuously, and their energy comes out of
%   the same 9.83 kWh.
%
%   Ignoring auxiliaries is the classic way to overestimate range. On
%   this pack a steady 150 W hotel load is 1.5% of total energy per
%   hour -- small per hour, but it never stops, and it is drawn even
%   while the boat is stationary on the start line.
%
%   The trim and steering actuators are different in character: high
%   peak current, very low duty cycle. They matter for DC/DC sizing and
%   for the 12 V bus, not for total energy.
%
%   ALL RATINGS BELOW ARE DATASHEET MAXIMA, NOT OPERATING POINTS
%   -----------------------------------------------------------
%   The Competr datasheet specifies driver capability -- what the
%   control unit can supply. Actual draw depends on the pumps chosen,
%   which the datasheet lists as "on request". Duty cycles are
%   engineering estimates for a race application.
%
%   See also P50B_DrivetrainModel, P50B_MissionProfile, P50B_Param.

    %% =========================================================
    % DC/DC CONVERTER -- DATASHEET
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
        aux = cached;
        return;
    end

    P.DCDC_RatedPower_W = P50B_FromFile("auxiliary.dcdc_rated_W");

    P.DCDC_OutputVoltage_V = P50B_FromFile("auxiliary.dcdc_output_V");

    P.DCDC_Efficiency = P50B_FromFile("auxiliary.dcdc_efficiency");

    P.DCDC_StandbyPower_W = P50B_FromFile("auxiliary.dcdc_standby_W");

    %% =========================================================
    % CONTROL UNIT -- DATASHEET SUPPLY, ESTIMATED DRAW
    %% =========================================================

    P.ControlUnit_SupplyVoltage_V = P50B_FromFile("auxiliary.dcdc_output_V");

    P.ControlUnit_Power_W = P50B_FromFile("auxiliary.control_unit_W");

    P.ControlUnit_DutyCycle = P50B_FromFile("auxiliary.control_unit_duty");

    %% =========================================================
    % COOLING PUMP
    %
    % Driver rated 12 V / 15 A low-side per the datasheet. The
    % motor and inverter are water cooled, so this runs whenever
    % the drivetrain is producing meaningful power.
    %% =========================================================

    P.CoolingPump_DriverRating_A = P50B_FromFile("auxiliary.cooling_pump_driver_A");

    P.CoolingPump_Power_W = P50B_FromFile("auxiliary.cooling_pump_W");

    P.CoolingPump_DutyCycle = P50B_FromFile("auxiliary.cooling_pump_duty");

    %% =========================================================
    % BILGE PUMP
    %% =========================================================

    P.BilgePump_DriverRating_A = P50B_FromFile("auxiliary.bilge_pump_driver_A");

    P.BilgePump_Power_W = P50B_FromFile("auxiliary.bilge_pump_W");

    P.BilgePump_DutyCycle = P50B_FromFile("auxiliary.bilge_pump_duty");

    %% =========================================================
    % TRIM ACTUATOR -- DATASHEET
    %
    % Hydraulic, electroactuated, driven by an H-bridge rated
    % 12 V / 40 A. Trim angle range -5 to +30 degrees.
    %% =========================================================

    P.TrimPump_DriverRating_A = P50B_FromFile("auxiliary.trim_pump_driver_A");

    P.TrimPump_PeakPower_W = P50B_Param(480,"W","CALCULATED", ...
        "Note","12 V x 40 A driver maximum. Actual pump draw " + ...
               "depends on the unit selected.");

    P.TrimPump_DutyCycle = P50B_FromFile("auxiliary.trim_pump_duty");

    P.TrimAngleMin_deg = P50B_FromFile("auxiliary.trim_angle_min_deg");
    P.TrimAngleMax_deg = P50B_FromFile("auxiliary.trim_angle_max_deg");

    %% =========================================================
    % STEERING ACTUATOR -- DATASHEET
    %% =========================================================

    P.SteeringPump_DriverRating_A = P50B_FromFile("auxiliary.steering_pump_driver_A");

    P.SteeringPump_PeakPower_W = P50B_Param(480,"W","CALCULATED");

    P.SteeringPump_DutyCycle = P50B_FromFile("auxiliary.steering_pump_duty");

    P.SteeringAngleMin_deg = P50B_FromFile("auxiliary.steer_angle_min_deg");
    P.SteeringAngleMax_deg = P50B_FromFile("auxiliary.steer_angle_max_deg");

    %% =========================================================
    % INSTRUMENTATION AND HOTEL
    %% =========================================================

    P.Instrumentation_Power_W = P50B_FromFile("auxiliary.instrumentation_W");

    P.Instrumentation_DutyCycle = P50B_FromFile("auxiliary.instrumentation_duty");

    %% =========================================================
    % AGGREGATE LOADS
    %% =========================================================

    %% ---------------------------------------------------------
    % Continuous average 12 V load
    %
    % Duty-cycle weighted. This is the number that consumes
    % energy over a mission.
    %% ---------------------------------------------------------

    avgLoad = ...
        P.ControlUnit_Power_W.Value    * P.ControlUnit_DutyCycle.Value + ...
        P.CoolingPump_Power_W.Value    * P.CoolingPump_DutyCycle.Value + ...
        P.BilgePump_Power_W.Value      * P.BilgePump_DutyCycle.Value + ...
        P.TrimPump_PeakPower_W.Value   * P.TrimPump_DutyCycle.Value + ...
        P.SteeringPump_PeakPower_W.Value * P.SteeringPump_DutyCycle.Value + ...
        P.Instrumentation_Power_W.Value * P.Instrumentation_DutyCycle.Value;

    P.AverageLoad12V_W = P50B_Param(avgLoad,"W","CALCULATED", ...
        "Note","Duty-cycle weighted mean 12 V draw.");

    %% ---------------------------------------------------------
    % Worst-case simultaneous 12 V load
    %
    % Everything on at once. This is what sizes the DC/DC and
    % checks it against its 1 kW rating.
    %% ---------------------------------------------------------

    peakLoad = ...
        P.ControlUnit_Power_W.Value + ...
        P.CoolingPump_Power_W.Value + ...
        P.BilgePump_Power_W.Value + ...
        P.TrimPump_PeakPower_W.Value + ...
        P.SteeringPump_PeakPower_W.Value + ...
        P.Instrumentation_Power_W.Value;

    P.PeakLoad12V_W = P50B_Param(peakLoad,"W","CALCULATED", ...
        "Note","All loads simultaneous. Compare against the 1 kW " + ...
               "DC/DC rating -- see the headroom check below.");

    P.DCDC_HeadroomAtPeak_W = P50B_Param( ...
        P.DCDC_RatedPower_W.Value - peakLoad, ...
        "W","CALCULATED", ...
        "Note","Negative means simultaneous trim and steering " + ...
               "actuation would exceed the DC/DC rating and must " + ...
               "be prevented in control software or absorbed by " + ...
               "the 12 V battery.");

    %% ---------------------------------------------------------
    % Load referred to the traction pack
    %% ---------------------------------------------------------

    P.AverageLoadFromPack_W = P50B_Param( ...
        avgLoad / P.DCDC_Efficiency.Value + ...
        P.DCDC_StandbyPower_W.Value, ...
        "W","CALCULATED", ...
        "Note","Average 12 V load referred through DC/DC efficiency, " + ...
               "plus converter standby. This is what the pack sees.");

    %% =========================================================
    % PUBLISH BOTH LAYERS
    %% =========================================================

    aux.P = P;

    plain = P50B_Unwrap(P);

    fn = fieldnames(plain);

    for k = 1:numel(fn)
        aux.(fn{k}) = plain.(fn{k});
    end

    %% =========================================================
    % STORE
    %% =========================================================

    cached      = aux;
    cachedStamp = stamp;

end

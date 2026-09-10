function data = P50B_CellData(varargin)
%P50B_CELLDATA  Molicel INR-21700-P50B cell definition.
%
%   data = P50B_CellData() returns the full parameter set for a single
%   Molicel INR-21700-P50B cylindrical cell, including the Simscape
%   Battery cell object used to build the pack.
%
%   The returned struct has three layers:
%
%     data.<Name>     Bare numeric values, for direct use in
%                     calculations. Example: data.Capacity_Ah.
%
%     data.P.<Name>   The same values wrapped by P50B_Param, carrying
%                     unit, source and note. Example:
%                     data.P.Capacity_Ah.Source -> "DATASHEET".
%
%     data.Cell       The simscape.battery.builder.Cell object.
%
%   Every number in data.P is traceable. Run P50B_ProvenanceReport to
%   see which values are datasheet-backed and which are estimates.
%
%   CELL CHEMISTRY NOTE
%   -------------------
%   The P50B is a high-power NMC 21700. It is rated for 60 A continuous
%   discharge (12 C), which is far above anything this pack will demand:
%   at the Monaco 25 kW limit the 21P group draws 12.7 A per cell (2.5 C).
%   The cell is therefore not the limiting element in this design; the
%   interconnect and the thermal path are.
%
%   data = P50B_CellData("Reload",true) bypasses the cache.
%
%   See also P50B_OCV, P50B_DCIR, P50B_CellLimits, P50B_Param.

    %% =========================================================
    % CACHE
    %
    % Building the Simscape Battery cell object costs several
    % seconds, and this function is called from almost everywhere.
    % Before caching, a single TEST_ALL run spent most of its time
    % rebuilding an identical object dozens of times.
    %
    % The cache is invalidated on the parameter file's timestamp,
    % so editing volare_params.json still takes effect immediately.
    % Pass "Reload",true to force a rebuild.
    %% =========================================================

    persistent cached cachedStamp

    jsonFile = fullfile(P50B_ProjectRoot(),"params","volare_params.json");

    derivedFile = fullfile(P50B_ProjectRoot(), ...
        "params","cells","p50b_derived.json");

    stamp = "";

    if isfile(jsonFile)
        d = dir(jsonFile);
        stamp = stamp + string(d.datenum);
    end

    if isfile(derivedFile)
        d = dir(derivedFile);
        stamp = stamp + "|" + string(d.datenum);
    end

    forceReload = false;

    for k = 1:2:numel(varargin)
        if string(varargin{k}) == "Reload"
            forceReload = logical(varargin{k+1});
        end
    end

    if ~isempty(cached) && isequal(cachedStamp,stamp) && ~forceReload
        data = cached;
        return;
    end

    %% =========================================================
    % LOAD FROM THE SHARED PARAMETER FILE
    %
    % Every scalar below comes from params/volare_params.json,
    % which Python and the Mission Control browser engine also
    % read. Nothing here is hard-coded, so a change made once
    % reaches all three models.
    %
    % Curve data (OCV, R0(SOC,T), entropic dU/dT) comes from
    % params/cells/p50b_derived.json via P50B_OCV and P50B_DCIR.
    %% =========================================================

    Par = P50B_LoadParams();

    C = Par.cell;

    %% =========================================================
    % IDENTIFICATION
    %% =========================================================

    data.Manufacturer = C.manufacturer.Value;
    data.Model        = C.part_number.Value;
    data.Chemistry    = C.chemistry.Value;
    data.Format       = "21700 cylindrical";

    data.DatasheetRevision = "Molicel INR-21700-P50B product data sheet";

    data.ParameterSource = "params/volare_params.json";

    %% =========================================================
    % SCALARS, WITH PROVENANCE CARRIED THROUGH
    %
    % The parameter file already wraps each value with its unit
    % and source, so they are used directly rather than being
    % re-declared here.
    %% =========================================================

    P.Diameter_m = C.diameter_m;
    P.Height_m   = C.height_m;

    P.Radius_m = P50B_Param(C.diameter_m.Value/2,"m","CALCULATED", ...
        "Note","diameter_m / 2.");

    P.Mass_kg = C.mass_kg;

    P.Capacity_Ah         = C.capacity_Ah;
    P.CapacityMinimum_Ah  = C.capacity_min_Ah;
    P.NominalVoltage_V    = C.v_nominal_V;
    P.MaxVoltage_V        = C.v_max_V;
    P.MinVoltage_V        = C.v_min_V;
    P.NominalEnergy_Wh    = C.energy_nominal_Wh;

    P.MaxContinuousCurrent_A = C.i_max_discharge_A;
    P.MaxChargeCurrent_A     = C.i_max_charge_A;

    P.ACImpedance1kHz_Ohm = C.ac_impedance_1kHz_ohm;
    P.DCIR_Ohm            = C.dcir_ref_ohm;

    P.TempDischargeMin_C = C.T_discharge_min_C;
    P.TempDischargeMax_C = C.T_discharge_max_C;
    P.TempChargeMin_C    = C.T_charge_min_C;
    P.TempChargeMax_C    = C.T_charge_max_C;
    P.TempCutOff_C       = C.T_cutoff_C;
    P.TempDesignTarget_C = C.T_warn_C;

    P.SpecificHeat_J_kgK = C.cp_J_kgK;

    P.ThermalConductivityRadial_W_mK = C.k_radial_W_mK;
    P.ThermalConductivityAxial_W_mK  = C.k_axial_W_mK;

    P.R_core_can_KW      = C.R_core_can_KW;
    P.CoreMassFraction   = C.core_mass_fraction;

    P.R1_ref_Ohm  = C.R1_ref_ohm;
    P.Tau1_s      = C.tau1_s;
    P.R2_ref_Ohm  = C.R2_ref_ohm;
    P.Tau2_s      = C.tau2_s;
    P.Ea_over_R_K = C.Ea_over_R_K;

    P.UsableSOCMin = C.usable_soc_min;
    P.UsableSOCMax = C.usable_soc_max;

    %% =========================================================
    % DERIVED QUANTITIES
    %% =========================================================

    P.ThermalMass_J_K = P50B_Param( ...
        P.Mass_kg.Value * P.SpecificHeat_J_kgK.Value, ...
        "J/K","CALCULATED", ...
        "Note","Mass x specific heat. Sets the thermal time constant.");

    P.SurfaceArea_m2 = P50B_Param( ...
        pi * P.Diameter_m.Value * P.Height_m.Value, ...
        "m^2","CALCULATED", ...
        "Note","Cylindrical side wall only, excludes end caps.");

    P.Volume_m3 = P50B_Param( ...
        pi * P.Radius_m.Value^2 * P.Height_m.Value, ...
        "m^3","CALCULATED");

    P.SpecificEnergy_Wh_kg = P50B_Param( ...
        P.NominalEnergy_Wh.Value / P.Mass_kg.Value, ...
        "W*hr/kg","CALCULATED");

    %% =========================================================
    % PUBLISH BOTH LAYERS
    %
    % data.P.<Name>  -> provenance-tagged
    % data.<Name>    -> bare numeric, for calculation code
    %% =========================================================

    data.P = P;

    plain = P50B_Unwrap(P);

    fn = fieldnames(plain);

    for k = 1:numel(fn)
        data.(fn{k}) = plain.(fn{k});
    end

    %% =========================================================
    % BACKWARD-COMPATIBILITY ALIASES
    %
    % Earlier revisions of this project referred to the cell
    % voltages as data.Vnom / data.Vmax / data.Vmin and to the
    % geometry as data.Diameter / data.Height / data.Radius.
    % Those short names are kept as aliases so that any script
    % still using them keeps working.
    %
    % New code should use the explicit _V and _m suffixed names,
    % which state their units.
    %% =========================================================

    data.Vnom = data.NominalVoltage_V;
    data.Vmax = data.MaxVoltage_V;
    data.Vmin = data.MinVoltage_V;

    data.Diameter = data.Diameter_m;
    data.Height   = data.Height_m;
    data.Radius   = data.Radius_m;

    %% =========================================================
    % LOOK-UP TABLES
    %% =========================================================

    data.OCV  = P50B_OCV();
    data.DCIR = P50B_DCIR();

    %% =========================================================
    % SIMSCAPE BATTERY CELL OBJECT
    %% =========================================================

    geometry = batteryCylindricalGeometry( ...
        simscape.Value(data.Height_m,"m"), ...
        simscape.Value(data.Radius_m,"m"));

    data.Cell = batteryCell(geometry);

    data.Cell.Mass = ...
        simscape.Value(data.Mass_kg,"kg");

    data.Cell.Capacity = ...
        simscape.Value(data.Capacity_Ah,"A*hr");

    %% ---------------------------------------------------------
    % Thermal model
    %
    % LumpedThermalMass treats the cell as a single node. That is
    % the right resolution for pack-level energy and temperature
    % work; it will not resolve the radial gradient inside a cell.
    %% ---------------------------------------------------------

    data.Cell.CellModelOptions.BlockParameters.ThermalModel = ...
        "LumpedThermalMass";

    %% =========================================================
    % STORE
    %% =========================================================

    cached      = data;
    cachedStamp = stamp;

end

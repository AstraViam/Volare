function harness = P50B_HarnessData()
%P50B_HARNESSDATA  High-voltage harness between pack and inverter.
%
%   harness = P50B_HarnessData() returns the parameter set for the DC
%   cabling, contactor, fuse and connector path linking the 26S21P pack
%   to the inverter.
%
%   WHY THIS IS A SEPARATE FILE
%   ---------------------------
%   The busbar model in 03_mechanical covers copper *inside* the pack:
%   cell-to-cell collectors and group-to-group series links. It stops at
%   the pack terminals.
%
%   Everything between the pack terminals and the inverter -- cable,
%   fuse, contactor, connectors -- is series resistance in exactly the
%   same circuit, and at 375 A it is not negligible. Leaving it out
%   makes the pack look better than the vehicle actually is.
%
%   At the Competr 375 A continuous rating, every milliohm anywhere in
%   this path costs 141 W and heats something.
%
%   See also P50B_Busbars, P50B_DrivetrainModel, P50B_Param.

    %% =========================================================
    % CABLE
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
        harness = cached;
        return;
    end

    P.CableLengthPositive_m = P50B_FromFile("harness.cable_length_pos_m");

    P.CableLengthNegative_m = P50B_FromFile("harness.cable_length_neg_m");

    P.CableCrossSection_mm2 = P50B_FromFile("harness.cable_area_mm2");

    P.CableConductor = P50B_FromFile("harness.cable_conductor");

    P.CableInsulationTempRating_C = P50B_FromFile("harness.cable_insulation_T_C");

    %% =========================================================
    % COPPER PROPERTIES
    %% =========================================================

    P.CopperResistivity20C_Ohm_m = P50B_FromFile("busbar.cu_rho_20C_ohm_m");

    P.CopperTempCoefficient_perK = P50B_FromFile("busbar.cu_tempco_per_K");

    P.CableOperatingTemp_C = P50B_FromFile("harness.cable_operating_T_C");

    %% ---------------------------------------------------------
    % Stranding derate
    %
    % A stranded conductor has slightly less copper in its stated
    % cross-section than a solid one, and the strands are longer
    % than the cable because of the lay.
    %% ---------------------------------------------------------

    P.StrandingFactor = P50B_FromFile("harness.stranding_factor");

    %% =========================================================
    % DERIVED CABLE RESISTANCE
    %% =========================================================

    rho20 = P.CopperResistivity20C_Ohm_m.Value;

    alpha = P.CopperTempCoefficient_perK.Value;

    Top   = P.CableOperatingTemp_C.Value;

    rhoHot = rho20 * (1 + alpha*(Top - 20));

    A = P.CableCrossSection_mm2.Value * 1e-6;

    Ltotal = P.CableLengthPositive_m.Value + ...
             P.CableLengthNegative_m.Value;

    Rcable = rhoHot * Ltotal / A * P.StrandingFactor.Value;

    P.CableResistance_Ohm = P50B_Param(Rcable,"Ohm","CALCULATED", ...
        "Note","Both legs, at operating temperature, with stranding " + ...
               "derate. This is the round-trip resistance.");

    %% =========================================================
    % PROTECTION AND SWITCHGEAR
    %% =========================================================

    P.FuseRating_A = P50B_FromFile("harness.fuse_rating_A");

    P.FuseResistance_Ohm = P50B_FromFile("harness.fuse_resistance_ohm");

    P.ContactorResistance_Ohm = P50B_FromFile("harness.contactor_resistance_ohm");

    P.ContactorCoilPower_W = P50B_FromFile("harness.contactor_coil_W");

    %% =========================================================
    % CONNECTORS AND JOINTS
    %
    % Bolted and mated joints are the most commonly forgotten
    % resistance in a HV path, and the most likely to degrade.
    %% =========================================================

    P.NumberOfBoltedJoints = P50B_FromFile("harness.n_bolted_joints");

    P.ResistancePerBoltedJoint_Ohm = P50B_FromFile("harness.R_per_bolted_joint_ohm");

    P.NumberOfMatedConnectors = P50B_FromFile("harness.n_mated_connectors");

    P.ResistancePerMatedConnector_Ohm = P50B_FromFile("harness.R_per_connector_ohm");

    %% =========================================================
    % TOTAL HARNESS RESISTANCE
    %% =========================================================

    Rjoints = P.NumberOfBoltedJoints.Value * ...
              P.ResistancePerBoltedJoint_Ohm.Value;

    Rconn = P.NumberOfMatedConnectors.Value * ...
            P.ResistancePerMatedConnector_Ohm.Value;

    Rtotal = Rcable + ...
             P.FuseResistance_Ohm.Value + ...
             P.ContactorResistance_Ohm.Value + ...
             Rjoints + ...
             Rconn;

    P.JointResistanceTotal_Ohm = ...
        P50B_Param(Rjoints,"Ohm","CALCULATED");

    P.ConnectorResistanceTotal_Ohm = ...
        P50B_Param(Rconn,"Ohm","CALCULATED");

    P.TotalResistance_Ohm = P50B_Param(Rtotal,"Ohm","CALCULATED", ...
        "Note","Pack terminals to inverter DC terminals, round trip.");

    %% =========================================================
    % AMPACITY CHECK
    %
    % Resistance is not the only constraint. The cable must also
    % be able to carry the current without exceeding its
    % insulation rating.
    %
    % Free-air ampacity for tinned copper in a 105 degC insulation
    % is roughly 4.5 A/mm^2 for large sections in a ventilated
    % run. Marine installations are rarely ventilated, so a
    % bundling and ambient derate is applied.
    %% =========================================================

    P.BaseAmpacity_A_per_mm2 = P50B_FromFile("harness.base_ampacity_A_mm2");

    P.BundlingDerate = P50B_FromFile("harness.bundling_derate");

    P.AmbientDerate = P50B_FromFile("harness.ambient_derate");

    ampacity = P.CableCrossSection_mm2.Value * ...
               P.BaseAmpacity_A_per_mm2.Value * ...
               P.BundlingDerate.Value * ...
               P.AmbientDerate.Value;

    P.CableAmpacity_A = P50B_Param(ampacity,"A","CALCULATED", ...
        "Note","Derated continuous rating of the chosen cable.");

    %% =========================================================
    % PUBLISH BOTH LAYERS
    %% =========================================================

    harness.P = P;

    plain = P50B_Unwrap(P);

    fn = fieldnames(plain);

    for k = 1:numel(fn)
        harness.(fn{k}) = plain.(fn{k});
    end

    %% =========================================================
    % STORE
    %% =========================================================

    cached      = harness;
    cachedStamp = stamp;

end

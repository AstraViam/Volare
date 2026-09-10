function Budget = P50B_MassBudget(varargin)
%P50B_MASSBUDGET  Weight budget for ENERGY_REQ_48 and ENERGY_REQ_135.
%
%   Budget = P50B_MassBudget() builds the boat's mass line by line and
%   checks it against the 250 kg limit.
%
%   OPTIONS
%     "Geometry"    struct from P50B_Geometry
%     "Motor"       struct from P50B_MotorData
%     "PilotMass_kg" override the pilot's ready-to-sail mass
%     "Verbose"     logical, default true
%
%   HOW THE RULE ACTUALLY READS
%   ---------------------------
%   ENERGY_REQ_48: "The overall weight excluding the hulls shall not
%   exceed 250 kg." And the note: "The boat will be weighted with the
%   hulls and the pilot. The hulls are supposed to be 65 +/- 1 kg."
%
%   So the test on the day is
%
%       (what the scales read, hulls and pilot included) - 65 <= 250
%
%   and the pilot counts against the 250. That is easy to get wrong in
%   the optimistic direction, because "excluding the hulls" reads like
%   an invitation to exclude the pilot too. It is not.
%
%   ENERGY_REQ_135 then requires the pilot, ready to sail with overalls,
%   helmet, lifejacket, shoes and communications, to weigh at least
%   60 kg; a lighter pilot means ballast, and the ballast counts too. If
%   there is more than one pilot the rule says to size the ballast on the
%   LIGHTEST of them, so that is what is used here.
%
%   WHERE THE NUMBERS COME FROM
%   ---------------------------
%   Lines the model computes -- the pack, the outboard, the trim
%   assembly -- are read from the model, not from the parameter file, so
%   they cannot drift away from the design they describe. Everything
%   else is a declared allowance in the mass section of
%   params/volare_params.json, and every one of those is an ASSUMPTION
%   until the part is on a scale.
%
%   WHAT TO EXPECT
%   --------------
%   This budget closes, but not by much. After stored energy it is the
%   tightest constraint in the project, and unlike stored energy it is
%   made of two dozen estimates rather than one exact calculation. An
%   overweight boat is not allowed in the water at all, so the margin
%   here is worth more attention than its size suggests.
%
%   See also P50B_MonacoCompliance, P50B_Geometry, P50B_MotorData.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct( ...
        "Geometry",[], ...
        "Motor",[], ...
        "PilotMass_kg",[], ...
        "Verbose",true);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_MassBudget:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if isempty(opts.Geometry); opts.Geometry = P50B_Geometry(); end
    if isempty(opts.Motor);    opts.Motor    = P50B_MotorData(); end

    G     = opts.Geometry;
    motor = opts.Motor;

    P = P50B_LoadParams("Plain",true);

    M = P.mass;

    %% =========================================================
    % LINES THE MODEL KNOWS
    %% =========================================================

    packMass_kg = P50B_Value(G.Mass.TotalEstimate);

    outboardMass_kg = P50B_Value(motor.Mass_kg);

    trimMass_kg = P.motor.trim_mass_kg;

    if isempty(opts.PilotMass_kg)
        pilotMass_kg = P.boat.pilot_mass_kg;
    else
        pilotMass_kg = opts.PilotMass_kg;
    end

    %% =========================================================
    % ENERGY_REQ_135 -- BALLAST
    %
    % Computed, not declared. A pilot at or above the minimum
    % needs none; a lighter one is ballasted up to it, and that
    % ballast is mass the boat has to carry against the 250 kg.
    %% =========================================================

    pilotMin_kg = P.rules.pilot_min_mass_kg;

    ballast_kg = max(0, pilotMin_kg - pilotMass_kg);

    %% =========================================================
    % THE BUDGET
    %% =========================================================

    itemNames = [ ...
        "Battery pack"
        "Outboard"
        "Trim assembly"
        "Inverter / ESC"
        "HV harness (cable)"
        "Energy container"
        "HV switchgear"
        "Cooling system"
        "LV system"
        "Cockpit structure"
        "Seat"
        "Steering and controls"
        "Beam clamps and fasteners"
        "Safety equipment"
        "Organiser equipment"
        "Pilot, ready to sail"
        "Ballast"
        "Contingency"];

    itemMass = [ ...
        packMass_kg
        outboardMass_kg
        trimMass_kg
        M.inverter_kg
        M.hv_harness_kg
        M.energy_container_kg
        M.hv_switchgear_kg
        M.cooling_system_kg
        M.lv_system_kg
        M.cockpit_structure_kg
        M.seat_kg
        M.steering_control_kg
        M.fasteners_clamps_kg
        M.safety_equipment_kg
        M.organiser_equipment_kg
        pilotMass_kg
        ballast_kg
        M.contingency_kg];

    itemSource = [ ...
        "model"
        "datasheet"
        "datasheet"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "allowance"
        "assumption"
        "ENERGY_REQ_135"
        "reserve"];

    Items = table(itemNames,itemMass,itemSource, ...
        VariableNames=["Item","Mass_kg","Source"]);

    Items.Percent = 100 * Items.Mass_kg / sum(Items.Mass_kg);

    %% =========================================================
    % THE CHECK
    %% =========================================================

    limit_kg = P.rules.mass_limit_excl_hulls_kg;

    hull_kg  = P.rules.hull_mass_kg;
    hullTol_kg = P.rules.hull_mass_tol_kg;

    exclHulls_kg = sum(Items.Mass_kg);

    margin_kg = limit_kg - exclHulls_kg;

    B = struct();

    B.Items            = Items;
    B.ExcludingHulls_kg = exclHulls_kg;
    B.Limit_kg         = limit_kg;
    B.Margin_kg        = margin_kg;
    B.MarginPercent    = 100*margin_kg/limit_kg;
    B.Pass             = exclHulls_kg <= limit_kg;

    B.HullMass_kg      = hull_kg;
    B.HullTolerance_kg = hullTol_kg;

    %% ---------------------------------------------------------
    % What the scales will read, and the worst case
    %
    % The hulls are 65 kg "supposed to be", plus or minus 1 kg.
    % The deduction on the day is presumably the nominal 65, so a
    % light set of hulls does not help and a heavy set does not
    % hurt -- but if the deduction is the MEASURED hull mass then
    % a light set costs a kilogram of margin. Both are reported
    % because the rule does not say which it is.
    %% ---------------------------------------------------------

    B.WeighInNominal_kg = exclHulls_kg + hull_kg;

    B.WorstCaseMargin_kg = margin_kg - hullTol_kg;

    B.PassWorstCase = B.WorstCaseMargin_kg >= 0;

    %% ---------------------------------------------------------
    % Floating mass, which is what the hydrodynamics wants
    %% ---------------------------------------------------------

    B.FloatingMass_kg = B.WeighInNominal_kg;

    B.ParameterDisplacement_kg = P.boat.displacement_kg;

    %% ---------------------------------------------------------
    % boat.displacement_kg is the mass at the CAP -- 250 kg of
    % cockpit plus 65 kg of supplied hulls -- and that is the
    % right target for the hydrodynamics, because designing the
    % hull around an illegal mass optimises a boat that cannot
    % race.
    %
    % So the test is not equality. It is whether the DESIGN has
    % drifted above the cap, which is a mass problem to fix
    % rather than a parameter to update.
    %% ---------------------------------------------------------

    B.DisplacementAtCap_kg = limit_kg + hull_kg;

    B.DisplacementConsistent = ...
        B.FloatingMass_kg <= B.DisplacementAtCap_kg + 1e-9;

    B.DisplacementExcess_kg = ...
        B.FloatingMass_kg - B.DisplacementAtCap_kg;

    %% ---------------------------------------------------------
    % ENERGY_REQ_135
    %% ---------------------------------------------------------

    B.Pilot = struct( ...
        "Mass_kg",     pilotMass_kg, ...
        "Minimum_kg",  pilotMin_kg, ...
        "Ballast_kg",  ballast_kg, ...
        "Compliant",   pilotMass_kg + ballast_kg >= pilotMin_kg);

    %% ---------------------------------------------------------
    % How much of the budget is guesswork?
    %% ---------------------------------------------------------

    isAllowance = Items.Source == "allowance";

    B.AllowanceMass_kg = sum(Items.Mass_kg(isAllowance));

    B.AllowanceFraction = B.AllowanceMass_kg / exclHulls_kg;

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose

        fprintf("\n");
        fprintf("================================================================\n");
        fprintf(" MASS BUDGET  --  ENERGY_REQ_48 and ENERGY_REQ_135\n");
        fprintf("================================================================\n\n");

        fprintf("  %-28s %9s %7s  %s\n","ITEM","kg","%","SOURCE");
        fprintf("  %s\n",repmat('-',1,60));

        [~,order] = sort(Items.Mass_kg,"descend");

        for k = order'

            if Items.Mass_kg(k) == 0
                continue;
            end

            fprintf("  %-28s %9.1f %6.1f%%  %s\n", ...
                Items.Item(k),Items.Mass_kg(k),Items.Percent(k), ...
                Items.Source(k));

        end

        fprintf("  %s\n",repmat('-',1,60));
        fprintf("  %-28s %9.1f\n","EXCLUDING HULLS",exclHulls_kg);
        fprintf("  %-28s %9.1f\n","Limit (ENERGY_REQ_48)",limit_kg);
        fprintf("  %-28s %9.1f  (%.1f%%)\n","MARGIN",margin_kg, ...
            B.MarginPercent);

        fprintf("\n  Hulls and beams            %9.1f  +/- %.0f kg\n", ...
            hull_kg,hullTol_kg);
        fprintf("  Scales will read           %9.1f\n",B.WeighInNominal_kg);

        if B.Pass
            fprintf("\n  ENERGY_REQ_48: PASS with %.1f kg to spare.\n", ...
                margin_kg);
        else
            fprintf("\n  ENERGY_REQ_48: FAIL by %.1f kg. " + ...
                "An overweight boat is not\n",-margin_kg);
            fprintf("  allowed in the water.\n");
        end

        if B.Pass && B.MarginPercent < 5
            fprintf("  The margin is under 5%%, and %.0f%% of the budget " + ...
                "is allowances\n",100*B.AllowanceFraction);
            fprintf("  rather than weighed parts. Weigh things early.\n");
        end

        fprintf("\n  ENERGY_REQ_135: pilot %.0f kg ready to sail, " + ...
            "minimum %.0f kg.\n",pilotMass_kg,pilotMin_kg);

        if ballast_kg > 0
            fprintf("  %.1f kg of ballast required, and it counts " + ...
                "against the 250 kg.\n",ballast_kg);
            fprintf("  Size it on the LIGHTEST pilot, as the rule says.\n");
        else
            fprintf("  No ballast required. If a lighter pilot is " + ...
                "entered, rerun this\n");
            fprintf("  with PilotMass_kg -- every kilogram under 60 " + ...
                "becomes ballast.\n");
        end

        if ~B.DisplacementConsistent
            fprintf("\n  NOTE: boat.displacement_kg is %.0f kg but this " + ...
                "budget floats\n",B.ParameterDisplacement_kg);
            fprintf("  %.0f kg. The hydrodynamics is being run at the " + ...
                "wrong mass.\n",B.FloatingMass_kg);
        end

        fprintf("================================================================\n\n");

    end

    Budget = B;

end

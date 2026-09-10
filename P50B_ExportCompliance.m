function outFile = P50B_ExportCompliance(varargin)
%P50B_EXPORTCOMPLIANCE  Write the compliance result for Mission Control.
%
%   outFile = P50B_ExportCompliance() runs the full compliance check, the
%   mass budget and the performance model, and writes
%   output/P50B_Compliance.json.
%
%   OPTIONS
%     "Out"         output path
%     "Compliance"  struct from P50B_MonacoCompliance
%     "Verbose"     logical, default true
%
%   WHY THE DASHBOARD DOES NOT COMPUTE THIS ITSELF
%   ----------------------------------------------
%   Mission Control has its own physics engine, deliberately: it has to
%   run a boat forward in time in a browser with no MATLAB anywhere near
%   it. But compliance is not physics, it is a reading of a rule book,
%   and a second reading of a rule book is not a cross-check -- it is a
%   second thing that can be wrong, in a place nobody looks.
%
%   So the rules are read once, here, and the dashboard displays the
%   result. tools/build_mission_control.py picks this file up and bakes
%   it into the page; if it is missing, the page falls back to the small
%   subset Python can recompute and says so.
%
%   Which means: after changing anything that affects compliance, run
%   this and then rebuild the dashboard, or the dashboard is showing an
%   older boat than the model is.
%
%   See also P50B_MonacoCompliance, P50B_MassBudget, P50B_BoatPerformance.

    opts = struct("Out","","Compliance",[],"Verbose",true);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_ExportCompliance:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if isempty(opts.Compliance)
        C = P50B_MonacoCompliance("Verbose",false);
    else
        C = opts.Compliance;
    end

    if strlength(string(opts.Out)) > 0
        outFile = string(opts.Out);
    else
        outFile = fullfile(P50B_ProjectRoot(),"output","P50B_Compliance.json");
    end

    %% =========================================================
    % CHECKS
    %% =========================================================

    T = C.Checks;

    checks = cell(height(T),1);

    for k = 1:height(T)

        checks{k} = struct( ...
            "req",     char(T.Req(k)), ...
            "title",   char(T.Title(k)), ...
            "status",  char(T.Status(k)), ...
            "finding", char(T.Finding(k)), ...
            "action",  char(T.Action(k)));

    end

    %% =========================================================
    % SUMMARY
    %% =========================================================

    out = struct();

    out.rulesDocument = char(C.RulesVersion);
    out.rulesIssued   = char(C.RulesIssued);
    out.rulesFile     = char(C.RulesFile);

    out.generatedBy = "P50B_ExportCompliance";

    out.summary = struct( ...
        "total",     C.NumChecks, ...
        "pass",      C.NumPass, ...
        "fail",      C.NumFail, ...
        "action",    C.NumAction, ...
        "partial",   C.NumPartial, ...
        "checklist", C.NumChecklist, ...
        "compliant", C.Compliant);

    out.checks = checks;

    %% =========================================================
    % MASS BUDGET
    %% =========================================================

    if isfield(C,"MassBudget") && ~isempty(C.MassBudget)

        B = C.MassBudget;

        items = cell(height(B.Items),1);

        for k = 1:height(B.Items)
            items{k} = struct( ...
                "item",    char(B.Items.Item(k)), ...
                "kg",      B.Items.Mass_kg(k), ...
                "percent", B.Items.Percent(k), ...
                "source",  char(B.Items.Source(k)));
        end

        out.mass = struct( ...
            "items",            {items}, ...
            "excludingHulls_kg",B.ExcludingHulls_kg, ...
            "limit_kg",         B.Limit_kg, ...
            "margin_kg",        B.Margin_kg, ...
            "marginPercent",    B.MarginPercent, ...
            "hull_kg",          B.HullMass_kg, ...
            "weighIn_kg",       B.WeighInNominal_kg, ...
            "allowanceFraction",B.AllowanceFraction, ...
            "pass",             B.Pass, ...
            "pilotMass_kg",     B.Pilot.Mass_kg, ...
            "pilotMin_kg",      B.Pilot.Minimum_kg, ...
            "ballast_kg",       B.Pilot.Ballast_kg);

    end

    %% =========================================================
    % PERFORMANCE
    %% =========================================================

    if isfield(C,"Performance") && ~isempty(C.Performance)

        Pf = C.Performance;

        out.performance = struct( ...
            "topSpeed_kmh",       Pf.TopSpeed_kmh, ...
            "topSpeed_knots",     Pf.TopSpeed_knots, ...
            "shaftCeiling_W",     Pf.ShaftPowerCeiling_W, ...
            "electricalLimit_W",  Pf.PowerCeiling.ElectricalLimit_W, ...
            "motorRPM",           Pf.TopSpeedMotorRPM, ...
            "motorTorque_Nm",     Pf.MotorTorqueAtTop_Nm, ...
            "motorSpeedLimit_rpm",Pf.MotorSpeedLimit_rpm, ...
            "motorTorqueLimit_Nm",Pf.MotorTorqueLimit_Nm, ...
            "drivetrainFeasible", Pf.DrivetrainFeasible, ...
            "propEfficiency",     Pf.TopSpeedPropEff, ...
            "targetSpeed_kmh",    Pf.TargetSpeed_kmh, ...
            "targetReachable",    Pf.TargetReachable, ...
            "minSpeedPower_W",    Pf.MinimumSpeed.ShaftPower_W, ...
            "minSpeedOK",         Pf.MinimumSpeed.Achievable, ...
            "reverseThrust_N",    Pf.Reverse.ThrustAstern_N, ...
            "reverseOK",          Pf.Reverse.Achievable);

        if ~isempty(Pf.BestRange)

            out.performance.bestRange_km    = Pf.BestRange.Range_km;
            out.performance.bestRangeSpeed_kmh = Pf.BestRange.Speed_kmh;
            out.performance.bestRangeWhPerKm = Pf.BestRange.Wh_per_km;

        end

        %% -----------------------------------------------------
        % A short speed / consumption table for the dashboard's
        % strategy view. Ten points is enough to draw a curve and
        % small enough not to bloat the page.
        %% -----------------------------------------------------

        R = Pf.Range;

        valid = find(~isnan(R.PackPower_W));

        if ~isempty(valid)

            pick = round(linspace(valid(1),valid(end),min(12,numel(valid))));

            pick = unique(pick);

            rows = cell(numel(pick),1);

            for k = 1:numel(pick)
                i = pick(k);
                rows{k} = struct( ...
                    "kmh",       R.Speed_kmh(i), ...
                    "packW",     R.PackPower_W(i), ...
                    "WhPerKm",   R.Wh_per_km(i), ...
                    "range_km",  R.Range_km(i), ...
                    "chainEff",  R.ChainEff(i));
            end

            out.performance.curve = rows;

        end

    end

    %% =========================================================
    % TELEMETRY CONTRACT -- ANNEX III AND IV
    %% =========================================================

    Pp = P50B_LoadParams("Plain",true);

    out.telemetry = struct( ...
        "protocol",      char(string(Pp.telemetry.api_protocol)), ...
        "method",        char(string(Pp.telemetry.api_method)), ...
        "path",          char(string(Pp.telemetry.api_path)), ...
        "contentType",   char(string(Pp.telemetry.api_content_type)), ...
        "periodSeconds", Pp.telemetry.post_period_s, ...
        "tempChannels",  Pp.telemetry.n_temperature_channels, ...
        "supplyV",       Pp.telemetry.supply_nominal_V, ...
        "supplyBudgetW", Pp.telemetry.supply_budget_W, ...
        "connector",     char(string(Pp.telemetry.connector_pn)), ...
        "pin1",          char(string(Pp.telemetry.connector_pin1)), ...
        "pin2",          char(string(Pp.telemetry.connector_pin2)));

    %% =========================================================
    % WRITE
    %% =========================================================

    folder = fileparts(outFile);

    if ~isfolder(folder)
        mkdir(folder);
    end

    fid = fopen(outFile,"w");

    if fid < 0
        error("P50B_ExportCompliance:CannotWrite", ...
            "Could not open %s for writing.",outFile);
    end

    fprintf(fid,"%s",jsonencode(out,"PrettyPrint",true));

    fclose(fid);

    if opts.Verbose

        fprintf("\nCompliance exported to:\n  %s\n",outFile);
        fprintf("  %d checks: %d pass, %d fail, %d to action, " + ...
            "%d checklist\n", ...
            C.NumChecks,C.NumPass,C.NumFail,C.NumAction,C.NumChecklist);
        fprintf("\nRebuild the dashboard to pick it up:\n");
        fprintf("  python tools/build_mission_control.py\n\n");

    end

end

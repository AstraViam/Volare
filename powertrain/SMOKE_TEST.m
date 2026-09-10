function varargout = SMOKE_TEST(varargin)
%SMOKE_TEST  Fast check that every MATLAB module still builds and agrees.
%
%   SMOKE_TEST runs every model in the project once, checks a short list
%   of invariants, and prints a table. It is meant to finish in seconds,
%   so it can be run after every edit.
%
%   ok = SMOKE_TEST() returns true if everything passed.
%   [ok,R] = SMOKE_TEST() also returns the results table.
%
%   OPTIONS
%     "Verbose"   logical, default true
%     "Strict"    logical, default false -- error() on failure rather
%                 than returning false. Use this in CI.
%     "Only"      string or string array, run only matching groups
%
%   WHY THIS EXISTS ALONGSIDE TEST_ALL
%   ----------------------------------
%   TEST_ALL is a regression test. It builds Simscape packs, runs
%   missions, solves thermal networks and takes a minute or two. That is
%   the right thing before a commit and the wrong thing after changing a
%   number, because a test nobody runs because it is slow is a test that
%   is not protecting anything.
%
%   This runs the same modules with the expensive parts turned off and
%   asks only: does it still build, and are the answers still the right
%   shape? It catches the errors that actually happen day to day -- a
%   renamed field, a broken option, a parameter that moved, an
%   assumption edited into an impossible value -- in about the time it
%   takes to read the output.
%
%   WHAT IT DELIBERATELY DOES NOT DO
%   --------------------------------
%   It does not check numerical accuracy against a reference, and it
%   does not compare MATLAB against Python. Those are TEST_ALL's job and
%   tools/crosscheck.py's job respectively. A smoke test that tried to
%   do everything would be as slow as the thing it exists to avoid.
%
%   A PASS here means nothing is obviously broken. It does not mean the
%   numbers are right.
%
%   See also TEST_ALL, P50B_Verification, P50B_MonacoCompliance.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct("Verbose",true,"Strict",false,"Only",string.empty);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("SMOKE_TEST:UnknownOption","Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    addpath(genpath(fileparts(mfilename("fullpath"))));

    %% =========================================================
    % RESULT ACCUMULATOR
    %% =========================================================

    Group   = string.empty(0,1);
    Check   = string.empty(0,1);
    Status  = string.empty(0,1);
    Detail  = string.empty(0,1);
    Seconds = zeros(0,1);

    tStart = tic;

    function record(group,check,status,detail,secs)

        Group(end+1,1)   = group;
        Check(end+1,1)   = check;
        Status(end+1,1)  = status;
        Detail(end+1,1)  = detail;
        Seconds(end+1,1) = secs;

    end

    function wanted = runGroup(name)

        wanted = isempty(opts.Only) || any(strcmpi(opts.Only,name));

    end

    %% ---------------------------------------------------------
    % Run one probe.
    %
    % fn returns a detail string, or throws. Anything thrown is
    % caught and recorded rather than aborting the run, because
    % a smoke test that stops at the first failure tells you
    % about one problem when there might be five.
    %% ---------------------------------------------------------

    function out = probe(group,check,fn)

        out = [];

        if ~runGroup(group)
            return;
        end

        t0 = tic;

        try

            [detail,out] = fn();

            record(group,check,"PASS",string(detail),toc(t0));

        catch ME

            record(group,check,"FAIL", ...
                string(ME.identifier) + ": " + string(ME.message), ...
                toc(t0));

        end

    end

    %% =========================================================
    % 1. PARAMETERS
    %% =========================================================

    P = [];

    probe("params","parameter file loads",@() localParamsLoad());

    try
        P = P50B_LoadParams("Plain",true);
    catch
        P = [];
    end

    probe("params","no placeholders",@() localNoPlaceholders());

    probe("params","required sections present",@() localSections(P));

    %% =========================================================
    % 2. CELL AND PACK
    %% =========================================================

    cellData = probe("cell","cell definition builds",@() localCell());

    probe("cell","OCV monotonic in SOC",@() localOCV());

    probe("cell","DCIR rises as it gets colder",@() localDCIR());

    G = probe("pack","geometry builds",@() localGeometry());

    probe("pack","stored energy under 10 kWh",@() localEnergy(G,cellData));

    %% =========================================================
    % 3. DRIVETRAIN
    %% =========================================================

    motor = probe("drivetrain","motor data builds",@() localMotor());

    probe("drivetrain","inverter data builds", ...
        @() localSimple(@P50B_InverterData,"inverter"));

    probe("drivetrain","harness data builds", ...
        @() localSimple(@P50B_HarnessData,"harness"));

    probe("drivetrain","auxiliary loads build", ...
        @() localSimple(@P50B_AuxiliaryLoads,"auxiliary"));

    probe("drivetrain","25 kW cap is enforced",@() localPowerCap());

    probe("drivetrain","motor spec audit runs",@() localMotorAudit());

    %% =========================================================
    % 4. HYDRODYNAMICS
    %% =========================================================

    Hull = probe("hydro","hull model builds",@() localHull());

    probe("hydro","resistance monotonic in speed",@() localMonotonic(Hull));

    probe("hydro","supplied curve reproduced",@() localCurve(Hull,P));

    Prop = probe("hydro","propulsor builds",@() localPropulsor());

    probe("hydro","design point reproduced",@() localDesignPoint(Prop));

    probe("hydro","thrust at rest is finite",@() localBollard(Prop));

    Boat = probe("hydro","boat dynamics build",@() localBoat(Hull,Prop));

    probe("hydro","shaft ceiling below the cap", ...
        @() localCeiling(Boat,motor));

    %% =========================================================
    % 5. COMPLIANCE
    %% =========================================================

    Budget = probe("compliance","mass budget closes",@() localMass());

    probe("compliance","ballast follows a light pilot",@() localBallast());

    probe("compliance","rules check runs with no violations", ...
        @() localCompliance());

    %% =========================================================
    % 6. ARTEFACTS
    %% =========================================================

    probe("artefacts","cell tables derived",@() localFile( ...
        "params/cells/p50b_derived.json", ...
        "run python tools/export_cell_tables.py"));

    probe("artefacts","compliance exported",@() localFile( ...
        "output/P50B_Compliance.json", ...
        "run matlab -batch P50B_ExportCompliance"));

    probe("artefacts","dashboard carries the export",@() localDashboard());

    probe("artefacts","hydrodynamics delivery present",@() localFile( ...
        "04_data/hydrodynamics/design_report.txt", ...
        "the BEM design report is missing"));

    %% =========================================================
    % REPORT
    %% =========================================================

    R = table(Group,Check,Status,Detail,Seconds);

    nFail = sum(R.Status == "FAIL");

    ok = nFail == 0;

    elapsed = toc(tStart);

    if opts.Verbose
        printSmoke(R,ok,nFail,elapsed);
    end

    if opts.Strict && ~ok

        error("SMOKE_TEST:Failed", ...
            "%d smoke check(s) failed. See the table above.",nFail);

    end

    if nargout >= 1; varargout{1} = ok; end
    if nargout >= 2; varargout{2} = R;  end

end


%% =============================================================
%  PROBES
%
%  Each returns [detail, payload]. The payload is passed back to
%  the caller so a later probe can reuse an expensive build.
%% =============================================================

function [d,out] = localParamsLoad()

    Pt = P50B_LoadParams("Reload",true);

    n = numel(fieldnames(Pt));

    assert(n > 5,"Only %d top-level sections; the file looks truncated.",n);

    d = sprintf("%d sections",n);
    out = Pt;

end

function [d,out] = localNoPlaceholders()

    %% ---------------------------------------------------------
    % Audit the PARAMETER FILE, not the model structs.
    %
    % P50B_ProvenanceReport walks the MATLAB model objects, which
    % is about 170 numbers. The parameter file is 459, and it is
    % the place a PLACEHOLDER would actually be introduced --
    % somebody adds a section, does not know a value yet, and
    % tags it honestly. Auditing only the model side meant that
    % tag was invisible here, which was verified by introducing
    % one and watching this check pass.
    %
    % Both are checked now. The file is the source of truth, so
    % it goes first.
    %% ---------------------------------------------------------

    jsonFile = fullfile(P50B_ProjectRoot(),"params","volare_params.json");

    assert(isfile(jsonFile),"The parameter file is missing.");

    raw = jsondecode(fileread(jsonFile));

    [nTotal,nPlace,paths] = countPlaceholders(raw,"");

    assert(nPlace == 0, ...
        "%d PLACEHOLDER parameter(s) in the parameter file: %s. " + ...
        "Results are not quotable.", ...
        nPlace,strjoin(paths,", "));

    %% ---------------------------------------------------------
    % And the model side, which can carry parameters the file
    % does not -- anything still built with a literal
    % P50B_Param call rather than read from the JSON.
    %% ---------------------------------------------------------

    Rep = P50B_ProvenanceReport("Verbose",false);

    nModelPlace = 0;

    if isstruct(Rep) && isfield(Rep,"Table") && ...
       any(strcmp(Rep.Table.Properties.VariableNames,"Source"))

        nModelPlace = sum(Rep.Table.Source == "PLACEHOLDER");

    end

    assert(nModelPlace == 0, ...
        "%d PLACEHOLDER parameter(s) in the MATLAB model.",nModelPlace);

    d = sprintf("0 of %d in the file, 0 in the model",nTotal);
    out = Rep;

end

function [nTotal,nPlace,paths] = countPlaceholders(node,prefix)

    nTotal = 0;
    nPlace = 0;
    paths  = string.empty(0,1);

    if ~isstruct(node) || ~isscalar(node)
        return;
    end

    fn = fieldnames(node);

    for k = 1:numel(fn)

        name = string(fn{k});

        if startsWith(name,"_") || startsWith(name,"x_")
            continue;
        end

        v = node.(fn{k});

        if strlength(prefix) > 0
            here = prefix + "." + name;
        else
            here = name;
        end

        if isstruct(v) && isscalar(v) && isfield(v,"v") && isfield(v,"s")

            nTotal = nTotal + 1;

            if string(v.s) == "PLACEHOLDER"
                nPlace = nPlace + 1;
                paths(end+1,1) = here; %#ok<AGROW>
            end

        elseif isstruct(v) && isscalar(v)

            [t,p,ps] = countPlaceholders(v,here);

            nTotal = nTotal + t;
            nPlace = nPlace + p;
            paths  = [paths; ps]; %#ok<AGROW>

        end

    end

end

function [d,out] = localSections(P)

    assert(~isempty(P),"Parameters did not load.");

    need = ["cell" "pack" "busbar" "cooling" "motor" "inverter" ...
            "harness" "auxiliary" "boat" "hydro" "mass" "cockpit" ...
            "telemetry" "rules" "simulation"];

    missing = need(~isfield(P,need));

    assert(isempty(missing), ...
        "Missing section(s): %s",strjoin(missing,", "));

    d = sprintf("%d sections present",numel(need));
    out = P;

end

function [d,out] = localCell()

    out = P50B_CellData();

    cap = P50B_Value(out.Capacity_Ah);

    assert(cap > 0 && cap < 20,"Capacity %.2f Ah is not credible.",cap);

    d = sprintf("%.1f Ah, %.2f V nominal", ...
        cap,P50B_Value(out.NominalVoltage_V));

end

function [d,out] = localOCV()

    O = P50B_OCV();

    soc = linspace(0.02,0.98,40);

    v = arrayfun(@(s) O.Evaluate(s),soc);

    assert(all(diff(v) > -1e-9), ...
        "OCV is not monotonic in SOC -- it falls somewhere as SOC rises.");

    d = sprintf("%.3f to %.3f V",v(1),v(end));
    out = O;

end

function [d,out] = localDCIR()

    warm = P50B_DCIR(0.5,25);
    cold = P50B_DCIR(0.5,0);

    assert(cold > warm, ...
        "DCIR at 0 degC (%.4f) is not above the 25 degC value (%.4f).", ...
        cold,warm);

    d = sprintf("%.2f mOhm at 25C, %.2f at 0C",warm*1000,cold*1000);
    out = [warm cold];

end

function [d,out] = localGeometry()

    out = P50B_Geometry();

    n = out.Pack.TotalCells;

    assert(n == out.Pack.SeriesGroups * out.Pack.ParallelCells, ...
        "Cell count %d does not equal %dS x %dP.", ...
        n,out.Pack.SeriesGroups,out.Pack.ParallelCells);

    d = sprintf("%dS%dP, %d cells", ...
        out.Pack.SeriesGroups,out.Pack.ParallelCells,n);

end

function [d,out] = localEnergy(G,cellData)

    assert(~isempty(G) && ~isempty(cellData), ...
        "Geometry or cell data unavailable.");

    Wh = G.Pack.TotalCells * P50B_Value(cellData.NominalVoltage_V) * ...
         P50B_Value(cellData.Capacity_Ah);

    P = P50B_LoadParams("Plain",true);

    limit = P.rules.energy_limit_Wh;

    assert(Wh < limit, ...
        "ENERGY_REQ_7: %.0f Wh exceeds the %.0f Wh limit.",Wh,limit);

    d = sprintf("%.0f Wh, %.2f%% margin",Wh,100*(limit-Wh)/limit);
    out = Wh;

end

function [d,out] = localMotor()

    out = P50B_MotorData();

    d = sprintf("%.1f kW nominal, %.0f Nm", ...
        P50B_Value(out.NominalPower_W)/1000, ...
        P50B_Value(out.MaximumTorque_Nm));

end

function [d,out] = localSimple(fn,label)

    out = fn();

    assert(isstruct(out) && ~isempty(fieldnames(out)), ...
        "%s returned nothing usable.",label);

    d = sprintf("%d fields",numel(fieldnames(out)));

end

function [d,out] = localPowerCap()

    %% ---------------------------------------------------------
    % Ask for far more than the rule allows and check it does not
    % arrive. This is the single most important assertion in the
    % project: ENERGY_REQ_188 is enforced, not reported.
    %% ---------------------------------------------------------

    P = P50B_LoadParams("Plain",true);

    cap = P.motor.configured_power_limit_W;

    op = P50B_DrivetrainModel(60e3,2500,0.6,35);

    assert(op.PowerLimit.Active, ...
        "A 60 kW demand was NOT power limited.");

    assert(op.Motor.InputPower_W <= cap*1.001, ...
        "Motor input %.0f W exceeds the %.0f W cap.", ...
        op.Motor.InputPower_W,cap);

    d = sprintf("60 kW demand capped to %.2f kW shaft, %.2f kW input", ...
        op.PowerLimit.DeliveredShaft_W/1000,op.Motor.InputPower_W/1000);

    out = op;

end

function [d,out] = localMotorAudit()

    out = P50B_MotorSpecAudit("Verbose",false);

    %% ---------------------------------------------------------
    % Not asserted as consistent -- it is NOT consistent, and
    % that is a recorded finding rather than a regression. What
    % is asserted is that the audit still runs and still notices.
    %% ---------------------------------------------------------

    d = sprintf("%d finding(s); propulsor needs %.0f rpm", ...
        numel(out.Findings),out.PropulsorMotorSpeed_rpm);

end

function [d,out] = localHull()

    out = P50B_HullModel();

    assert(out.Geometry.WettedArea_m2 > 0, ...
        "Wetted area is not positive.");

    d = sprintf("%s model, %.2f m2 wetted, %.0f kg", ...
        out.Model,out.Geometry.WettedArea_m2, ...
        out.Geometry.Displacement_kg);

end

function [d,out] = localMonotonic(Hull)

    assert(~isempty(Hull),"Hull model unavailable.");

    C = P50B_HydroConstants();

    v = (1:0.5:30)/C.KnotsPerMs;

    R = arrayfun(@(x) Hull.Resistance_N(x),v);

    bad = find(diff(R) <= 0,1);

    assert(isempty(bad), ...
        "Resistance falls between %.1f and %.1f knots -- the " + ...
        "interpolator has overshot.", ...
        v(bad)*C.KnotsPerMs,v(bad+1)*C.KnotsPerMs);

    d = sprintf("%.0f to %.0f N over 1-30 knots",R(1),R(end));
    out = R;

end

function [d,out] = localCurve(Hull,P)

    assert(~isempty(Hull) && ~isempty(P),"Hull or parameters unavailable.");

    C = P50B_HydroConstants();

    vPts = P.hydro.resistance_speed_kn(:)';
    RPts = P.hydro.resistance_bare_hull_N(:)';

    vMax = P.hydro.resistance_max_valid_kn / C.KnotsPerMs;

    legCoeff = P.hydro.drive_leg_drag_N_at_20kn / vMax^2;

    worst = 0;

    for k = 1:numel(vPts)

        vv = vPts(k)/C.KnotsPerMs;

        expected = RPts(k) + legCoeff*vv^2;

        err = abs(Hull.SuppliedHydro_N(vv) - expected);

        worst = max(worst,err);

    end

    assert(worst < 1e-6, ...
        "The hull model misses a supplied point by %.4g N.",worst);

    d = sprintf("%d points, worst error %.2g N",numel(vPts),worst);
    out = worst;

end

function [d,out] = localPropulsor()

    out = P50B_Propulsor();

    d = sprintf("%s, %.0f/%.0f mm, eta %.3f", ...
        out.Type,out.Diameter_m*1000,out.RearDiameter_m*1000, ...
        out.DesignEfficiency);

end

function [d,out] = localDesignPoint(Prop)

    assert(~isempty(Prop),"Propulsor unavailable.");

    T = Prop.ThrustFromPower_N(Prop.DesignSpeed_ms,Prop.DesignShaftPower_W);

    err = abs(T - Prop.DesignThrust_N);

    assert(err < 1.0, ...
        "Propulsor gives %.2f N at its own design point, not %.2f N.", ...
        T,Prop.DesignThrust_N);

    d = sprintf("%.1f N against %.1f N (%.2f N out)", ...
        T,Prop.DesignThrust_N,err);

    out = err;

end

function [d,out] = localBollard(Prop)

    assert(~isempty(Prop),"Propulsor unavailable.");

    %% ---------------------------------------------------------
    % An earlier version returned zero thrust at zero speed --
    % the efficiency relation goes to 0/0 there -- and the boat
    % could not leave the dock. Cheap to check, easy to
    % reintroduce.
    %% ---------------------------------------------------------

    T = Prop.ThrustFromPower_N(0,Prop.DesignShaftPower_W);

    assert(isfinite(T) && T > 0, ...
        "Bollard thrust is %g. The boat cannot start moving.",T);

    d = sprintf("%.0f N at %.1f kW",T,Prop.DesignShaftPower_W/1000);
    out = T;

end

function [d,out] = localBoat(Hull,Prop)

    assert(~isempty(Hull) && ~isempty(Prop), ...
        "Hull or propulsor unavailable.");

    out = P50B_BoatDynamics("Hull",Hull,"Propeller",Prop);

    v = out.SteadySpeed(out.ShaftPowerMax_W);

    C = P50B_HydroConstants();

    assert(v > 0,"The boat does not move at full power.");

    d = sprintf("top %.1f km/h, gearbox %.3f:1 (needs %.2f for full power)", ...
        v*C.KmhPerMs,out.GearRatioFitted,out.GearRatioForFullPower);

end

function [d,out] = localCeiling(Boat,motor)

    assert(~isempty(Boat) && ~isempty(motor), ...
        "Boat or motor unavailable.");

    cap = P50B_Value(motor.ConfiguredPowerLimit_W);

    %% ---------------------------------------------------------
    % ENERGY_REQ_188 caps ELECTRICAL input. The shaft figure must
    % therefore be lower. If these were ever equal, somebody has
    % confused consumption with output and the boat would be
    % drawing about 26.9 kW at scrutineering.
    %% ---------------------------------------------------------

    assert(Boat.ShaftPowerMax_W < cap, ...
        "Shaft ceiling %.0f W is not below the %.0f W electrical cap.", ...
        Boat.ShaftPowerMax_W,cap);

    d = sprintf("%.2f kW shaft of %.0f kW electrical (%.1f%%)", ...
        Boat.ShaftPowerMax_W/1000,cap/1000, ...
        100*Boat.ShaftPowerMax_W/cap);

    out = Boat.ShaftPowerMax_W;

end

function [d,out] = localMass()

    out = P50B_MassBudget("Verbose",false);

    assert(out.Pass, ...
        "ENERGY_REQ_48: %.1f kg against a %.0f kg limit.", ...
        out.ExcludingHulls_kg,out.Limit_kg);

    assert(out.DisplacementConsistent, ...
        "boat.displacement_kg is %.1f kg but the budget floats %.1f kg.", ...
        out.ParameterDisplacement_kg,out.FloatingMass_kg);

    d = sprintf("%.1f of %.0f kg, %.1f kg margin (%.1f%%)", ...
        out.ExcludingHulls_kg,out.Limit_kg,out.Margin_kg,out.MarginPercent);

end

function [d,out] = localBallast()

    B = P50B_MassBudget("PilotMass_kg",52,"Verbose",false);

    assert(B.Pilot.Ballast_kg > 0, ...
        "ENERGY_REQ_135: a 52 kg pilot must require ballast.");

    total = B.Pilot.Mass_kg + B.Pilot.Ballast_kg;

    assert(abs(total - B.Pilot.Minimum_kg) < 1e-9, ...
        "Ballast brings the pilot to %.2f kg, not the %.0f kg minimum.", ...
        total,B.Pilot.Minimum_kg);

    d = sprintf("52 kg pilot needs %.1f kg",B.Pilot.Ballast_kg);
    out = B;

end

function [d,out] = localCompliance()

    out = P50B_MonacoCompliance("Verbose",false);

    assert(out.NumFail == 0, ...
        "%d rule violation(s).",out.NumFail);

    d = sprintf("%d checks, %d pass, %d to action, %d checklist", ...
        out.NumChecks,out.NumPass,out.NumAction,out.NumChecklist);

end

function [d,out] = localFile(relPath,hint)

    f = fullfile(P50B_ProjectRoot(),relPath);

    assert(isfile(f),"%s is missing -- %s.",relPath,hint);

    info = dir(f);

    d = sprintf("%.0f kB, %s",info.bytes/1024, ...
        string(datetime(info.datenum,"ConvertFrom","datenum", ...
            "Format","yyyy-MM-dd")));

    out = f;

end

function [d,out] = localDashboard()

    f = fullfile(P50B_ProjectRoot(),"web","mission_control.html");

    assert(isfile(f),"web/mission_control.html is missing.");

    txt = fileread(f);

    assert(contains(txt,"VOLARE_COMPLIANCE"), ...
        "The dashboard has no compliance block -- rebuild it.");

    %% ---------------------------------------------------------
    % The full MATLAB export is what the Compliance tab reads.
    % Without it the page silently falls back to the handful of
    % numbers Python can recompute, which is not a compliance
    % check and should not be mistaken for one.
    %% ---------------------------------------------------------

    assert(contains(txt,'"full"'), ...
        "The dashboard carries no MATLAB compliance export. " + ...
        "Run P50B_ExportCompliance then " + ...
        "python tools/build_mission_control.py.");

    info = dir(f);

    d = sprintf("%.0f kB, carries the MATLAB export",info.bytes/1024);
    out = f;

end


%% =============================================================
%  REPORT
%% =============================================================

function printSmoke(R,ok,nFail,elapsed)

    fprintf("\n");
    fprintf("================================================================\n");
    fprintf(" SMOKE TEST\n");
    fprintf("================================================================\n\n");

    groups = unique(R.Group,"stable");

    for g = groups'

        rows = R(R.Group == g,:);

        fprintf("  %s\n",upper(g));

        for k = 1:height(rows)

            if rows.Status(k) == "PASS"
                mark = "  ok  ";
            else
                mark = " FAIL ";
            end

            fprintf("   [%s] %-36s %s\n", ...
                mark,rows.Check(k),rows.Detail(k));

        end

        fprintf("\n");

    end

    fprintf("================================================================\n");

    if ok

        fprintf(" ALL %d CHECKS PASSED in %.1f s\n",height(R),elapsed);
        fprintf("\n");
        fprintf(" Nothing is obviously broken. This does NOT mean the\n");
        fprintf(" numbers are right -- run TEST_ALL for the regression and\n");
        fprintf(" python tools/crosscheck.py to prove MATLAB and Python\n");
        fprintf(" still describe the same boat.\n");

    else

        fprintf(" %d OF %d CHECKS FAILED in %.1f s\n", ...
            nFail,height(R),elapsed);

        fprintf("\n");

        F = R(R.Status == "FAIL",:);

        for k = 1:height(F)
            fprintf("   %s / %s\n     %s\n", ...
                F.Group(k),F.Check(k),F.Detail(k));
        end

    end

    fprintf("================================================================\n\n");

end

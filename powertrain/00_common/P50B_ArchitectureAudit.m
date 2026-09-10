function Audit = P50B_ArchitectureAudit(varargin)
%P50B_ARCHITECTUREAUDIT  Measure the architecture instead of asserting it.
%
%   Audit = P50B_ArchitectureAudit() counts how much of this project
%   actually obeys the rules it claims to follow, and reports the gaps.
%
%   OPTIONS
%     "Verbose"   logical, default true
%     "Export"    write output/P50B_Architecture.json, default false
%
%   WHY MEASURE IT
%   --------------
%   README.md says "One parameter file. Three models. They cannot
%   disagree." docs/ARCHITECTURE.md says every physical number lives in
%   params/volare_params.json.
%
%   Both were false when written, and stayed false for months, because a
%   claim in a document is not enforced by anything. P50B_Geometry loaded
%   the parameter file and then hard-coded the pack topology. Four
%   drivetrain modules duplicated 89 values that were already in the
%   file. The cross-check passed the whole time, because it compared
%   literals against the file and they happened to agree.
%
%   This function turns those claims into numbers:
%
%     BINDING     what fraction of each module's parameters are read
%                 from the file rather than written as literals
%     PROVENANCE  how much of the design rests on assumption
%     COVERAGE    how much of the model the cross-check actually protects
%     COMPLIANCE  how much of the rule check is computed rather than
%                 declared or deferred
%
%   None of these should be 100%. Derived quantities SHOULD be literals
%   in the module that derives them, and a preliminary design SHOULD rest
%   partly on assumption. The point is not a perfect score -- it is that
%   the number is visible and moves in the direction you intend when you
%   change something.
%
%   WHAT IT CANNOT SEE
%   ------------------
%   It counts P50B_Param against P50B_FromFile by reading source text. A
%   module that reads the file into a local variable and then does its
%   own arithmetic looks "unbound" here and may be perfectly correct. Read
%   the per-module notes, not just the percentage.
%
%   See also SMOKE_TEST, TEST_ALL, P50B_ProvenanceReport, P50B_FromFile.

    opts = struct("Verbose",true,"Export",false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_ArchitectureAudit:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% Self-contained: the audit must run from a cold MATLAB.
    addpath(genpath(fileparts(mfilename("fullpath"))));

    root = P50B_ProjectRoot();

    A = struct();

    A.Generated = string(datetime("now","Format","yyyy-MM-dd HH:mm"));
    A.Root      = string(root);

    %% =========================================================
    % 1. PARAMETER FILE
    %% =========================================================

    jsonFile = fullfile(root,"params","volare_params.json");

    raw = jsondecode(fileread(jsonFile));

    [nParams,bySource,sections] = auditFile(raw);

    A.File = struct( ...
        "Path",       "params/volare_params.json", ...
        "Parameters", nParams, ...
        "Sections",   numel(sections), ...
        "SectionNames",{sections}, ...
        "BySource",   bySource);

    %% ---------------------------------------------------------
    % Trust: how much of the design traces to something real?
    %
    % MEASURED, DATASHEET, DIGITISED and PUBLISHED_TEST are
    % traceable to a measurement somebody made. CALCULATED
    % derives from those. DESIGN_CHOICE is a decision, which is
    % legitimate but is not evidence. ASSUMPTION is a guess with
    % a reason.
    %% ---------------------------------------------------------

    traceable = sumFields(bySource, ...
        ["MEASURED" "DATASHEET" "DIGITISED" "PUBLISHED_TEST"]);

    derived = sumFields(bySource,"CALCULATED");
    chosen  = sumFields(bySource,"DESIGN_CHOICE");
    assumed = sumFields(bySource,"ASSUMPTION");
    placeheld = sumFields(bySource,"PLACEHOLDER");

    A.Trust = struct( ...
        "Traceable",     traceable, ...
        "TraceablePct",  100*traceable/nParams, ...
        "Derived",       derived, ...
        "Chosen",        chosen, ...
        "Assumed",       assumed, ...
        "AssumedPct",    100*assumed/nParams, ...
        "Placeholders",  placeheld);

    %% =========================================================
    % 2. BINDING -- LITERALS AGAINST FILE READS
    %% =========================================================

    modules = [ ...
        "01_cell/P50B_CellData.m"
        "03_mechanical/P50B_Geometry.m"
        "03_mechanical/P50B_Busbars.m"
        "06_drivetrain/P50B_MotorData.m"
        "06_drivetrain/P50B_InverterData.m"
        "06_drivetrain/P50B_HarnessData.m"
        "06_drivetrain/P50B_AuxiliaryLoads.m"
        "07_simulation/P50B_MissionProfile.m"
        "07_simulation/P50B_RunMission.m"
        "08_compliance/P50B_MonacoCompliance.m"
        "08_compliance/P50B_MassBudget.m"
        "09_hydro/P50B_HullModel.m"
        "09_hydro/P50B_Propulsor.m"
        "09_hydro/P50B_BoatDynamics.m"
        "P50B_ThermalDesign.m"];

    Module   = strings(0,1);
    FromFile = zeros(0,1);
    Literal  = zeros(0,1);
    Derived  = zeros(0,1);
    Suspect  = zeros(0,1);
    ReadsFile = false(0,1);

    for k = 1:numel(modules)

        f = fullfile(root,modules(k));

        if ~isfile(f)
            continue;
        end

        txt = fileread(f);

        %% -----------------------------------------------------
        % Comment lines are stripped first. Several modules
        % discuss P50B_Param in their headers, and a header that
        % explains the provenance system should not count as a
        % violation of it.
        %% -----------------------------------------------------

        code = stripComments(txt);

        nLiteral = count(code,"P50B_Param(");

        %% -----------------------------------------------------
        % Split the literals: a derivation is not a duplicate.
        %
        % P50B_CellData writes five P50B_Param calls and is 0%
        % "bound", which looks like a violation and is not --
        % all five compute something from file values (radius
        % from diameter, thermal mass, surface area). A literal
        % tagged CALCULATED belongs exactly where it is.
        %
        % What actually matters is a literal that RESTATES a
        % value the file already holds. Those are the ones that
        % drift, and they are the ones counted as Suspect.
        %
        % The split is by the provenance tag inside each call,
        % which is imperfect -- a duplicate mislabelled
        % CALCULATED would hide here -- but it separates the two
        % populations well enough to point at the right modules.
        %% -----------------------------------------------------

        nDerived = countDerivations(code);

        Module(end+1,1)    = modules(k); %#ok<AGROW>
        FromFile(end+1,1)  = count(code,"P50B_FromFile("); %#ok<AGROW>
        Literal(end+1,1)   = nLiteral; %#ok<AGROW>
        Derived(end+1,1)   = nDerived; %#ok<AGROW>
        Suspect(end+1,1)   = nLiteral - nDerived; %#ok<AGROW>
        ReadsFile(end+1,1) = contains(code,"P50B_LoadParams") || ...
                             contains(code,"P50B_FromFile"); %#ok<AGROW>

    end

    Total = FromFile + Literal;

    %% ---------------------------------------------------------
    % Bound fraction counts DERIVATIONS as correctly placed, so
    % a module that only derives scores 100% rather than 0%.
    % Only suspect literals count against it.
    %% ---------------------------------------------------------

    BoundPct = 100*(FromFile + Derived) ./ max(Total,1);

    BoundPct(Total == 0) = NaN;

    A.Binding = table(Module,FromFile,Literal,Derived,Suspect, ...
                      Total,BoundPct,ReadsFile);

    A.BindingTotals = struct( ...
        "FromFile", sum(FromFile), ...
        "Literal",  sum(Literal), ...
        "Derived",  sum(Derived), ...
        "Suspect",  sum(Suspect), ...
        "BoundPct", 100*(sum(FromFile)+sum(Derived)) / ...
                    max(sum(FromFile)+sum(Literal),1));

    %% ---------------------------------------------------------
    % The dangerous case
    %
    % A module that loads the parameter file AND still carries a
    % pile of literals is the pattern that produced every
    % single-source failure in this project. It looks bound. It
    % is not. Flagged specifically rather than left to be
    % spotted in a percentage.
    %% ---------------------------------------------------------

    suspicious = A.Binding(A.Binding.Suspect > 0,:);

    suspicious = sortrows(suspicious,"Suspect","descend");

    A.Suspicious = suspicious;

    %% =========================================================
    % 3. CROSS-CHECK COVERAGE
    %% =========================================================

    ccFile = fullfile(root,"tools","crosscheck.py");

    nChecks = 0;

    if isfile(ccFile)

        cc = fileread(ccFile);

        %% -------------------------------------------------
        % Count the entries of the CHECKS list. Each is a
        % ("name", tol, kind) tuple on its own line.
        %% -------------------------------------------------

        tok = regexp(cc,'\n\s*\("([a-zA-Z0-9_.]+)",\s*[^,]+,\s*"(rel|abs|eq)"\)', ...
            "tokens");

        nChecks = numel(tok);

        names = strings(nChecks,1);

        for k = 1:nChecks
            names(k) = string(tok{k}{1});
        end

    else

        names = strings(0,1);

    end

    A.CrossCheck = struct( ...
        "Quantities", nChecks, ...
        "Names",      {names}, ...
        "Groups",     {unique(extractBefore(names + ".","."))});

    %% =========================================================
    % 4. COMPLIANCE TIERS
    %% =========================================================

    try

        C = P50B_MonacoCompliance("Verbose",false);

        A.Compliance = struct( ...
            "Checks",     C.NumChecks, ...
            "Pass",       C.NumPass, ...
            "Fail",       C.NumFail, ...
            "Action",     C.NumAction, ...
            "Checklist",  C.NumChecklist, ...
            "EvaluatedPct",100*(C.NumChecks-C.NumChecklist)/C.NumChecks);

    catch ME

        A.Compliance = struct("Error",string(ME.message));

    end

    %% =========================================================
    % 5. TEST SURFACE
    %% =========================================================

    A.Tests = struct( ...
        "SmokeChecks",  countProbes(fullfile(root,"SMOKE_TEST.m")), ...
        "RegressionStages", regressionStages(fullfile(root,"TEST_ALL.m")), ...
        "CrossCheckQuantities", nChecks);

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose
        printAudit(A);
    end

    if opts.Export

        out = fullfile(root,"output","P50B_Architecture.json");

        E = A;
        E.Binding = table2struct(A.Binding);

        if ~isempty(A.Suspicious)
            E.Suspicious = table2struct(A.Suspicious);
        else
            E.Suspicious = [];
        end

        fid = fopen(out,"w");
        fprintf(fid,"%s",jsonencode(E,"PrettyPrint",true));
        fclose(fid);

        if opts.Verbose
            fprintf("Written to %s\n\n",out);
        end

    end

    Audit = A;

end


%% =============================================================
%  HELPERS
%% =============================================================

function [n,bySource,sections] = auditFile(node)

    bySource = struct();
    sections = string.empty(0,1);

    fn = fieldnames(node);

    for k = 1:numel(fn)

        name = string(fn{k});

        if startsWith(name,"_") || startsWith(name,"x_")
            continue;
        end

        v = node.(fn{k});

        if isstruct(v) && isscalar(v) && ~isfield(v,"v")
            sections(end+1,1) = name; %#ok<AGROW>
        end

    end

    [n,bySource] = walkCount(node,bySource);

end

function [n,bySource] = walkCount(node,bySource)

    n = 0;

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

        if isstruct(v) && isscalar(v) && isfield(v,"v") && isfield(v,"s")

            n = n + 1;

            src = matlab.lang.makeValidName(string(v.s));

            if isfield(bySource,src)
                bySource.(src) = bySource.(src) + 1;
            else
                bySource.(src) = 1;
            end

        elseif isstruct(v) && isscalar(v)

            [sub,bySource] = walkCount(v,bySource);

            n = n + sub;

        end

    end

end

function t = sumFields(S,names)

    t = 0;

    for k = 1:numel(names)
        if isfield(S,names(k))
            t = t + S.(names(k));
        end
    end

end

function n = countDerivations(code)

    %% ---------------------------------------------------------
    % Count P50B_Param calls whose provenance tag is CALCULATED.
    % Matched over the whole call, since the tag is the third
    % argument and may be several lines down.
    %% ---------------------------------------------------------

    starts = strfind(code,"P50B_Param(");

    n = 0;

    for k = 1:numel(starts)

        %% Look ahead far enough to reach the third argument.
        stop = min(starts(k)+240,strlength(code));

        window = extractBetween(code,starts(k),stop);

        if contains(window,"CALCULATED")
            n = n + 1;
        end

    end

end

function code = stripComments(txt)

    lines = split(string(txt),newline);

    keep = ~startsWith(strip(lines),"%");

    code = strjoin(lines(keep),newline);

end

function n = countProbes(f)

    n = 0;

    if ~isfile(f); return; end

    n = count(fileread(f),"probe(""");

end

function n = regressionStages(f)

    n = 0;

    if ~isfile(f); return; end

    tok = regexp(fileread(f),'nStages\s*=\s*(\d+)',"tokens","once");

    if ~isempty(tok)
        n = str2double(tok{1});
    end

end


%% =============================================================
%  REPORT
%% =============================================================

function printAudit(A)

    fprintf("\n");
    fprintf("================================================================\n");
    fprintf(" ARCHITECTURE AUDIT\n");
    fprintf("================================================================\n");
    fprintf(" %s\n",A.Generated);
    fprintf("================================================================\n");

    %% ---- parameter file -------------------------------------

    fprintf("\nPARAMETER FILE\n");
    fprintf("  %d parameters in %d sections\n", ...
        A.File.Parameters,A.File.Sections);

    order = ["MEASURED" "DATASHEET" "DIGITISED" "PUBLISHED_TEST" ...
             "CALCULATED" "DESIGN_CHOICE" "ASSUMPTION" "PLACEHOLDER"];

    for k = 1:numel(order)

        if ~isfield(A.File.BySource,order(k))
            continue;
        end

        c = A.File.BySource.(order(k));

        fprintf("    %-16s %4d  %5.1f%%  %s\n",order(k),c, ...
            100*c/A.File.Parameters,bar(100*c/A.File.Parameters));

    end

    fprintf("\n  Traceable to a measurement : %d (%.0f%%)\n", ...
        A.Trust.Traceable,A.Trust.TraceablePct);
    fprintf("  Resting on assumption      : %d (%.0f%%)\n", ...
        A.Trust.Assumed,A.Trust.AssumedPct);

    if A.Trust.Placeholders > 0
        fprintf("  PLACEHOLDERS               : %d -- results not quotable\n", ...
            A.Trust.Placeholders);
    end

    %% ---- binding --------------------------------------------

    fprintf("\nPARAMETER BINDING\n");
    fprintf("  Does each module READ the file, or repeat it?\n\n");

    fprintf("  %-26s %6s %8s %8s %6s\n", ...
        "MODULE","file","derived","suspect","ok");

    B = A.Binding;

    for k = 1:height(B)

        [~,shortName] = fileparts(B.Module(k));

        if B.Total(k) == 0

            %% -------------------------------------------------
            % No tagged-parameter calls at all. These modules
            % read the file into plain values and compute with
            % them, which is correct and invisible to a count of
            % constructor calls. Shown rather than omitted --
            % a module missing from an audit table looks like an
            % oversight, and silence is the wrong default in a
            % report about hidden duplication.
            %% -------------------------------------------------

            if B.ReadsFile(k)
                note = "reads the file directly";
            else
                note = "no parameters";
            end

            fprintf("  %-26s %6s %8s %8s %6s   %s\n", ...
                shortName,"-","-","-","-",note);

            continue;

        end

        fprintf("  %-26s %6d %8d %8d %5.0f%%\n", ...
            shortName,B.FromFile(k),B.Derived(k),B.Suspect(k), ...
            B.BoundPct(k));

    end

    fprintf("\n  %-26s %6d %8d %8d %5.0f%%\n","TOTAL", ...
        A.BindingTotals.FromFile,A.BindingTotals.Derived, ...
        A.BindingTotals.Suspect,A.BindingTotals.BoundPct);

    fprintf("\n  file     read from params/volare_params.json\n");
    fprintf("  derived  a literal tagged CALCULATED -- correctly placed\n");
    fprintf("  suspect  a literal that may RESTATE the file. These are\n");
    fprintf("           the ones that drift.\n");

    if height(A.Suspicious) > 0

        fprintf("\n  MODULES WITH SUSPECT LITERALS\n");

        for k = 1:height(A.Suspicious)

            [~,sn] = fileparts(A.Suspicious.Module(k));

            fprintf("    %-26s %d\n",sn,A.Suspicious.Suspect(k));

        end

        fprintf("\n    Not necessarily wrong -- a value genuinely local to\n");
        fprintf("    one model belongs there. But this is the population\n");
        fprintf("    every single-source failure in this project came from,\n");
        fprintf("    so it is the list to work down.\n");

    else

        fprintf("\n  No suspect literals.\n");

    end

    %% ---- coverage -------------------------------------------

    fprintf("\nCROSS-CHECK COVERAGE\n");
    fprintf("  %d quantities compared between MATLAB and Python\n", ...
        A.CrossCheck.Quantities);

    g = A.CrossCheck.Groups;

    if ~isempty(g)
        fprintf("  Groups: %s\n",strjoin(g',", "));
    end

    fprintf("\n  This list IS the coverage. Anything not on it is\n");
    fprintf("  unprotected, and the two largest errors found in this\n");
    fprintf("  project were both in quantities that were not on it.\n");

    %% ---- compliance -----------------------------------------

    if isfield(A.Compliance,"Checks")

        C = A.Compliance;

        fprintf("\nCOMPLIANCE\n");
        fprintf("  %d checks: %d pass, %d fail, %d to action, %d checklist\n", ...
            C.Checks,C.Pass,C.Fail,C.Action,C.Checklist);
        fprintf("  %.0f%% evaluated rather than deferred to inspection\n", ...
            C.EvaluatedPct);

    end

    %% ---- tests ----------------------------------------------

    fprintf("\nTEST SURFACE\n");
    fprintf("  Smoke checks        %d\n",A.Tests.SmokeChecks);
    fprintf("  Regression stages   %d\n",A.Tests.RegressionStages);
    fprintf("  Cross-check         %d quantities\n", ...
        A.Tests.CrossCheckQuantities);

    fprintf("\n================================================================\n\n");

end

function s = bar(pct)

    n = round(pct/4);

    s = string(repmat('#',1,max(n,0)));

end

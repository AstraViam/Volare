function T = P50B_ProvenanceReport(varargin)
%P50B_PROVENANCEREPORT  Audit every tagged parameter in the project.
%
%   T = P50B_ProvenanceReport() loads the cell, motor, inverter, harness,
%   auxiliary and geometry parameter sets and returns a table of every
%   tagged parameter with its value, unit, source and note.
%
%   T = P50B_ProvenanceReport(S1,S2,...) audits the supplied structs
%   instead, using their variable names as the group label.
%
%   The report exists to answer one question honestly: which numbers in
%   this model are real, and which are guesses? Any parameter tagged
%   PLACEHOLDER is printed in a dedicated warning block, because no
%   result that depends on a placeholder should be quoted as a finding.
%
%   See also P50B_Param, P50B_Value.

    %% ---------------------------------------------------------
    % Collect the structs to audit
    %% ---------------------------------------------------------

    if isempty(varargin)

        Sets = struct();

        Sets.Cell      = P50B_CellData();
        Sets.Motor     = P50B_MotorData();
        Sets.Inverter  = P50B_InverterData();
        Sets.Harness   = P50B_HarnessData();
        Sets.Auxiliary = P50B_AuxiliaryLoads();
        Sets.Geometry  = P50B_Geometry();

    else

        Sets = struct();

        for k = 1:numel(varargin)

            label = inputname(k);

            if isempty(label)
                label = sprintf("Set%d",k);
            end

            Sets.(label) = varargin{k};

        end

    end

    %% ---------------------------------------------------------
    % Walk every set
    %% ---------------------------------------------------------

    Group      = strings(0,1);
    Parameter  = strings(0,1);
    Value      = strings(0,1);
    Unit       = strings(0,1);
    Source     = strings(0,1);
    Confidence = zeros(0,1);
    Note       = strings(0,1);

    setNames = fieldnames(Sets);

    for s = 1:numel(setNames)

        [names,vals,units,srcs,confs,notes] = ...
            walkStruct(Sets.(setNames{s}),"");

        n = numel(names);

        Group      = [Group;      repmat(string(setNames{s}),n,1)]; %#ok<AGROW>
        Parameter  = [Parameter;  names];  %#ok<AGROW>
        Value      = [Value;      vals];   %#ok<AGROW>
        Unit       = [Unit;       units];  %#ok<AGROW>
        Source     = [Source;     srcs];   %#ok<AGROW>
        Confidence = [Confidence; confs];  %#ok<AGROW>
        Note       = [Note;       notes];  %#ok<AGROW>

    end

    T = table( ...
        Group, ...
        Parameter, ...
        Value, ...
        Unit, ...
        Source, ...
        Confidence, ...
        Note);

    %% ---------------------------------------------------------
    % Sort worst-confidence first, so the numbers that need
    % attention appear at the top of the table.
    %% ---------------------------------------------------------

    T = sortrows(T,["Confidence" "Group" "Parameter"],"descend");

    %% ---------------------------------------------------------
    % Summary
    %% ---------------------------------------------------------

    fprintf("\n");
    fprintf("================================================================\n");
    fprintf(" P50B PARAMETER PROVENANCE REPORT\n");
    fprintf("================================================================\n");

    allSources = [ ...
        "MEASURED" ...
        "DATASHEET" ...
        "DIGITISED" ...
        "PUBLISHED_TEST" ...
        "CALCULATED" ...
        "DESIGN_CHOICE" ...
        "ASSUMPTION" ...
        "PLACEHOLDER"];

    fprintf("\nParameter count by source:\n\n");

    for k = 1:numel(allSources)

        n = sum(T.Source == allSources(k));

        if n > 0
            fprintf("   %-16s %4d\n",allSources(k),n);
        end

    end

    fprintf("\n   %-16s %4d\n","TOTAL",height(T));

    %% ---------------------------------------------------------
    % Placeholder warning block
    %% ---------------------------------------------------------

    isPlaceholder = T.Source == "PLACEHOLDER";

    if any(isPlaceholder)

        fprintf("\n");
        fprintf("----------------------------------------------------------------\n");
        fprintf(" WARNING: %d PLACEHOLDER PARAMETER(S)\n", ...
            sum(isPlaceholder));
        fprintf("----------------------------------------------------------------\n");
        fprintf(" These numbers were invented to let the model run.\n");
        fprintf(" Any result that depends on them is NOT quotable.\n\n");

        P = T(isPlaceholder,:);

        for k = 1:height(P)

            fprintf("   %s.%s = %s %s\n", ...
                P.Group(k), ...
                P.Parameter(k), ...
                P.Value(k), ...
                P.Unit(k));

            if strlength(P.Note(k)) > 0
                fprintf("        %s\n",P.Note(k));
            end

        end

    else

        fprintf("\nNo PLACEHOLDER parameters. ");
        fprintf("Every number traces to a source.\n");

    end

    %% ---------------------------------------------------------
    % Assumption block
    %% ---------------------------------------------------------

    isAssumption = T.Source == "ASSUMPTION";

    if any(isAssumption)

        fprintf("\n");
        fprintf("----------------------------------------------------------------\n");
        fprintf(" %d ASSUMPTION(S) -- defensible, but unverified\n", ...
            sum(isAssumption));
        fprintf("----------------------------------------------------------------\n");

        A = T(isAssumption,:);

        for k = 1:height(A)

            fprintf("   %s.%s = %s %s\n", ...
                A.Group(k), ...
                A.Parameter(k), ...
                A.Value(k), ...
                A.Unit(k));

        end

    end

    fprintf("\n================================================================\n");

end

%% =============================================================
% Recursive walker
%% =============================================================

function [names,vals,units,srcs,confs,notes] = walkStruct(S,prefix)

    names = strings(0,1);
    vals  = strings(0,1);
    units = strings(0,1);
    srcs  = strings(0,1);
    confs = zeros(0,1);
    notes = strings(0,1);

    if ~isstruct(S) || ~isscalar(S)
        return;
    end

    f = fieldnames(S);

    for k = 1:numel(f)

        value = S.(f{k});

        if strlength(prefix) > 0
            fullName = prefix + "." + string(f{k});
        else
            fullName = string(f{k});
        end

        if isstruct(value) && isfield(value,"IsP50BParam")

            names(end+1,1) = fullName;                 %#ok<AGROW>
            vals(end+1,1)  = formatValue(value.Value); %#ok<AGROW>
            units(end+1,1) = value.Unit;               %#ok<AGROW>
            srcs(end+1,1)  = value.Source;             %#ok<AGROW>
            confs(end+1,1) = value.Confidence;         %#ok<AGROW>
            notes(end+1,1) = value.Note;               %#ok<AGROW>

        elseif isstruct(value) && isscalar(value)

            [n2,v2,u2,s2,c2,t2] = walkStruct(value,fullName);

            names = [names; n2]; %#ok<AGROW>
            vals  = [vals;  v2]; %#ok<AGROW>
            units = [units; u2]; %#ok<AGROW>
            srcs  = [srcs;  s2]; %#ok<AGROW>
            confs = [confs; c2]; %#ok<AGROW>
            notes = [notes; t2]; %#ok<AGROW>

        end

    end

end

%% =============================================================
% Value formatter
%% =============================================================

function s = formatValue(v)

    if isstring(v) || ischar(v)

        s = string(v);

    elseif isnumeric(v) && isscalar(v)

        if v ~= 0 && (abs(v) < 1e-3 || abs(v) >= 1e5)
            s = sprintf("%.4g",v);
        else
            s = sprintf("%.6g",v);
        end

    elseif isnumeric(v)

        s = sprintf("[%s array]",strjoin(string(size(v)),"x"));

    else

        s = "<" + string(class(v)) + ">";

    end

end

function P = P50B_LoadParams(varargin)
%P50B_LOADPARAMS  Read the project's single source of truth.
%
%   P = P50B_LoadParams() loads params/volare_params.json and returns a
%   struct in which every physical parameter is wrapped by P50B_Param, so
%   it carries its unit, provenance tag and note.
%
%   P = P50B_LoadParams("Plain",true) returns bare numeric values instead,
%   which is what calculation code usually wants.
%
%   P = P50B_LoadParams("Reload",true) bypasses the cache after the JSON
%   has been edited in a live session.
%
%   WHY THIS EXISTS
%   ---------------
%   This project has three independent implementations of the same physics:
%   this MATLAB model, the Python reference model, and the JavaScript engine
%   inside Mission Control. Three implementations is a strength -- they
%   cross-check each other -- but only while they describe the same design.
%
%   Before this file existed they did not. MATLAB had a cell DCIR of
%   12.8 mOhm from the datasheet; Python had a digitised R0(SOC,T) map.
%   MATLAB had a two-layer pack; Python a flat one. Neither was wrong on
%   its own terms, and nothing in either codebase could have revealed the
%   disagreement.
%
%   Every physical parameter now lives in params/volare_params.json and all
%   three read it. Add a measurement once and it reaches everywhere.
%
%   ACCESS
%     P.cell.capacity_Ah.Value        provenance-tagged (default)
%     P.cell.capacity_Ah              bare value, with "Plain",true
%
%   Parameter paths are identical to the Python reader, so
%   "cell.capacity_Ah" means the same thing in both languages.
%
%   See also P50B_Param, P50B_ProvenanceReport, P50B_CellData.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct("Plain",false,"Reload",false,"File","");

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_LoadParams:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% =========================================================
    % LOCATE
    %% =========================================================

    if strlength(string(opts.File)) > 0
        jsonFile = string(opts.File);
    else
        jsonFile = fullfile(P50B_ProjectRoot(),"params","volare_params.json");
    end

    if ~isfile(jsonFile)
        error("P50B_LoadParams:FileNotFound", ...
            "Parameter file not found:\n  %s\n" + ...
            "This is the project's single source of truth and every " + ...
            "model needs it.",jsonFile);
    end

    %% =========================================================
    % CACHE
    %
    % Every function wants the parameters, and re-parsing the JSON
    % inside a sweep is pure waste.
    %% =========================================================

    persistent cachedTagged cachedFile cachedDate

    info = dir(jsonFile);

    stale = isempty(cachedTagged) || ...
            ~isequal(cachedFile,jsonFile) || ...
            ~isequal(cachedDate,info.datenum) || ...
            opts.Reload;

    if stale

        raw = jsondecode(fileread(jsonFile));

        cachedTagged = walkAndTag(raw,"");

        cachedFile = jsonFile;
        cachedDate = info.datenum;

        validateTags(cachedTagged);

    end

    %% =========================================================
    % RETURN
    %% =========================================================

    if opts.Plain
        P = P50B_Unwrap(cachedTagged);
    else
        P = cachedTagged;
    end

end

%% =============================================================
% Recursive walker: convert JSON leaves into P50B_Param structs
%% =============================================================

function out = walkAndTag(node,prefix)

    out = struct();

    fn = fieldnames(node);

    for k = 1:numel(fn)

        name = fn{k};

        %% -----------------------------------------------------
        % Keys beginning with _ are documentation.
        %
        % jsondecode maps a leading underscore to "x_", so both
        % spellings are skipped.
        %% -----------------------------------------------------

        if startsWith(name,"_") || startsWith(name,"x_")
            continue;
        end

        value = node.(name);

        if strlength(prefix) > 0
            path = prefix + "." + string(name);
        else
            path = string(name);
        end

        if isLeaf(value)

            %% -------------------------------------------------
            % A provenance-tagged parameter
            %% -------------------------------------------------

            if isfield(value,"n")
                note = string(value.n);
            else
                note = "";
            end

            if isfield(value,"u")
                unit = string(value.u);
            else
                unit = "-";
            end

            out.(name) = P50B_Param( ...
                value.v, ...
                unit, ...
                string(value.s), ...
                "Note",note, ...
                "Reference",path);

        elseif isstruct(value) && isscalar(value)

            out.(name) = walkAndTag(value,path);

        else

            %% -------------------------------------------------
            % Plain data: arrays, strings, cell arrays from the
            % JSON that are not tagged parameters.
            %% -------------------------------------------------

            out.(name) = value;

        end

    end

end

%% =============================================================
% Leaf test
%% =============================================================

function tf = isLeaf(v)

    tf = isstruct(v) && isscalar(v) && ...
         isfield(v,"v") && isfield(v,"s");

end

%% =============================================================
% Validation
%
% An unusable parameter file should fail loudly on load, not
% silently produce a model built on a typo.
%% =============================================================

function validateTags(S)

    bad = collectBadTags(S,"");

    if ~isempty(bad)

        msg = "Unknown provenance tag(s) in the parameter file:" + newline;

        for k = 1:numel(bad)
            msg = msg + "  " + bad(k) + newline;
        end

        msg = msg + "Valid tags: MEASURED, DATASHEET, DIGITISED, " + ...
              "PUBLISHED_TEST, CALCULATED, DESIGN_CHOICE, ASSUMPTION, " + ...
              "PLACEHOLDER";

        error("P50B_LoadParams:BadProvenanceTag","%s",msg);

    end

end

function bad = collectBadTags(S,prefix)

    bad = strings(0,1);

    valid = ["MEASURED" "DATASHEET" "DIGITISED" "PUBLISHED_TEST" ...
             "CALCULATED" "DESIGN_CHOICE" "ASSUMPTION" "PLACEHOLDER"];

    if ~isstruct(S) || ~isscalar(S)
        return;
    end

    fn = fieldnames(S);

    for k = 1:numel(fn)

        v = S.(fn{k});

        if strlength(prefix) > 0
            path = prefix + "." + string(fn{k});
        else
            path = string(fn{k});
        end

        if isstruct(v) && isfield(v,"IsP50BParam")

            if ~any(v.Source == valid)
                bad(end+1,1) = path + ": '" + v.Source + "'"; %#ok<AGROW>
            end

        elseif isstruct(v) && isscalar(v)

            bad = [bad; collectBadTags(v,path)]; %#ok<AGROW>

        end

    end

end

function p = P50B_FromFile(path,varargin)
%P50B_FROMFILE  Build a provenance-tagged parameter from the shared file.
%
%   p = P50B_FromFile("motor.power_nominal_W") returns the P50B_Param for
%   that dotted path in params/volare_params.json, carrying the value,
%   unit, provenance tag and note recorded there.
%
%   p = P50B_FromFile(PATH,"Note",TEXT) appends MATLAB-side context to
%   the note from the file, for cases where this model has something to
%   say that the file does not.
%
%   WHY THIS EXISTS
%   ---------------
%   The project's central claim is that one parameter file describes one
%   boat. For the cell and the geometry that was true. For the drivetrain
%   it was not: P50B_MotorData, P50B_InverterData, P50B_HarnessData and
%   P50B_AuxiliaryLoads built 134 parameters with literal P50B_Param
%   calls that duplicated values already in the file.
%
%   They agreed, which is the problem. A duplicate that agrees is
%   indistinguishable from a single source until the day somebody edits
%   one of them, and then it is indistinguishable from a bug. Exactly
%   that had already happened twice elsewhere -- the pack topology in
%   P50B_Geometry and the cell-to-coolant resistance in
%   P50B_ThermalDesign -- and in both cases the duplicate agreed for
%   months before it did not.
%
%   Writing
%
%       P.NominalPower_W = P50B_FromFile("motor.power_nominal_W");
%
%   instead of
%
%       P.NominalPower_W = P50B_Param(26.9e3,"W","DATASHEET", ...);
%
%   is the same length and cannot drift.
%
%   IT FAILS LOUDLY
%   ---------------
%   A missing path is an error, not a default. A model that silently
%   substitutes something when a parameter is absent is a model that will
%   one day run on a number nobody chose -- and the whole point of the
%   provenance system is that no such number exists.
%
%   See also P50B_Param, P50B_LoadParams, P50B_Value.

    arguments
        path (1,1) string
    end

    arguments (Repeating)
        varargin
    end

    extraNote = "";

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if name == "Note"
            extraNote = string(varargin{k+1});
        else
            error("P50B_FromFile:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

    end

    %% =========================================================
    % WALK THE PATH
    %% =========================================================

    Pt = P50B_LoadParams();

    parts = split(path,".");

    node = Pt;

    for k = 1:numel(parts)

        field = parts(k);

        if ~isstruct(node) || ~isfield(node,field)

            %% -------------------------------------------------
            % Say what IS there. A "not found" that does not
            % suggest the alternatives sends people to the JSON
            % to read it by eye, which is how typos survive.
            %% -------------------------------------------------

            if isstruct(node)
                avail = strjoin(string(fieldnames(node))',", ");
            else
                avail = "(not a section)";
            end

            error("P50B_FromFile:NotFound", ...
                "No parameter '%s' in params/volare_params.json.\n" + ...
                "  Failed at '%s' after '%s'.\n" + ...
                "  Available there: %s", ...
                path,field,strjoin(parts(1:k-1)',"."),avail);

        end

        node = node.(field);

    end

    if ~(isstruct(node) && isfield(node,"IsP50BParam"))

        error("P50B_FromFile:NotALeaf", ...
            "'%s' is a section, not a parameter. Append one of: %s", ...
            path,strjoin(string(fieldnames(node))',", "));

    end

    p = node;

    %% =========================================================
    % MATLAB-SIDE NOTE
    %% =========================================================

    if strlength(extraNote) > 0

        if strlength(p.Note) > 0
            p.Note = p.Note + " " + extraNote;
        else
            p.Note = extraNote;
        end

    end

end

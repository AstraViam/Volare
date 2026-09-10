function p = P50B_Param(value,unit,source,varargin)
%P50B_PARAM  Construct a provenance-tagged parameter.
%
%   p = P50B_Param(VALUE,UNIT,SOURCE) wraps a numeric (or string) VALUE
%   together with its physical UNIT and a SOURCE tag describing where the
%   number came from. Every parameter in this project that feeds a
%   calculation is expected to carry provenance so that no unverified
%   number can silently masquerade as a measured one.
%
%   p = P50B_Param(...,Note=TEXT) attaches a free-text note.
%   p = P50B_Param(...,Tolerance=X) attaches a +/- tolerance in UNIT.
%   p = P50B_Param(...,Reference=TEXT) attaches a citation.
%
%   SOURCE must be one of the following tags:
%
%     "DATASHEET"      Taken directly from a manufacturer datasheet held
%                      in 04_data/. Trustworthy for design.
%
%     "DIGITISED"      Traced from a manufacturer datasheet plot. Real
%                      data, carrying tracing error rather than an
%                      engineering guess.
%
%     "PUBLISHED_TEST" Taken from third-party published characterisation
%                      (bench tests, cell libraries). Reasonable, but not
%                      a manufacturer guarantee.
%
%     "MEASURED"       Measured in-house on this project's own hardware.
%                      Highest confidence.
%
%     "CALCULATED"     Derived from other parameters in this project.
%
%     "DESIGN_CHOICE"  A value the design team selected (a clearance, a
%                      busbar width). Not a physical constant; free to
%                      change, but must be recorded.
%
%     "ASSUMPTION"     An engineering estimate based on typical practice.
%                      Defensible but unverified. Must be reviewed.
%
%     "PLACEHOLDER"    A number invented to let the model run. NOT
%                      defensible. Must be replaced before any result is
%                      quoted. P50B_ProvenanceReport flags these loudly.
%
%   See also P50B_ProvenanceReport, P50B_Value.

    arguments
        value
        unit        (1,1) string
        source      (1,1) string {mustBeMember(source, ...
                        ["DATASHEET" ...
                         "DIGITISED" ...
                         "PUBLISHED_TEST" ...
                         "MEASURED" ...
                         "CALCULATED" ...
                         "DESIGN_CHOICE" ...
                         "ASSUMPTION" ...
                         "PLACEHOLDER"])}
    end

    arguments (Repeating)
        varargin
    end

    %% ---------------------------------------------------------
    % Optional name-value arguments
    %% ---------------------------------------------------------

    opts = struct( ...
        "Note",      "", ...
        "Tolerance", NaN, ...
        "Reference", "");

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_Param:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% ---------------------------------------------------------
    % Assemble
    %% ---------------------------------------------------------

    p.Value     = value;
    p.Unit      = unit;
    p.Source    = source;
    p.Note      = string(opts.Note);
    p.Tolerance = opts.Tolerance;
    p.Reference = string(opts.Reference);

    %% ---------------------------------------------------------
    % Confidence ranking, used for sorting the provenance report
    %
    % 1 = best, 7 = worst
    %% ---------------------------------------------------------

    switch source
        case "MEASURED";       p.Confidence = 1;
        case "DATASHEET";      p.Confidence = 2;
        case "DIGITISED";      p.Confidence = 3;
        case "PUBLISHED_TEST"; p.Confidence = 4;
        case "CALCULATED";     p.Confidence = 5;
        case "DESIGN_CHOICE";  p.Confidence = 6;
        case "ASSUMPTION";     p.Confidence = 7;
        case "PLACEHOLDER";    p.Confidence = 8;
    end

    %% ---------------------------------------------------------
    % Marker so P50B_Value and the report walker can recognise a
    % parameter struct without ambiguity.
    %% ---------------------------------------------------------

    p.IsP50BParam = true;

end

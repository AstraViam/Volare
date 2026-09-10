function v = P50B_Value(p)
%P50B_VALUE  Extract the numeric value from a provenance-tagged parameter.
%
%   v = P50B_Value(P) returns P.Value if P is a struct created by
%   P50B_Param, and returns P unchanged otherwise. This lets calculation
%   code be written against either a tagged parameter or a bare number
%   without branching everywhere.
%
%   See also P50B_Param, P50B_ProvenanceReport.

    if isstruct(p) && isfield(p,"IsP50BParam")
        v = p.Value;
    else
        v = p;
    end

end

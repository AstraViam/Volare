function plain = P50B_Unwrap(S)
%P50B_UNWRAP  Strip provenance wrappers from a whole parameter struct.
%
%   plain = P50B_Unwrap(S) walks struct S recursively and replaces every
%   P50B_Param field with its bare numeric value. The result is a plain
%   struct suitable for fast numerical code, Simulink mask population, or
%   saving to a .mat consumed by tools that do not know about provenance.
%
%   The provenance itself is not lost: it stays in the original struct,
%   and P50B_ProvenanceReport reads it from there.
%
%   See also P50B_Param, P50B_Value, P50B_ProvenanceReport.

    plain = struct();

    names = fieldnames(S);

    for k = 1:numel(names)

        f = names{k};

        value = S.(f);

        if isstruct(value) && isfield(value,"IsP50BParam")

            % A tagged parameter -> take the raw value
            plain.(f) = value.Value;

        elseif isstruct(value) && isscalar(value)

            % A nested struct -> recurse
            plain.(f) = P50B_Unwrap(value);

        else

            % Anything else (arrays, tables, objects) passes through
            plain.(f) = value;

        end

    end

end

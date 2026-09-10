function T = chk(T, name, condition, varargin)
%CHK  Append one check to a result array.
%
%   T = CHK(T, name, condition)
%   T = CHK(T, name, condition, fmt, ...)   with detail shown only on failure
%
%   Keeping the detail lazy matters: a passing run should print one line per
%   check, not a wall of numbers nobody reads.

    if isempty(varargin)
        detail = '';
    else
        detail = sprintf(varargin{:});
    end
    rec = struct('name', name, 'passed', logical(condition), 'detail', detail);
    if isempty(T)
        T = rec;
    else
        T(end+1) = rec; %#ok<AGROW>
    end
end

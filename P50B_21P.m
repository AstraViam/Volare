function P21 = P50B_21P(data,varargin)
%P50B_21P  Build the 21-cell parallel assembly.
%
%   P21 = P50B_21P(data) creates the Simscape Battery parallel assembly
%   representing one 21P group: 21 P50B cells in parallel, arranged as
%   3 rows by 7 columns.
%
%   P21 = P50B_21P(data,"ModelResolution",R) overrides the resolution.
%
%   ON MODEL RESOLUTION
%   -------------------
%   "Detailed" gives every cell its own state. For a 546-cell pack that
%   is 546 sets of states, which simulates slowly but is the only
%   resolution that can show cell-to-cell imbalance.
%
%   "Lumped" collapses the parallel group to a single equivalent cell.
%   It is far faster and is the right choice for energy and thermal
%   studies where within-group imbalance is not the question.
%
%   Detailed is the default here because the parallel group is exactly
%   where imbalance shows up: 21 cells sharing current through unequal
%   busbar path lengths do not share it equally.
%
%   See also P50B_13S21P, P50B_26S21P, P50B_CellData.

    opts = struct( ...
        "ModelResolution","Detailed", ...
        "InterCellGap",[]);

    for k = 1:2:numel(varargin)
        name = string(varargin{k});
        if ~isfield(opts,name)
            error("P50B_21P:UnknownOption","Unknown option '%s'.",name);
        end
        opts.(name) = varargin{k+1};
    end

    if nargin < 1 || isempty(data)
        data = P50B_CellData();
    end

    %% ---------------------------------------------------------
    % Take the cell gap from the geometry module so that the
    % Simscape object and the mechanical model agree.
    %% ---------------------------------------------------------

    if isempty(opts.InterCellGap)
        G = P50B_Geometry();
        gap = G.Cell.Clearance;
    else
        gap = opts.InterCellGap;
    end

    P21 = batteryParallelAssembly( ...
        data.Cell, ...
        21, ...
        Rows=3, ...
        Topology="Square", ...
        InterCellGap=simscape.Value(gap,"m"), ...
        ModelResolution=opts.ModelResolution);

end

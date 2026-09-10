function Layout = P50B_MechanicalLayout(data,varargin)
%P50B_MECHANICALLAYOUT  Pack mechanical layout (compatibility wrapper).
%
%   Layout = P50B_MechanicalLayout(data) returns the full mechanical
%   layout of the 26S21P pack: group positions, all 546 cell positions,
%   and the pack envelope.
%
%   DEPRECATED -- USE THE 03_mechanical FUNCTIONS DIRECTLY
%   -----------------------------------------------------
%   This file used to contain a second, independent implementation of
%   the pack layout. The project therefore had two layout generators
%   that disagreed with each other:
%
%     - different X/Y origin (this one started at a corner, the
%       03_mechanical one centred on the pack)
%     - different Z datum for group centres
%     - different group ordering within a layer
%     - different output field names, so P50B_Verification could only
%       read the output of one of them
%
%   It also read data.Diameter, data.Height and data.Radius, which the
%   cell definition does not define -- it defines Diameter_m, Height_m
%   and Radius_m -- so calling it raised an undefined-field error before
%   it produced anything.
%
%   That duplicate implementation has been removed. This function now
%   delegates to the single authoritative layout:
%
%       G      = P50B_Geometry()
%       Layout = P50B_GroupLayout(G)
%
%   New code should call those directly. This wrapper exists so that
%   older scripts keep working, and it returns the legacy field names
%   alongside the current ones.
%
%   OPTIONS
%     "Plot"    logical, default true
%     "Verbose" logical, default true
%     "Write"   logical, default true -- write CSVs to output/
%
%   See also P50B_Geometry, P50B_GroupLayout, P50B_CellCoordinates.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct("Plot",true,"Verbose",true,"Write",true);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_MechanicalLayout:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% =========================================================
    % CONSISTENCY CHECK
    %
    % The geometry module reads the cell definition itself. If the
    % caller passed a different cell struct, the two would silently
    % disagree. Catch that here rather than produce a pack built
    % from two different cells.
    %% =========================================================

    G = P50B_Geometry();

    if nargin >= 1 && ~isempty(data)

        if isfield(data,"Diameter_m")

            assert(abs(G.Cell.Diameter - data.Diameter_m) < 1e-9, ...
                "P50B_MechanicalLayout:CellMismatch", ...
                "The cell data passed in has diameter %.4f mm but " + ...
                "P50B_Geometry built the pack from %.4f mm.", ...
                data.Diameter_m*1e3, G.Cell.Diameter*1e3);

            assert(abs(G.Cell.Height - data.Height_m) < 1e-9, ...
                "P50B_MechanicalLayout:CellMismatch", ...
                "The cell data passed in has height %.4f mm but " + ...
                "P50B_Geometry built the pack from %.4f mm.", ...
                data.Height_m*1e3, G.Cell.Height*1e3);

        end

    end

    %% =========================================================
    % BUILD THE LAYOUT
    %% =========================================================

    Layout = P50B_GroupLayout(G, ...
        "Plot",    opts.Plot, ...
        "Verbose", opts.Verbose, ...
        "Cells",   true);

    Layout.Geometry = G;

    %% =========================================================
    % LEGACY FIELD ALIASES
    %
    % The old implementation named the group table columns
    % GroupLayer / GroupX / GroupY / GroupZ, and the cell table
    % columns Row / Column. Scripts written against those names
    % still work through these aliases.
    %% =========================================================

    Groups = Layout.Groups;

    Groups.GroupLayer = Groups.Layer;
    Groups.GroupX     = Groups.X;
    Groups.GroupY     = Groups.Y;
    Groups.GroupZ     = Groups.Z;

    Layout.Groups = Groups;

    Cells = Layout.Cells;

    %% ---------------------------------------------------------
    % Legacy "Row" and "Column" columns
    %
    % A table variable cannot be called "Row" while the table's
    % first dimension is also called "Row" -- MATLAB rejects the
    % duplicate. The default dimension names are
    % ["Row" "Variables"], so the dimension is renamed first.
    %
    % This is why the old implementation's Row/Column columns
    % could not simply be reproduced by assignment.
    %% ---------------------------------------------------------

    Cells.Properties.DimensionNames = ["CellIndex" "Variables"];

    if ~ismember("Row",string(Cells.Properties.VariableNames))

        Cells = addvars(Cells,Cells.CellRow, ...
            NewVariableNames="Row", ...
            After="CellColumn");

    end

    if ~ismember("Column",string(Cells.Properties.VariableNames))

        Cells = addvars(Cells,Cells.CellColumn, ...
            NewVariableNames="Column", ...
            After="Row");

    end

    Layout.Cells = Cells;

    %% ---------------------------------------------------------
    % 4 x 4 slot map for layer 1, as the old code returned
    %% ---------------------------------------------------------

    Layout.GroupSlotsLayer1 = Layout.GroupSlots(:,:,1);

    %% =========================================================
    % WRITE COORDINATE FILES
    %% =========================================================

    if opts.Write

        outputDir = fullfile(P50B_ProjectRoot(),"output");

        if ~isfolder(outputDir)
            mkdir(outputDir);
        end

        writetable(Layout.Cells, ...
            fullfile(outputDir,"P50B_26S21P_CellCoordinates.csv"));

        writetable(Layout.Groups, ...
            fullfile(outputDir,"P50B_26S21P_GroupCoordinates.csv"));

        if opts.Verbose
            fprintf("Coordinate files written to output/.\n");
        end

    end

end

function Cells = P50B_CellCoordinates(G,Layout,varargin)
%P50B_CELLCOORDINATES  XYZ coordinates for all 546 cells.
%
%   Cells = P50B_CellCoordinates(G,Layout) generates the position and
%   terminal orientation of every cell in the pack, returned as a
%   546-row table.
%
%   Cells = P50B_CellCoordinates(G,Layout,"Verbose",false) suppresses
%   the summary print.
%
%   COLUMNS
%     CellID          1 to 546, unique
%     SeriesGroup     1 to 26, which series group the cell belongs to
%     Layer           1 or 2
%     CellRow         1 to 3, row within the group
%     CellColumn      1 to 7, column within the group
%     X, Y, Z         cell axis position, metres. Z is the base of the
%                     cell, not its centre.
%     PositiveSide    "TOP" or "BOTTOM"
%     NegativeSide    the opposite face
%     RowPosition     signed offset from the row's centre-feed point,
%                     in cell pitches. Used by the busbar model.
%
%   COORDINATE CONVENTION
%   ---------------------
%   X and Y are centred on the pack. Z has its origin at the base of
%   layer 1, so a cell's body occupies Z to Z + cell height. This is
%   the convention used everywhere in the project; the busbar model
%   depends on it for computing terminal plane heights.
%
%   See also P50B_GroupLayout, P50B_Geometry, P50B_PlotCells.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct("Verbose",true);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_CellCoordinates:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% =========================================================
    % SETUP
    %% =========================================================

    nGroups = G.Pack.SeriesGroups;
    nPer    = G.Pack.ParallelCells;

    totalCells = nGroups * nPer;

    CellID      = zeros(totalCells,1);
    SeriesGroup = zeros(totalCells,1);
    Layer       = zeros(totalCells,1);
    CellRow     = zeros(totalCells,1);
    CellColumn  = zeros(totalCells,1);

    X = zeros(totalCells,1);
    Y = zeros(totalCells,1);
    Z = zeros(totalCells,1);

    RowPosition = zeros(totalCells,1);

    PositiveSide = strings(totalCells,1);
    NegativeSide = strings(totalCells,1);

    %% ---------------------------------------------------------
    % Offsets that centre the 3 x 7 array on the group centre
    %% ---------------------------------------------------------

    x0 = -((G.Group.Columns-1)/2) * G.Group.PitchX;
    y0 = -((G.Group.Rows-1)/2)    * G.Group.PitchY;

    %% ---------------------------------------------------------
    % Centre column index
    %
    % With 7 columns the centre is column 4. The busbar collector
    % is fed here, so each cell's distance from column 4 sets how
    % much current flows in the rail segments beside it.
    %% ---------------------------------------------------------

    centreColumn = (G.Group.Columns + 1)/2;

    %% =========================================================
    % GENERATE
    %% =========================================================

    id = 1;

    for g = 1:nGroups

        gx = Layout.Groups.X(g);
        gy = Layout.Groups.Y(g);
        gz = Layout.Groups.Z(g);

        layer = Layout.Groups.Layer(g);

        %% -----------------------------------------------------
        % Cell orientation follows the group orientation
        %% -----------------------------------------------------

        positive = Layout.Groups.PositiveTerminal(g);
        negative = Layout.Groups.NegativeTerminal(g);

        for r = 1:G.Group.Rows

            for c = 1:G.Group.Columns

                CellID(id)      = id;
                SeriesGroup(id) = g;
                Layer(id)       = layer;
                CellRow(id)     = r;
                CellColumn(id)  = c;

                X(id) = gx + x0 + (c-1)*G.Group.PitchX;
                Y(id) = gy + y0 + (r-1)*G.Group.PitchY;
                Z(id) = gz;

                RowPosition(id) = c - centreColumn;

                PositiveSide(id) = positive;
                NegativeSide(id) = negative;

                id = id + 1;

            end

        end

    end

    %% =========================================================
    % TABLE
    %% =========================================================

    Cells = table( ...
        CellID, ...
        SeriesGroup, ...
        Layer, ...
        CellRow, ...
        CellColumn, ...
        X, ...
        Y, ...
        Z, ...
        RowPosition, ...
        PositiveSide, ...
        NegativeSide);

    %% =========================================================
    % VALIDATION
    %
    % These assertions are cheap and they catch the class of bug
    % that silently produces a plausible-looking but wrong pack.
    %% =========================================================

    assert(height(Cells) == totalCells, ...
        "P50B_CellCoordinates:WrongCellCount", ...
        "Generated %d cells, expected %d.",height(Cells),totalCells);

    groupCounts = accumarray(Cells.SeriesGroup,1);

    assert(all(groupCounts == nPer), ...
        "P50B_CellCoordinates:GroupPopulation", ...
        "Every series group must contain exactly %d cells.",nPer);

    layerCounts = accumarray(Cells.Layer,1);

    assert(all(layerCounts == totalCells/G.Pack.Layers), ...
        "P50B_CellCoordinates:LayerPopulation", ...
        "Every layer must contain %d cells.",totalCells/G.Pack.Layers);

    assert(all(isfinite(Cells.X)) && ...
           all(isfinite(Cells.Y)) && ...
           all(isfinite(Cells.Z)), ...
        "P50B_CellCoordinates:NonFinite", ...
        "All cell coordinates must be finite.");

    assert(numel(unique(Cells.CellID)) == totalCells, ...
        "P50B_CellCoordinates:DuplicateID", ...
        "Cell IDs must be unique.");

    %% ---------------------------------------------------------
    % Interference check
    %
    % No two cells in the same layer may be closer than one cell
    % diameter. This catches a pitch or offset error immediately,
    % which is otherwise very hard to see in a 3D plot.
    %
    % Checked per layer, since layers are separated in Z.
    %% ---------------------------------------------------------

    minSeparation = inf;

    for layer = 1:G.Pack.Layers

        idx = Cells.Layer == layer;

        P = [Cells.X(idx) Cells.Y(idx)];

        D = pdistSimple(P);

        minSeparation = min(minSeparation,min(D));

    end

    assert(minSeparation >= G.Cell.Diameter - 1e-9, ...
        "P50B_CellCoordinates:CellInterference", ...
        "Minimum centre-to-centre spacing is %.3f mm but the cell " + ...
        "diameter is %.3f mm. Cells overlap.", ...
        minSeparation*1e3, G.Cell.Diameter*1e3);

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose

        fprintf("\n");
        fprintf("Cell coordinate model created:\n");
        fprintf("  Total cells        : %d\n",height(Cells));
        fprintf("  Series groups      : %d\n", ...
            numel(unique(Cells.SeriesGroup)));
        fprintf("  Cells per layer    : %d\n",layerCounts(1));
        fprintf("  Min cell spacing   : %.2f mm (diameter %.2f mm)\n", ...
            minSeparation*1e3,G.Cell.Diameter*1e3);
        fprintf("  Edge-to-edge gap   : %.2f mm\n", ...
            (minSeparation - G.Cell.Diameter)*1e3);
        fprintf("\n");

    end

end

%% =============================================================
% Minimum pairwise distance
%
% Implemented locally so the project does not require the
% Statistics Toolbox for pdist.
%% =============================================================

function dmin = pdistSimple(P)

    n = size(P,1);

    dmin = inf(1,1);

    for i = 1:n-1

        dx = P(i+1:end,1) - P(i,1);
        dy = P(i+1:end,2) - P(i,2);

        d = sqrt(dx.^2 + dy.^2);

        dmin = min(dmin,min(d));

    end

end

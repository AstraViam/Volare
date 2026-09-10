function G = P50B_Geometry()
%P50B_GEOMETRY  Master mechanical dimensions for the 26S21P pack.
%
%   G = P50B_Geometry() returns the single authoritative geometry
%   definition for the pack. Every other mechanical function in this
%   project derives from it; no dimension should be hard-coded anywhere
%   else.
%
%   ARCHITECTURE
%     Cell        Molicel INR-21700-P50B, cylindrical
%     Group       21 cells as 3 rows x 7 columns
%     Layer       13 groups placed in a 4 x 4 slot grid
%     Pack        2 layers stacked in Z, 26 groups, 546 cells
%
%   UNITS ARE SI THROUGHOUT (metres).
%
%   ON THE 4 x 4 GRID
%   -----------------
%   13 groups occupy a 16-slot grid, leaving 3 slots empty. The bounding
%   box is still the full 4 x 4 extent, because the 13th group sits in
%   row 4 while rows 1 to 3 are full. Those 3 empty slots are usable
%   volume: they are where the BMS, contactor, fuse and pre-charge
%   hardware should go rather than adding a separate enclosure section.
%   G.Grid.EmptySlots records how many there are.
%
%   See also P50B_GroupLayout, P50B_CellCoordinates, P50B_Busbars.

    %% =========================================================
    % CELL
    %
    % Read straight from the shared parameter file rather than by
    % constructing a full cell definition.
    %
    % P50B_CellData builds a Simscape Battery object, which costs
    % seconds. This function needs four numbers. Calling it here
    % made every geometry query pay for an object nothing in this
    % file touches, and geometry is queried constantly.
    %
    % Both routes read the same params/volare_params.json, so
    % there is still exactly one source of truth.
    %% =========================================================

    Par = P50B_LoadParams('Plain',true);

    G.Cell.Diameter = Par.cell.diameter_m;
    G.Cell.Radius   = Par.cell.diameter_m/2;
    G.Cell.Height   = Par.cell.height_m;
    G.Cell.Mass     = Par.cell.mass_kg;

    %% =========================================================
    % CELL-TO-CELL CLEARANCE
    %
    % A mechanical design choice, not a cell specification.
    %
    % 2 mm is a compromise: enough for a cell holder wall and
    % some thermal isolation between neighbours, tight enough to
    % keep the pack small. Reducing it improves energy density
    % but worsens thermal propagation resistance, which for a
    % 546-cell pack is a safety argument, not just a thermal one.
    %% =========================================================

    G.Cell.Clearance = Par.pack.cell_clearance_m;

    %% =========================================================
    % 21P GROUP ARRAY
    %% =========================================================

    G.Group.Rows          = Par.pack.group_rows;
    G.Group.Columns       = Par.pack.group_cols;
    G.Group.NumberOfCells = Par.pack.n_parallel;

    assert( ...
        G.Group.Rows*G.Group.Columns == G.Group.NumberOfCells, ...
        "P50B_Geometry:GroupArrayMismatch", ...
        "Group rows x columns (%d x %d = %d) must equal the " + ...
        "parallel count (%d). Fix pack.group_rows, pack.group_cols " + ...
        "or pack.n_parallel in params/volare_params.json.", ...
        G.Group.Rows,G.Group.Columns, ...
        G.Group.Rows*G.Group.Columns,G.Group.NumberOfCells);

    %% =========================================================
    % CELL PITCH
    %
    % Square packing. A hexagonal (staggered) arrangement would
    % be about 13% denser for the same clearance, at the cost of
    % a more complex busbar and a non-rectangular group envelope.
    % Square is retained here for busbar simplicity.
    %% =========================================================

    G.Group.PitchX = G.Cell.Diameter + G.Cell.Clearance;
    G.Group.PitchY = G.Cell.Diameter + G.Cell.Clearance;

    %% =========================================================
    % 21P GROUP ENVELOPE
    %% =========================================================

    G.Group.Width = ...
        G.Cell.Diameter + (G.Group.Columns-1)*G.Group.PitchX;

    G.Group.Depth = ...
        G.Cell.Diameter + (G.Group.Rows-1)*G.Group.PitchY;

    G.Group.Height = G.Cell.Height;

    %% =========================================================
    % GROUP-TO-GROUP CLEARANCE
    %
    % Larger than the cell clearance because this gap carries the
    % series interconnect, which must be insulated from both
    % neighbouring groups at up to the full pack potential.
    %% =========================================================

    G.Group.ClearanceX = Par.pack.group_clearance_x_m;
    G.Group.ClearanceY = Par.pack.group_clearance_y_m;

    G.Group.PitchGroupX = G.Group.Width + G.Group.ClearanceX;
    G.Group.PitchGroupY = G.Group.Depth + G.Group.ClearanceY;

    %% =========================================================
    % PACK TOPOLOGY
    %% =========================================================

    %% ---------------------------------------------------------
    % From the parameter file, not from literals.
    %
    % These were 26, 21, 2 and 13 written out longhand, in the
    % one module every other model asks for the pack topology.
    % The file was loaded ten lines above and then ignored for
    % the four numbers that matter most, so editing pack.n_series
    % changed the Python model, the dashboard and the compliance
    % limits -- and left MATLAB quietly building the old pack.
    %
    % It was found by a smoke test: n_parallel was changed to 24
    % to see what would break, and this module went on reporting
    % 21. The cross-check passed too, because it was comparing a
    % literal against the file and they happened to agree.
    %
    % An assertion that the total is 546 would have hidden it
    % just as well, so the assertions below check RELATIONSHIPS
    % between the parameters rather than their values. A design
    % change should be a data edit; only an inconsistent design
    % should fail.
    %% ---------------------------------------------------------

    G.Pack.SeriesGroups  = Par.pack.n_series;
    G.Pack.ParallelCells = Par.pack.n_parallel;

    G.Pack.Layers         = Par.pack.n_layers;
    G.Pack.GroupsPerLayer = Par.pack.groups_per_layer;

    G.Pack.TotalCells = ...
        G.Pack.SeriesGroups * G.Pack.ParallelCells;

    assert( ...
        G.Pack.Layers*G.Pack.GroupsPerLayer == G.Pack.SeriesGroups, ...
        "P50B_Geometry:LayerMismatch", ...
        "pack.n_layers x pack.groups_per_layer (%d x %d = %d) must " + ...
        "equal pack.n_series (%d).", ...
        G.Pack.Layers,G.Pack.GroupsPerLayer, ...
        G.Pack.Layers*G.Pack.GroupsPerLayer,G.Pack.SeriesGroups);

    %% ---------------------------------------------------------
    % The rule, not the arithmetic.
    %
    % ENERGY_REQ_7 caps stored energy at 10 kWh. That is what
    % actually constrains the cell count, so that is what is
    % asserted -- with the limit read from the file rather than
    % a cell count read from memory.
    %% ---------------------------------------------------------

    storedEnergy_Wh = G.Pack.TotalCells * ...
        Par.cell.v_nominal_V * Par.cell.capacity_Ah * ...
        Par.rules.battery_energy_factor;

    assert( ...
        storedEnergy_Wh < Par.rules.energy_limit_Wh, ...
        "P50B_Geometry:EnergyLimitExceeded", ...
        "ENERGY_REQ_7: %dS%dP stores %.0f Wh, over the %.0f Wh " + ...
        "limit. The rule permits at most %d cells of this type.", ...
        G.Pack.SeriesGroups,G.Pack.ParallelCells,storedEnergy_Wh, ...
        Par.rules.energy_limit_Wh, ...
        floor(Par.rules.energy_limit_Wh / ...
              (Par.cell.v_nominal_V*Par.cell.capacity_Ah)));

    G.Pack.StoredEnergy_Wh = storedEnergy_Wh;

    %% =========================================================
    % GROUP SLOT GRID
    %% =========================================================

    G.Grid.Rows    = Par.pack.grid_rows;
    G.Grid.Columns = Par.pack.grid_cols;

    G.Grid.TotalSlots = G.Grid.Rows*G.Grid.Columns;

    G.Grid.EmptySlots = ...
        G.Grid.TotalSlots - G.Pack.GroupsPerLayer;

    assert( ...
        G.Grid.TotalSlots >= G.Pack.GroupsPerLayer, ...
        "P50B_Geometry:GridTooSmall", ...
        "The slot grid cannot hold the required groups per layer.");

    %% =========================================================
    % LAYER SPACING
    %% =========================================================

    G.Layer.CellToCellGap = 10e-3;

    %% =========================================================
    % COOLING
    %% =========================================================

    G.Cooling.BottomPlateThickness     = 5e-3;
    G.Cooling.InterLayerPlateThickness = 5e-3;
    G.Cooling.SideMargin               = 10e-3;

    %% =========================================================
    % ENCLOSURE
    %
    % Not previously modelled. The pack does not float in space:
    % it needs walls, and those walls set the volume that has to
    % fit in the hull.
    %% =========================================================

    G.Enclosure.WallThickness = 3e-3;

    G.Enclosure.InternalClearance = 8e-3;

    G.Enclosure.LidThickness = 3e-3;

    G.Enclosure.BaseThickness = 4e-3;

    %% =========================================================
    % BUSBAR GEOMETRY
    %
    % See P50B_Busbars for how these are used. They live here so
    % that geometry and interconnect share one definition.
    %% =========================================================

    G.Busbar.Thickness = 1.5e-3;

    G.Busbar.EdgeClearance = 2e-3;

    %% ---------------------------------------------------------
    % Collector rail width
    %
    % The rail segment next to the centre feed carries three
    % cells' worth of current. At the worst legal case -- 25 kW
    % drawn at the 65 V minimum bus, 385 A pack -- that is 55 A,
    % which needs 11 mm^2 at the 5 A/mm^2 design density.
    %
    % 6 mm x 1.5 mm gave only 9 mm^2 and made the rails, rather
    % than the series links, the binding ampacity constraint.
    %% ---------------------------------------------------------

    G.Busbar.RailWidth = 8e-3;

    %% ---------------------------------------------------------
    % Series link cross-section
    %
    % Sized so the busbar's continuous rating exceeds both the
    % worst legal operating current and the fuse that protects
    % it, as Monaco ENERGY_REQ_59 requires.
    %
    % Worst legal continuous current is the 25 kW rule limit
    % drawn at the 65 V minimum bus, which is 385 A. At the
    % 5 A/mm^2 design density that needs 77 mm^2; 30 x 3 mm
    % gives 90 mm^2 and a 450 A rating, leaving room for a
    % 400 A fuse beneath it.
    %
    % The earlier 20 x 2 mm (40 mm^2) was sized against the
    % 267 A implied by the Monaco 25 kW cap. That is the wrong
    % driver: the busbars carry whatever the inverter draws, not
    % whatever the rules cap the average at, and at 375 A a
    % 40 mm^2 bar runs at 9.4 A/mm^2.
    %% ---------------------------------------------------------

    G.Busbar.SeriesLinkWidth     = 30e-3;
    G.Busbar.SeriesLinkThickness = 3e-3;

    %% ---------------------------------------------------------
    % Cell-to-busbar joint
    %
    % Wire bonds or laser-welded tabs. This is the single most
    % underestimated resistance in a cylindrical-cell pack: it is
    % in series with every cell, and there are 1092 of these
    % joints in the pack (two per cell).
    %% ---------------------------------------------------------

    G.Busbar.JointsPerCell = 2;

    G.Busbar.WeldResistance = 0.20e-3;

    G.Busbar.WeldsPerJoint = 2;

    %% =========================================================
    % PACK ENVELOPE
    %
    % Span from the outer edge of the first group to the outer
    % edge of the last, across the full 4 x 4 grid extent:
    %
    %   n*Width + (n-1)*Clearance
    %% =========================================================

    G.Pack.Width = ...
        G.Grid.Columns*G.Group.Width + ...
        (G.Grid.Columns-1)*G.Group.ClearanceX;

    G.Pack.Depth = ...
        G.Grid.Rows*G.Group.Depth + ...
        (G.Grid.Rows-1)*G.Group.ClearanceY;

    G.Pack.Height = ...
        G.Cooling.BottomPlateThickness + ...
        G.Cell.Height + ...
        G.Layer.CellToCellGap + ...
        G.Cooling.InterLayerPlateThickness + ...
        G.Cell.Height + ...
        G.Cooling.BottomPlateThickness;

    %% =========================================================
    % EXTERNAL ENVELOPE INCLUDING ENCLOSURE
    %
    % This is the number that has to fit in the boat.
    %% =========================================================

    G.Pack.ExternalWidth = ...
        G.Pack.Width + ...
        2*(G.Enclosure.InternalClearance + G.Enclosure.WallThickness);

    G.Pack.ExternalDepth = ...
        G.Pack.Depth + ...
        2*(G.Enclosure.InternalClearance + G.Enclosure.WallThickness);

    G.Pack.ExternalHeight = ...
        G.Pack.Height + ...
        G.Enclosure.BaseThickness + ...
        G.Enclosure.LidThickness + ...
        G.Enclosure.InternalClearance;

    %% =========================================================
    % VOLUME AND PACKAGING EFFICIENCY
    %
    % Packaging efficiency is the fraction of pack volume that is
    % actually cell. For a cylindrical-cell pack with square
    % packing, values in the 45-55% range are typical. Anything
    % markedly lower means the enclosure or the empty grid slots
    % are costing more than they should.
    %% =========================================================

    G.Pack.InternalVolume_m3 = ...
        G.Pack.Width * G.Pack.Depth * G.Pack.Height;

    G.Pack.ExternalVolume_m3 = ...
        G.Pack.ExternalWidth * ...
        G.Pack.ExternalDepth * ...
        G.Pack.ExternalHeight;

    cellVolume = pi * G.Cell.Radius^2 * G.Cell.Height;

    G.Pack.TotalCellVolume_m3 = ...
        cellVolume * G.Pack.TotalCells;

    G.Pack.PackagingEfficiency = ...
        G.Pack.TotalCellVolume_m3 / G.Pack.ExternalVolume_m3;

    %% =========================================================
    % MASS ROLL-UP
    %
    % Cell mass is known. Everything else is estimated as a
    % fraction of it, which is the standard first-pass approach
    % and is explicitly flagged as an estimate.
    %% =========================================================

    G.Mass.Cells = G.Pack.TotalCells * G.Cell.Mass;

    G.Mass.NonCellFraction = 0.35;

    G.Mass.NonCellEstimate = ...
        G.Mass.Cells * G.Mass.NonCellFraction;

    G.Mass.TotalEstimate = ...
        G.Mass.Cells + G.Mass.NonCellEstimate;

    G.Mass.Note = ...
        "Non-cell mass is a 35% estimate covering holders, " + ...
        "busbars, enclosure, cooling plates, BMS and harness. " + ...
        "Replace with a measured build.";

end

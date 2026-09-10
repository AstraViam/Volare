function Layout = P50B_GroupLayout(G,varargin)
%P50B_GROUPLAYOUT  Spatial and electrical layout of the 26 series groups.
%
%   Layout = P50B_GroupLayout(G) places all 26 series groups in the
%   4 x 4 x 2-layer slot grid defined by G, assigns each group's terminal
%   orientation, and returns the complete layout.
%
%   Layout = P50B_GroupLayout(G,"Plot",false) suppresses the figure.
%   Layout = P50B_GroupLayout(G,"Cells",false) skips cell coordinate
%   generation, which is faster when only group positions are needed.
%
%   OUTPUT CONTRACT
%   ---------------
%   This function is the single source of truth for pack layout. It
%   returns everything downstream code needs:
%
%     Layout.Groups        26-row table: position, layer, terminals
%     Layout.Cells         546-row table: position, group, orientation
%     Layout.PackWidth     metres
%     Layout.PackDepth     metres
%     Layout.PackHeight    metres
%     Layout.GroupSlots    4 x 4 slot occupancy map
%     Layout.PathLength    total series path length, metres
%
%   Earlier revisions of this project had two competing layout
%   generators with different origin conventions, and a verification
%   function that read fields only one of them produced. This function
%   replaces both.
%
%   THE SERPENTINE, AND WHY IT MATTERS
%   ----------------------------------
%   Groups are numbered along a boustrophedon (serpentine) path so that
%   G(n) and G(n+1) are always physically adjacent. Every series link is
%   then a short hop to a neighbour rather than a long run across the
%   pack.
%
%   This is not cosmetic. Series link resistance is proportional to
%   length, and there are 25 of them carrying full pack current. A naive
%   row-major numbering would need a long return conductor at the end of
%   every row.
%
%   Layer 2 is traversed in reverse row order specifically so that G13
%   (end of layer 1) sits directly beneath G14 (start of layer 2),
%   making the inter-layer link a short vertical hop instead of a
%   diagonal run across the pack.
%
%   TERMINAL ALTERNATION
%   --------------------
%   Odd groups are oriented positive-down, even groups positive-up. A
%   series link therefore always joins two terminals on the same face of
%   the pack, alternating between the top and bottom faces. Without this
%   alternation every link would have to climb the full cell height.
%
%   See also P50B_Geometry, P50B_CellCoordinates, P50B_Busbars.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct("Plot",true,"Cells",true,"Verbose",true);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_GroupLayout:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% =========================================================
    % SETUP
    %% =========================================================

    nRows = G.Grid.Rows;
    nCols = G.Grid.Columns;

    nGroups        = G.Pack.SeriesGroups;
    groupsPerLayer = G.Pack.GroupsPerLayer;
    nLayers        = G.Pack.Layers;

    GroupID    = zeros(nGroups,1);
    Layer      = zeros(nGroups,1);
    GridRow    = zeros(nGroups,1);
    GridColumn = zeros(nGroups,1);

    X = zeros(nGroups,1);
    Y = zeros(nGroups,1);
    Z = zeros(nGroups,1);

    slots = zeros(nRows,nCols,nLayers);

    %% =========================================================
    % PLACE GROUPS
    %% =========================================================

    globalGroup = 1;

    lastColumnPlaced = 0;

    for layer = 1:nLayers

        %% -----------------------------------------------------
        % Column direction for this layer's first row
        %
        % Layer 1 simply starts at column 1.
        %
        % Layer 2 must start directly above where layer 1 ended,
        % otherwise the inter-layer link has to run across the
        % pack instead of straight up. Which end of the row that
        % is depends on how many groups landed in layer 1's last
        % row, so it is read from the layout rather than assumed.
        %% -----------------------------------------------------

        if layer == 1
            startAscending = true;
        else
            startAscending = (lastColumnPlaced == 1);
        end

        for localR = 1:nRows

            %% -------------------------------------------------
            % Row traversal order
            %
            % Layer 1 runs top row to bottom row.
            % Layer 2 runs bottom row to top row, so that the
            % first group of layer 2 lands directly above the
            % last group of layer 1.
            %% -------------------------------------------------

            if layer == 1
                r = localR;
            else
                r = nRows - localR + 1;
            end

            %% -------------------------------------------------
            % Column traversal direction alternates each row,
            % producing the serpentine.
            %% -------------------------------------------------

            ascendThisRow = (mod(localR,2) == 1) == startAscending;

            if ascendThisRow
                columns = 1:nCols;
            else
                columns = nCols:-1:1;
            end

            for c = columns

                if globalGroup > layer*groupsPerLayer
                    break;
                end

                GroupID(globalGroup)    = globalGroup;
                Layer(globalGroup)      = layer;
                GridRow(globalGroup)    = r;
                GridColumn(globalGroup) = c;

                X(globalGroup) = (c-1)*G.Group.PitchGroupX;
                Y(globalGroup) = (r-1)*G.Group.PitchGroupY;

                Z(globalGroup) = ...
                    (layer-1)*(G.Cell.Height + G.Layer.CellToCellGap);

                slots(r,c,layer) = globalGroup;

                lastColumnPlaced = c;

                globalGroup = globalGroup + 1;

            end

        end

    end

    assert(globalGroup-1 == nGroups, ...
        "P50B_GroupLayout:PlacementIncomplete", ...
        "Placed %d groups, expected %d.",globalGroup-1,nGroups);

    %% =========================================================
    % CENTRE THE PACK ABOUT THE ORIGIN IN X AND Y
    %
    % Z is left with its origin at the base of layer 1, because
    % the cooling plate and enclosure floor are referenced from
    % there.
    %% =========================================================

    X = X - (G.Pack.Width  - G.Group.Width)/2;
    Y = Y - (G.Pack.Depth  - G.Group.Depth)/2;

    %% =========================================================
    % TERMINAL ORIENTATION
    %% =========================================================

    PositiveTerminal = strings(nGroups,1);
    NegativeTerminal = strings(nGroups,1);

    for g = 1:nGroups

        if mod(g,2) == 1
            PositiveTerminal(g) = "BOTTOM";
            NegativeTerminal(g) = "TOP";
        else
            PositiveTerminal(g) = "TOP";
            NegativeTerminal(g) = "BOTTOM";
        end

    end

    %% ---------------------------------------------------------
    % Pack terminal check
    %
    % With this alternation and an even group count, the pack
    % negative (G1 minus) and pack positive (G26 plus) both land
    % on the TOP face. Convenient: both main terminals, and
    % therefore both HV cables, exit the same face.
    %% ---------------------------------------------------------

    packNegativeFace = NegativeTerminal(1);
    packPositiveFace = PositiveTerminal(nGroups);

    %% =========================================================
    % GROUP TABLE
    %% =========================================================

    Groups = table( ...
        GroupID, ...
        Layer, ...
        GridRow, ...
        GridColumn, ...
        X, ...
        Y, ...
        Z, ...
        PositiveTerminal, ...
        NegativeTerminal);

    Layout.Groups = Groups;

    %% =========================================================
    % SERIES PATH LENGTH
    %
    % Centre-to-centre distance summed along G1 -> G26. A useful
    % single figure of merit for the numbering scheme: a shorter
    % path means less interconnect copper and less loss.
    %% =========================================================

    pathLength = 0;

    stepLength = zeros(nGroups-1,1);

    for g = 1:nGroups-1

        stepLength(g) = sqrt( ...
            (X(g+1)-X(g))^2 + ...
            (Y(g+1)-Y(g))^2 + ...
            (Z(g+1)-Z(g))^2);

        pathLength = pathLength + stepLength(g);

    end

    Layout.PathLength      = pathLength;
    Layout.StepLength      = stepLength;
    Layout.MeanStepLength  = mean(stepLength);
    Layout.MaxStepLength   = max(stepLength);

    %% ---------------------------------------------------------
    % Adjacency check
    %
    % Every consecutive pair should be a neighbour. A step longer
    % than one diagonal group pitch means the serpentine has been
    % broken and a long conductor is required.
    %% ---------------------------------------------------------

    maxAdjacentStep = sqrt( ...
        G.Group.PitchGroupX^2 + ...
        G.Group.PitchGroupY^2 + ...
        (G.Cell.Height + G.Layer.CellToCellGap)^2) * 1.01;

    Layout.NonAdjacentSteps = find(stepLength > maxAdjacentStep);

    Layout.AllStepsAdjacent = isempty(Layout.NonAdjacentSteps);

    %% =========================================================
    % PACK ENVELOPE
    %% =========================================================

    Layout.PackWidth  = G.Pack.Width;
    Layout.PackDepth  = G.Pack.Depth;
    Layout.PackHeight = G.Pack.Height;

    Layout.PackExternalWidth  = G.Pack.ExternalWidth;
    Layout.PackExternalDepth  = G.Pack.ExternalDepth;
    Layout.PackExternalHeight = G.Pack.ExternalHeight;

    Layout.GroupSlots = slots;

    Layout.PackNegativeFace = packNegativeFace;
    Layout.PackPositiveFace = packPositiveFace;

    %% =========================================================
    % CELL COORDINATES
    %
    % Generated here so that Layout is a complete, self-contained
    % description of the pack. Downstream code should not have to
    % call two functions and hope their conventions agree.
    %% =========================================================

    if opts.Cells
        Layout.Cells = P50B_CellCoordinates(G,Layout);
    end

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose

        fprintf("\n");
        fprintf("====================================================\n");
        fprintf(" GROUP LAYOUT\n");
        fprintf("====================================================\n");

        fprintf("Groups placed        : %d\n",nGroups);
        fprintf("Layers               : %d\n",nLayers);
        fprintf("Grid                 : %d x %d (%d slots, %d empty)\n", ...
            nRows,nCols,G.Grid.TotalSlots,G.Grid.EmptySlots);

        fprintf("\n");
        fprintf("Series path length   : %.3f m\n",pathLength);
        fprintf("Mean step            : %.1f mm\n", ...
            Layout.MeanStepLength*1e3);
        fprintf("Longest step         : %.1f mm\n", ...
            Layout.MaxStepLength*1e3);

        if Layout.AllStepsAdjacent
            fprintf("Adjacency            : OK, all 25 links join neighbours\n");
        else
            fprintf("Adjacency            : %d link(s) are NOT neighbours\n", ...
                numel(Layout.NonAdjacentSteps));
        end

        fprintf("\n");
        fprintf("Pack envelope (cells): %.1f x %.1f x %.1f mm\n", ...
            Layout.PackWidth*1e3, ...
            Layout.PackDepth*1e3, ...
            Layout.PackHeight*1e3);

        fprintf("Pack envelope (ext.) : %.1f x %.1f x %.1f mm\n", ...
            Layout.PackExternalWidth*1e3, ...
            Layout.PackExternalDepth*1e3, ...
            Layout.PackExternalHeight*1e3);

        fprintf("Packaging efficiency : %.1f %% of volume is cell\n", ...
            G.Pack.PackagingEfficiency*100);

        fprintf("\n");
        fprintf("Pack negative (G1-)  : %s face\n",packNegativeFace);
        fprintf("Pack positive (G26+) : %s face\n",packPositiveFace);

        fprintf("====================================================\n");

    end

    %% =========================================================
    % PLOT
    %% =========================================================

    if opts.Plot
        plotLayout(G,Layout);
    end

end

%% =============================================================
% Layout plot
%% =============================================================

function plotLayout(G,Layout)

    Groups = Layout.Groups;

    nGroups = height(Groups);

    figure( ...
        "Name","P50B 26S21P Group Layout", ...
        "Color","white");

    hold on;
    grid on;
    axis equal;

    xlabel("X [m]");
    ylabel("Y [m]");
    zlabel("Z [m]");

    title("P50B 26S21P - Series Path G01 to G26");

    %% ---------------------------------------------------------
    % Group footprints
    %% ---------------------------------------------------------

    for g = 1:nGroups

        x = Groups.X(g);
        y = Groups.Y(g);
        z = Groups.Z(g);

        w = G.Group.Width;
        d = G.Group.Depth;

        if Groups.Layer(g) == 1
            faceColour = [0.80 0.88 0.96];
        else
            faceColour = [0.96 0.88 0.80];
        end

        patch( ...
            x + [-w/2 w/2 w/2 -w/2], ...
            y + [-d/2 -d/2 d/2 d/2], ...
            z*[1 1 1 1], ...
            faceColour, ...
            "FaceAlpha",0.55, ...
            "EdgeColor",[0.3 0.3 0.3]);

        text(x,y,z, ...
            sprintf("G%02d",g), ...
            "HorizontalAlignment","center", ...
            "FontWeight","bold", ...
            "FontSize",8);

    end

    %% ---------------------------------------------------------
    % Series path
    %
    % The inter-layer link is drawn in a different colour because
    % it is the one connection that crosses between layers and is
    % mechanically distinct.
    %% ---------------------------------------------------------

    for g = 1:nGroups-1

        isInterLayer = Groups.Layer(g) ~= Groups.Layer(g+1);

        if isInterLayer
            lineSpec = "-";
            lineColour = [0.85 0.20 0.20];
            lineWidth = 2.5;
        else
            lineSpec = "--";
            lineColour = [0.25 0.25 0.25];
            lineWidth = 1.2;
        end

        plot3( ...
            [Groups.X(g) Groups.X(g+1)], ...
            [Groups.Y(g) Groups.Y(g+1)], ...
            [Groups.Z(g) Groups.Z(g+1)], ...
            lineSpec, ...
            "Color",lineColour, ...
            "LineWidth",lineWidth);

    end

    %% ---------------------------------------------------------
    % Pack terminals
    %% ---------------------------------------------------------

    plot3(Groups.X(1),Groups.Y(1),Groups.Z(1), ...
        "o","MarkerSize",12,"LineWidth",2, ...
        "MarkerEdgeColor",[0.1 0.1 0.7]);

    plot3(Groups.X(end),Groups.Y(end),Groups.Z(end), ...
        "o","MarkerSize",12,"LineWidth",2, ...
        "MarkerEdgeColor",[0.7 0.1 0.1]);

    legend( ...
        "off");

    view(35,28);

end

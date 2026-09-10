function Bus = P50B_Busbars(G,Layout,varargin)
%P50B_BUSBARS  Interconnect resistance, loss and ampacity model.
%
%   Bus = P50B_Busbars(G,Layout) builds the electrical interconnect model
%   for the 26S21P pack and evaluates it at every defined operating
%   point.
%
%   Bus = P50B_Busbars(G,Layout,"Plot",false,"Verbose",false) runs
%   silently, which is what sweeps and the drivetrain model want.
%
%   OPTIONS
%     Plot           logical, default true
%     Verbose        logical, default true
%     BusbarTemp_C   conductor temperature, default 60
%     OperatingPoints table of cases to evaluate; defaults to the four
%                    below.
%
%   WHAT THIS MODELS
%   ----------------
%   Three physically distinct resistances in series, per group:
%
%     1. Cell-to-busbar joints.  Two per cell (positive and negative
%        tab), each made of one or more welds or wire bonds. There are
%        1092 of these in the pack. They are in series with every cell
%        and they are routinely left out of first-pass models, which is
%        why those models are optimistic.
%
%     2. Collector rails.  Current from 7 cells converges along a rail
%        to a centre feed. Segments nearer the centre carry more
%        current, so the loss is not simply I-squared-R on the total.
%
%     3. Manifold.  Joins the three row rails to the group terminal.
%        Carries a third of the group current per row over the row
%        pitch.
%
%   plus 25 series links between groups, each carrying full pack current.
%
%   WHAT CHANGED FROM THE PREVIOUS REVISION
%   ---------------------------------------
%   The earlier model computed collector resistance only, at a single
%   267 A operating point, with copper at 20 degC and no ampacity check.
%   That understated interconnect resistance by roughly a factor of two
%   and gave no warning that the series links are undersized for the
%   Competr drivetrain's actual 375 A continuous rating.
%
%   OPERATING POINTS
%   ----------------
%   Sizing against the Monaco 25 kW power cap alone is a mistake. The
%   propulsion system is rated well above it, and the busbars have to
%   survive whatever the inverter asks for, not whatever the rules cap
%   the average at.
%
%   See also P50B_Geometry, P50B_GroupLayout, P50B_BusbarThermal.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct( ...
        "Plot",            true, ...
        "Verbose",         true, ...
        "BusbarTemp_C",    60, ...
        "OperatingPoints", []);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_Busbars:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    %% =========================================================
    % OPERATING POINTS
    %% =========================================================

    if isempty(opts.OperatingPoints)

        Vnom = G.Pack.SeriesGroups * 3.6;
        Vmin = G.Pack.SeriesGroups * 2.5;

        Plimit = 25e3;

        Name = [ ...
            "Monaco cap, nominal V"
            "Monaco cap, minimum V"
            "Competr hardware continuous"
            "FAULT: cap failure, 42 kW"];

        Current_A = [ ...
            Plimit/Vnom
            Plimit/Vmin
            375
            42e3/Vmin];

        Description = [ ...
            "25 kW cap at the 93.6 V nominal bus. The everyday " + ...
                "operating point."
            "25 kW cap at the 65 V minimum bus. THIS IS THE SIZING " + ...
                "DRIVER: the cap fixes power, so current is highest " + ...
                "when the pack is nearly empty."
            "Competr datasheet continuous battery current. Below the " + ...
                "cap-limited worst case, so it is a reference rather " + ...
                "than a constraint."
            "42 kW at minimum bus. NOT an operating point -- the " + ...
                "inverter is hard-capped at 25 kW. Retained only to " + ...
                "check that the fuse can clear a cap failure."];

        %% -----------------------------------------------------
        % Duty classification
        %
        % Continuous cases must meet the sustained current
        % density limit. Peak cases are momentary and are judged
        % against the higher absolute limit instead -- a busbar
        % sized so that a few seconds at maximum power stays
        % under the continuous limit would be needlessly heavy.
        %% -----------------------------------------------------

        Duty = [ ...
            "Continuous"
            "Continuous"
            "Continuous"
            "Peak"];

        opts.OperatingPoints = table(Name,Current_A,Duty,Description);

    end

    OP = opts.OperatingPoints;

    nOP = height(OP);

    %% =========================================================
    % CONDUCTOR MATERIAL
    %
    % Resistivity is evaluated at the busbar operating
    % temperature, not at 20 degC. Copper gains about 0.39% per
    % kelvin; at 60 degC that is 16% more resistance than the
    % handbook value, and busbars in a sealed pack run hotter
    % than people expect.
    %% =========================================================

    rho20  = 1.724e-8;              % Ohm*m, annealed copper at 20 degC
    alpha  = 3.93e-3;               % 1/K
    Tbus   = opts.BusbarTemp_C;

    rhoCu = rho20 * (1 + alpha*(Tbus - 20));

    Bus.Material.Name              = "Copper, annealed (C11000)";
    Bus.Material.Resistivity20C    = rho20;
    Bus.Material.TempCoefficient   = alpha;
    Bus.Material.OperatingTemp_C   = Tbus;
    Bus.Material.ResistivityHot    = rhoCu;
    Bus.Material.Density_kg_m3     = 8960;
    Bus.Material.SpecificHeat_J_kgK = 385;

    %% =========================================================
    % GEOMETRY
    %% =========================================================

    railWidth     = G.Busbar.RailWidth;
    railThickness = G.Busbar.Thickness;
    railArea      = railWidth * railThickness;

    seriesWidth     = G.Busbar.SeriesLinkWidth;
    seriesThickness = G.Busbar.SeriesLinkThickness;
    seriesArea      = seriesWidth * seriesThickness;

    %% ---------------------------------------------------------
    % Manifold
    %
    % Joins the three row rails. It carries up to two thirds of
    % the group current, so it is made wider than a row rail.
    %% ---------------------------------------------------------

    manifoldWidth     = 12e-3;
    manifoldThickness = G.Busbar.Thickness;
    manifoldArea      = manifoldWidth * manifoldThickness;

    Bus.Geometry.RailWidth         = railWidth;
    Bus.Geometry.RailThickness     = railThickness;
    Bus.Geometry.RailArea_mm2      = railArea*1e6;
    Bus.Geometry.SeriesWidth       = seriesWidth;
    Bus.Geometry.SeriesThickness   = seriesThickness;
    Bus.Geometry.SeriesArea_mm2    = seriesArea*1e6;
    Bus.Geometry.ManifoldWidth     = manifoldWidth;
    Bus.Geometry.ManifoldThickness = manifoldThickness;
    Bus.Geometry.ManifoldArea_mm2  = manifoldArea*1e6;

    %% =========================================================
    % 1. CELL-TO-BUSBAR JOINT RESISTANCE
    %
    % Each cell connects to the collector through a joint at each
    % end. A joint may be several parallel welds or wire bonds.
    %
    % Per cell:   R = jointsPerCell * (Rweld / weldsPerJoint)
    % Per group:  that resistance divided by 21, since the cells
    %             are in parallel.
    %% =========================================================

    Rjoint_perCell = G.Busbar.JointsPerCell * ...
        (G.Busbar.WeldResistance / G.Busbar.WeldsPerJoint);

    Rjoint_perGroup = Rjoint_perCell / G.Pack.ParallelCells;

    Rjoint_total = Rjoint_perGroup * G.Pack.SeriesGroups;

    nJoints = G.Pack.TotalCells * G.Busbar.JointsPerCell;

    nWelds = nJoints * G.Busbar.WeldsPerJoint;

    Bus.Joints.ResistancePerWeld_Ohm  = G.Busbar.WeldResistance;
    Bus.Joints.WeldsPerJoint          = G.Busbar.WeldsPerJoint;
    Bus.Joints.JointsPerCell          = G.Busbar.JointsPerCell;
    Bus.Joints.ResistancePerCell_Ohm  = Rjoint_perCell;
    Bus.Joints.ResistancePerGroup_Ohm = Rjoint_perGroup;
    Bus.Joints.TotalResistance_Ohm    = Rjoint_total;
    Bus.Joints.TotalJointCount        = nJoints;
    Bus.Joints.TotalWeldCount         = nWelds;

    %% =========================================================
    % 2. COLLECTOR RAIL RESISTANCE
    %
    % A centre-fed row of 7 cells. Numbering columns from the
    % centre outward, the segment between column offset k and k+1
    % carries the current of every cell beyond it.
    %
    % For 7 cells the two halves each carry 3i, 2i, i, so the
    % loss coefficient is
    %
    %     2 * (3^2 + 2^2 + 1^2) = 28
    %
    % in units of i^2 * R_segment, where i is one cell's current.
    %
    % Computing the coefficient rather than hard-coding 28 means
    % the model stays correct if the group ever changes shape.
    %% =========================================================

    nCols = G.Group.Columns;
    nRows = G.Group.Rows;

    centreColumn = (nCols + 1)/2;

    rowLossCoefficient = 0;

    for c = 1:nCols

        offset = abs(c - centreColumn);

        if offset > 0
            % Number of cells whose current crosses this segment
            cellsBeyond = ceil(offset);
            rowLossCoefficient = rowLossCoefficient + cellsBeyond^2;
        end

    end

    segmentLength = G.Group.PitchX;

    Rsegment = rhoCu * segmentLength / railArea;

    Bus.Collector.RowLossCoefficient = rowLossCoefficient;
    Bus.Collector.SegmentLength_m    = segmentLength;
    Bus.Collector.SegmentResistance_Ohm = Rsegment;

    %% =========================================================
    % 3. MANIFOLD RESISTANCE
    %
    % Three row rails feed a terminal at the centre row. The
    % outer two rows must carry their current one row pitch to
    % reach it; the centre row does not move.
    %
    % Each row carries nCols cells' worth of current.
    %% =========================================================

    manifoldSegmentLength = G.Group.PitchY;

    Rmanifold_segment = rhoCu * manifoldSegmentLength / manifoldArea;

    % Rows that must travel to the centre
    centreRow = (nRows + 1)/2;

    manifoldLossCoefficient = 0;

    for r = 1:nRows

        offset = abs(r - centreRow);

        if offset > 0
            % This row's full current travels 'offset' pitches
            manifoldLossCoefficient = ...
                manifoldLossCoefficient + (nCols^2) * offset;
        end

    end

    Bus.Collector.ManifoldLossCoefficient = manifoldLossCoefficient;
    Bus.Collector.ManifoldSegmentResistance_Ohm = Rmanifold_segment;

    %% ---------------------------------------------------------
    % Equivalent group collector resistance
    %
    % Referred to group current, so it can be summed in series
    % with everything else:
    %
    %     R_eq = Q_total / I_group^2
    %
    % with i = I_group / Np.
    %
    % This is exact for a linear network, not an approximation.
    %% ---------------------------------------------------------

    Np = G.Pack.ParallelCells;

    % Q = nRows * rowCoeff * i^2 * Rseg  +  manifoldCoeff * i^2 * Rman
    % I_group = Np * i
    % R_eq = Q / I_group^2

    Rcollector_perGroup = ...
        (nRows * rowLossCoefficient * Rsegment + ...
         manifoldLossCoefficient * Rmanifold_segment) / Np^2;

    Rcollector_total = Rcollector_perGroup * G.Pack.SeriesGroups;

    Bus.Collector.ResistancePerGroup_Ohm = Rcollector_perGroup;
    Bus.Collector.TotalResistance_Ohm    = Rcollector_total;

    %% =========================================================
    % 4. SERIES LINKS
    %% =========================================================

    nLinks = G.Pack.SeriesGroups - 1;

    LinkID    = (1:nLinks)';
    FromGroup = (1:nLinks)';
    ToGroup   = (2:G.Pack.SeriesGroups)';

    LinkLength     = zeros(nLinks,1);
    LinkResistance = zeros(nLinks,1);
    LinkSurface    = strings(nLinks,1);

    for k = 1:nLinks

        g1 = k;
        g2 = k+1;

        x1 = Layout.Groups.X(g1);
        y1 = Layout.Groups.Y(g1);
        z1 = Layout.Groups.Z(g1);

        x2 = Layout.Groups.X(g2);
        y2 = Layout.Groups.Y(g2);
        z2 = Layout.Groups.Z(g2);

        %% -----------------------------------------------------
        % Which face does this link sit on?
        %
        % Odd group positive is on the BOTTOM, even group
        % positive is on the TOP. A link runs from g1 positive
        % to g2 negative, and because of the alternation those
        % two terminals are always on the same face.
        %% -----------------------------------------------------

        if mod(g1,2) == 1
            zStart = z1;
            zEnd   = z2;
            LinkSurface(k) = "BOTTOM";
        else
            zStart = z1 + G.Cell.Height;
            zEnd   = z2 + G.Cell.Height;
            LinkSurface(k) = "TOP";
        end

        %% -----------------------------------------------------
        % Routed length
        %
        % Straight-line distance understates a real busbar,
        % which must clear cell tops and include bend radii.
        % A routing factor accounts for that.
        %% -----------------------------------------------------

        straightLength = sqrt( ...
            (x2-x1)^2 + (y2-y1)^2 + (zEnd-zStart)^2);

        routingFactor = 1.15;

        L = straightLength * routingFactor;

        LinkLength(k) = L;

        LinkResistance(k) = rhoCu * L / seriesArea;

    end

    IsInterLayer = ...
        Layout.Groups.Layer(FromGroup) ~= ...
        Layout.Groups.Layer(ToGroup);

    Rseries_total = sum(LinkResistance);

    %% =========================================================
    % TOTAL INTERCONNECT RESISTANCE
    %% =========================================================

    Rtotal = Rjoint_total + Rcollector_total + Rseries_total;

    Bus.Rjoint     = Rjoint_total;
    Bus.Rcollector = Rcollector_total;
    Bus.Rseries    = Rseries_total;
    Bus.Rtotal     = Rtotal;

    %% ---------------------------------------------------------
    % Contribution shares
    %
    % The output that tells you which of the three to attack.
    %% ---------------------------------------------------------

    Bus.Share.Joints     = Rjoint_total     / Rtotal;
    Bus.Share.Collectors = Rcollector_total / Rtotal;
    Bus.Share.SeriesLinks = Rseries_total   / Rtotal;

    %% =========================================================
    % AMPACITY AND CURRENT DENSITY
    %
    % Resistance is only half the sizing problem. A conductor
    % also has to survive the current thermally.
    %
    % For busbars in still air with limited convection, sustained
    % current density above about 5 A/mm^2 needs justification;
    % above 8 A/mm^2 it needs forced cooling or a very short duty
    % cycle. These are engineering rules of thumb, not standards.
    %% =========================================================

    Bus.Ampacity.DesignLimit_A_per_mm2 = 5.0;

    Bus.Ampacity.AbsoluteLimit_A_per_mm2 = 8.0;

    Bus.Ampacity.Note = ...
        "Sustained density above the design limit requires " + ...
        "forced cooling or a demonstrated short duty cycle.";

    %% =========================================================
    % EVALUATE EVERY OPERATING POINT
    %% =========================================================

    if ~ismember("Duty",string(OP.Properties.VariableNames))
        OP.Duty = repmat("Continuous",height(OP),1);
    end

    OPName        = strings(nOP,1);
    OPDuty        = strings(nOP,1);
    OPLimit       = zeros(nOP,1);
    OPCurrent     = zeros(nOP,1);
    OPCellCurrent = zeros(nOP,1);
    OPJointLoss   = zeros(nOP,1);
    OPCollLoss    = zeros(nOP,1);
    OPSeriesLoss  = zeros(nOP,1);
    OPTotalLoss   = zeros(nOP,1);
    OPSeriesDensity  = zeros(nOP,1);
    OPRailDensity    = zeros(nOP,1);
    OPDensityOK      = false(nOP,1);
    OPVoltageDrop    = zeros(nOP,1);

    for k = 1:nOP

        I = OP.Current_A(k);

        OPName(k)        = OP.Name(k);
        OPDuty(k)        = OP.Duty(k);
        OPCurrent(k)     = I;
        OPCellCurrent(k) = I / Np;

        %% -----------------------------------------------------
        % Density limit applicable to this duty
        %% -----------------------------------------------------

        if OP.Duty(k) == "Peak"
            OPLimit(k) = Bus.Ampacity.AbsoluteLimit_A_per_mm2;
        else
            OPLimit(k) = Bus.Ampacity.DesignLimit_A_per_mm2;
        end

        OPJointLoss(k)  = I^2 * Rjoint_total;
        OPCollLoss(k)   = I^2 * Rcollector_total;
        OPSeriesLoss(k) = I^2 * Rseries_total;
        OPTotalLoss(k)  = I^2 * Rtotal;

        OPVoltageDrop(k) = I * Rtotal;

        %% -----------------------------------------------------
        % Current density
        %
        % Series links carry full pack current. Row rails carry
        % at most 3 cells' worth at the segment nearest the
        % centre feed.
        %% -----------------------------------------------------

        OPSeriesDensity(k) = I / (seriesArea*1e6);

        peakRailCurrent = ceil((nCols-1)/2) * (I/Np);

        OPRailDensity(k) = peakRailCurrent / (railArea*1e6);

        OPDensityOK(k) = ...
            OPSeriesDensity(k) <= OPLimit(k) && ...
            OPRailDensity(k)   <= OPLimit(k);

    end

    Bus.OperatingPoints = table( ...
        OPName, ...
        OPDuty, ...
        OPLimit, ...
        OPCurrent, ...
        OPCellCurrent, ...
        OPJointLoss, ...
        OPCollLoss, ...
        OPSeriesLoss, ...
        OPTotalLoss, ...
        OPVoltageDrop, ...
        OPSeriesDensity, ...
        OPRailDensity, ...
        OPDensityOK, ...
        'VariableNames',{ ...
            'Case','Duty','DensityLimit_A_mm2','Current_A', ...
            'CellCurrent_A', ...
            'JointLoss_W','CollectorLoss_W','SeriesLoss_W', ...
            'TotalLoss_W','VoltageDrop_V', ...
            'SeriesDensity_A_mm2','RailDensity_A_mm2','DensityOK'});

    %% =========================================================
    % LINK TABLE
    %
    % Loss is reported at the first operating point; scale by
    % (I/I_ref)^2 for any other.
    %% =========================================================

    Iref = OP.Current_A(1);

    LinkPowerLoss = Iref^2 * LinkResistance;

    LinkArea = seriesArea*ones(nLinks,1);

    Bus.SeriesLinks = table( ...
        LinkID, ...
        FromGroup, ...
        ToGroup, ...
        LinkLength, ...
        LinkArea, ...
        LinkResistance, ...
        LinkPowerLoss, ...
        LinkSurface, ...
        IsInterLayer);

    Bus.SeriesLinkReferenceCurrent_A = Iref;

    %% =========================================================
    % COPPER MASS
    %% =========================================================

    railLengthPerGroup = nRows * (nCols-1) * G.Group.PitchX;

    manifoldLengthPerGroup = (nRows-1) * G.Group.PitchY;

    % Two collectors per group: positive and negative face
    collectorVolume = 2 * G.Pack.SeriesGroups * ...
        (railLengthPerGroup*railArea + ...
         manifoldLengthPerGroup*manifoldArea);

    seriesVolume = sum(LinkLength) * seriesArea;

    totalVolume = collectorVolume + seriesVolume;

    Bus.Mass.CollectorVolume_m3 = collectorVolume;
    Bus.Mass.SeriesVolume_m3    = seriesVolume;
    Bus.Mass.TotalVolume_m3     = totalVolume;
    Bus.Mass.TotalMass_kg       = totalVolume * Bus.Material.Density_kg_m3;

    %% =========================================================
    % LEGACY FIELDS
    %
    % Retained so that any existing script or test still reads
    % what it expects. New code should use the OperatingPoints
    % table instead, which covers all four cases rather than one.
    %% =========================================================

    Bus.PackCurrent_A     = OP.Current_A(1);
    Bus.CellCurrent_A     = OP.Current_A(1)/Np;
    Bus.SeriesLoss_W      = OP.Current_A(1)^2 * Rseries_total;
    Bus.CollectorLoss_W   = OP.Current_A(1)^2 * Rcollector_total;
    Bus.TotalLoss_W       = OP.Current_A(1)^2 * Rtotal;
    Bus.CopperResistivity = rhoCu;
    Bus.SeriesWidth       = seriesWidth;
    Bus.SeriesThickness   = seriesThickness;

    Bus.GroupCollectorResistance = ...
        Rcollector_perGroup * ones(G.Pack.SeriesGroups,1);

    %% =========================================================
    % REPORT
    %% =========================================================

    if opts.Verbose
        printReport(Bus,G,nJoints,nWelds);
    end

    %% =========================================================
    % PLOT
    %% =========================================================

    if opts.Plot
        P50B_PlotBusbars(G,Layout,Bus);
    end

end

%% =============================================================
% Report
%% =============================================================

function printReport(Bus,G,nJoints,nWelds)

    fprintf("\n");
    fprintf("================================================================\n");
    fprintf(" BUSBAR AND INTERCONNECT ANALYSIS\n");
    fprintf("================================================================\n");

    fprintf("\nCONDUCTOR\n");
    fprintf("  Material                : %s\n",Bus.Material.Name);
    fprintf("  Assumed temperature     : %.0f degC\n", ...
        Bus.Material.OperatingTemp_C);
    fprintf("  Resistivity at temp     : %.4g Ohm*m ", ...
        Bus.Material.ResistivityHot);
    fprintf("(%.1f%% above 20 degC)\n", ...
        (Bus.Material.ResistivityHot/Bus.Material.Resistivity20C - 1)*100);

    fprintf("\nGEOMETRY\n");
    fprintf("  Collector rail          : %.1f x %.1f mm = %.1f mm^2\n", ...
        Bus.Geometry.RailWidth*1e3, ...
        Bus.Geometry.RailThickness*1e3, ...
        Bus.Geometry.RailArea_mm2);
    fprintf("  Manifold                : %.1f x %.1f mm = %.1f mm^2\n", ...
        Bus.Geometry.ManifoldWidth*1e3, ...
        Bus.Geometry.ManifoldThickness*1e3, ...
        Bus.Geometry.ManifoldArea_mm2);
    fprintf("  Series link             : %.1f x %.1f mm = %.1f mm^2\n", ...
        Bus.Geometry.SeriesWidth*1e3, ...
        Bus.Geometry.SeriesThickness*1e3, ...
        Bus.Geometry.SeriesArea_mm2);

    fprintf("\nRESISTANCE BREAKDOWN\n");
    fprintf("  Cell-to-busbar joints   : %7.3f mOhm  (%4.1f%%)\n", ...
        Bus.Rjoint*1e3, Bus.Share.Joints*100);
    fprintf("  Collector rails         : %7.3f mOhm  (%4.1f%%)\n", ...
        Bus.Rcollector*1e3, Bus.Share.Collectors*100);
    fprintf("  Series links (25)       : %7.3f mOhm  (%4.1f%%)\n", ...
        Bus.Rseries*1e3, Bus.Share.SeriesLinks*100);
    fprintf("  ----------------------------------------\n");
    fprintf("  TOTAL                   : %7.3f mOhm\n",Bus.Rtotal*1e3);

    fprintf("\n  Joint count             : %d joints, %d welds\n", ...
        nJoints,nWelds);
    fprintf("  Interconnect copper     : %.2f kg\n", ...
        Bus.Mass.TotalMass_kg);

    fprintf("\nOPERATING POINTS\n");
    fprintf("  %-24s %-11s %8s %9s %9s %8s\n", ...
        "Case","Duty","I [A]","Loss [W]","dV [V]","Density");
    fprintf("  %s\n",repmat('-',1,78));

    T = Bus.OperatingPoints;

    for k = 1:height(T)

        if T.DensityOK(k)
            flag = "ok";
        else
            flag = "HIGH";
        end

        fprintf("  %-24s %-11s %8.1f %9.1f %9.3f %5.1f %s\n", ...
            T.Case(k), ...
            T.Duty(k), ...
            T.Current_A(k), ...
            T.TotalLoss_W(k), ...
            T.VoltageDrop_V(k), ...
            T.SeriesDensity_A_mm2(k), ...
            flag);

    end

    fprintf("\n  Density limits : %.1f A/mm^2 continuous, %.1f A/mm^2 peak\n", ...
        Bus.Ampacity.DesignLimit_A_per_mm2, ...
        Bus.Ampacity.AbsoluteLimit_A_per_mm2);

    %% ---------------------------------------------------------
    % Flag any operating point that exceeds the density limit
    %% ---------------------------------------------------------

    bad = find(~T.DensityOK);

    if ~isempty(bad)

        fprintf("\n");
        fprintf("  ATTENTION: %d operating point(s) exceed the design\n", ...
            numel(bad));
        fprintf("  current density for the series links.\n\n");

        for k = bad(:)'

            requiredArea = T.Current_A(k) / ...
                T.DensityLimit_A_mm2(k);

            fprintf("    %s\n",T.Case(k));
            fprintf("      %.1f A over %.1f mm^2 = %.1f A/mm^2\n", ...
                T.Current_A(k), ...
                Bus.Geometry.SeriesArea_mm2, ...
                T.SeriesDensity_A_mm2(k));
            fprintf("      Needs >= %.1f mm^2, e.g. %.0f x %.1f mm\n", ...
                requiredArea, ...
                ceil(requiredArea/Bus.Geometry.SeriesThickness/1e3), ...
                Bus.Geometry.SeriesThickness*1e3);

        end

    end

    fprintf("\n================================================================\n");

end

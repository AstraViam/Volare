function outFile = P50B_ExportGeometry(varargin)
%P50B_EXPORTGEOMETRY  Write the pack geometry for the CAD package.
%
%   outFile = P50B_ExportGeometry() writes output/P50B_Geometry.json with
%   the pack envelopes, group layout and mass, for cad/scripts/ to consume.
%
%   OPTIONS
%     "Out"        output path
%     "Geometry"   struct from P50B_Geometry
%     "Verbose"    logical, default true
%
%   WHY THIS EXISTS
%   ---------------
%   The Blender and FreeCAD package needs the pack envelope. It cannot call
%   MATLAB, so it had two options: reproduce the derivation, or consume the
%   answer.
%
%   Reproducing it was tried first and got 717.4 x 340.6 x 173.3 mm against
%   this model's 709.4 x 332.6 x 180.3 -- 8 mm wrong on two axes and 7 mm
%   the other way on the third. The arithmetic looked right. It was not,
%   and it would have been a box in Blender that did not match the box
%   every other model describes.
%
%   That is the ninth instance of the same failure in this project: a
%   duplicated derivation that agrees closely enough to look correct. The
%   cure is the same as the other eight -- derive once, export, consume.
%
%   So the CAD reads this file and asserts against it. If the pack changes,
%   the model in Blender changes with it or the build fails.
%
%   RUN IT AFTER ANY GEOMETRY CHANGE
%   --------------------------------
%   Nothing watches the file for staleness except cad/scripts/powertrain.py,
%   which compares the modification time and warns.
%
%   See also P50B_Geometry, P50B_ExportCompliance.

    opts = struct("Out","","Geometry",[],"Verbose",true);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_ExportGeometry:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if isempty(opts.Geometry)
        G = P50B_Geometry();
    else
        G = opts.Geometry;
    end

    if strlength(string(opts.Out)) > 0
        outFile = string(opts.Out);
    else
        outFile = fullfile(P50B_ProjectRoot(),"output","P50B_Geometry.json");
    end

    P = P50B_LoadParams("Plain",true);

    %% =========================================================
    % ENVELOPES
    %
    % In millimetres, because that is what CAD works in and a
    % unit conversion at the boundary is one more place to be
    % wrong. The MATLAB model works in metres throughout.
    %% =========================================================

    out = struct();

    out.generatedBy = "P50B_ExportGeometry";
    out.generated   = char(string(datetime("now","Format","yyyy-MM-dd HH:mm")));
    out.units       = "mm, kg";

    out.pack = struct( ...
        "nSeries",       G.Pack.SeriesGroups, ...
        "nParallel",     G.Pack.ParallelCells, ...
        "nCells",        G.Pack.TotalCells, ...
        "nLayers",       G.Pack.Layers, ...
        "groupsPerLayer",G.Pack.GroupsPerLayer, ...
        "storedEnergy_Wh", G.Pack.StoredEnergy_Wh);

    %% ---------------------------------------------------------
    % Both envelopes matter and they are different things.
    % CellEnvelope is the volume the cells occupy; Envelope adds
    % the enclosure. Confusing them costs 22 mm on each axis,
    % which is the difference between a lid that closes and one
    % that does not.
    %% ---------------------------------------------------------

    out.packCellEnvelope_mm = [G.Pack.Width, G.Pack.Depth, G.Pack.Height] * 1000;

    out.packEnvelope_mm = [G.Pack.ExternalWidth, ...
                           G.Pack.ExternalDepth, ...
                           G.Pack.ExternalHeight] * 1000;

    out.group = struct( ...
        "rows",     G.Group.Rows, ...
        "cols",     G.Group.Columns, ...
        "cells",    G.Group.NumberOfCells, ...
        "width_mm", G.Group.Width*1000, ...
        "depth_mm", G.Group.Depth*1000, ...
        "pitchX_mm",G.Group.PitchGroupX*1000, ...
        "pitchY_mm",G.Group.PitchGroupY*1000);

    out.grid = struct( ...
        "rows",  G.Grid.Rows, ...
        "cols",  G.Grid.Columns, ...
        "slots", G.Grid.TotalSlots);

    out.cell = struct( ...
        "diameter_mm", P.cell.diameter_m*1000, ...
        "height_mm",   P.cell.height_m*1000, ...
        "mass_kg",     P.cell.mass_kg, ...
        "clearance_mm",P.pack.cell_clearance_m*1000);

    out.mass = struct( ...
        "cells_kg",   P50B_Value(G.Mass.Cells), ...
        "nonCell_kg", P50B_Value(G.Mass.NonCellEstimate), ...
        "pack_kg",    P50B_Value(G.Mass.TotalEstimate));

    %% =========================================================
    % WRITE
    %% =========================================================

    folder = fileparts(outFile);

    if ~isfolder(folder)
        mkdir(folder);
    end

    fid = fopen(outFile,"w");

    if fid < 0
        error("P50B_ExportGeometry:CannotWrite", ...
            "Could not open %s for writing.",outFile);
    end

    fprintf(fid,"%s",jsonencode(out,"PrettyPrint",true));

    fclose(fid);

    if opts.Verbose

        fprintf("\nGeometry exported to:\n  %s\n",outFile);
        fprintf("  pack envelope  %.1f x %.1f x %.1f mm external\n", ...
            out.packEnvelope_mm(1),out.packEnvelope_mm(2), ...
            out.packEnvelope_mm(3));
        fprintf("  cells only     %.1f x %.1f x %.1f mm\n", ...
            out.packCellEnvelope_mm(1),out.packCellEnvelope_mm(2), ...
            out.packCellEnvelope_mm(3));
        fprintf("  %dS%dP, %d cells, %.0f Wh, %.1f kg\n\n", ...
            out.pack.nSeries,out.pack.nParallel,out.pack.nCells, ...
            out.pack.storedEnergy_Wh,out.mass.pack_kg);

    end

end

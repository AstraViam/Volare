function pack = P50B_26S21P(module13S,varargin)
%P50B_26S21P  Build the complete 26S21P pack object.
%
%   pack = P50B_26S21P(module13S) creates the full pack: two 13S21P
%   modules connected electrically in series, giving 26S21P and 546
%   cells.
%
%   pack = P50B_26S21P(module13S,"CoolingPlate","Bottom") adds cooling
%   plates to both modules. This requires a cell-level thermal model,
%   which P50B_CellData enables.
%
%   OPTIONS
%     "StackingAxis"    "X" or "Y", default "Y"
%     "InterModuleGap"  metres, default from P50B_Geometry
%     "CoolingPlate"    "None" (default), "Bottom", or "Top"
%
%   A NOTE ON THE STACKING AXIS
%   ---------------------------
%   The two modules are physically stacked vertically in the real pack:
%   layer 1 sits below layer 2. Simscape Battery's batteryModuleAssembly
%   accepts only "X" or "Y" for StackingAxis, so the vertical
%   arrangement cannot be expressed there directly.
%
%   This affects only the Simscape object's own visualisation. It does
%   not affect the electrical model, which depends on the series
%   connection and not on where the blocks are drawn, and it does not
%   affect the mechanical model, which is built independently by
%   P50B_GroupLayout and does place the layers correctly in Z.
%
%   See also P50B_21P, P50B_13S21P, P50B_GroupLayout.

    opts = struct( ...
        "StackingAxis",   "Y", ...
        "InterModuleGap", [], ...
        "CoolingPlate",   "None");

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_26S21P:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    if isempty(opts.InterModuleGap)
        G = P50B_Geometry();
        gap = G.Layer.CellToCellGap;
    else
        gap = opts.InterModuleGap;
    end

    %% ---------------------------------------------------------
    % Two identical modules in series
    %% ---------------------------------------------------------

    modules = repmat(module13S,1,2);

    moduleAssembly = batteryModuleAssembly( ...
        modules, ...
        CircuitConnection="Series", ...
        StackingAxis=opts.StackingAxis, ...
        NumLevels=2, ...
        InterModuleGap=simscape.Value(gap,"m"));

    %% ---------------------------------------------------------
    % Optional cooling plates
    %% ---------------------------------------------------------

    if opts.CoolingPlate ~= "None"

        for m = 1:numel(moduleAssembly.Module)

            moduleAssembly.Module(m).CoolingPlate = opts.CoolingPlate;

            moduleAssembly.Module(m).CoolingPlateBlockPath = ...
                "batt_lib/Thermal/Parallel Channels";

        end

    end

    pack = batteryPack(moduleAssembly);

end

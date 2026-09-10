function M = P50B_13S21P(P21,varargin)
%P50B_13S21P  Build one 13S21P module from a 21P parallel assembly.
%
%   M = P50B_13S21P(P21) creates a module of 13 parallel assemblies in
%   series. Two of these modules in series form the 26S pack.
%
%   M = P50B_13S21P(P21,"InterParallelAssemblyGap",X) overrides the gap.
%
%   WHY 13 AND NOT 26 IN ONE MODULE
%   -------------------------------
%   Splitting 26S into two 13S modules gives a physical break in the
%   pack at roughly half the pack voltage. That break is where the
%   service disconnect belongs: with it open, no accessible point in
%   either module is above about 55 V.
%
%   It also matches the mechanical layout, which stacks two layers of
%   13 groups.
%
%   See also P50B_21P, P50B_26S21P.

    opts = struct( ...
        "InterParallelAssemblyGap",[], ...
        "ModelResolution","Detailed");

    for k = 1:2:numel(varargin)
        name = string(varargin{k});
        if ~isfield(opts,name)
            error("P50B_13S21P:UnknownOption","Unknown option '%s'.",name);
        end
        opts.(name) = varargin{k+1};
    end

    if isempty(opts.InterParallelAssemblyGap)
        G = P50B_Geometry();
        gap = G.Group.ClearanceX;
    else
        gap = opts.InterParallelAssemblyGap;
    end

    M = batteryModule( ...
        P21, ...
        13, ...
        InterParallelAssemblyGap=simscape.Value(gap,"m"), ...
        ModelResolution=opts.ModelResolution);

end

function OCV = P50B_OCV(soc)
%P50B_OCV  Open-circuit voltage characteristic of the P50B cell.
%
%   OCV = P50B_OCV() returns a struct containing the OCV(SOC) breakpoint
%   table, an interpolation handle, and the inverse SOC(OCV) map.
%
%   V = P50B_OCV(SOC) evaluates the curve directly at the supplied state
%   of charge (0 to 1, scalar or array) and returns volts.
%
%   PROVENANCE -- READ THIS BEFORE QUOTING RESULTS
%   -----------------------------------------------
%   This project does not yet have measured OCV data for the P50B. The
%   table below is a representative high-power NMC 21700 discharge curve
%   that has been anchored to the three datasheet-known points:
%
%       SOC = 1.00   ->  4.20 V   (charge termination)
%       SOC = 0.00   ->  3.00 V   (relaxed OCV at empty; the 2.50 V
%                                  datasheet figure is the cut-off
%                                  under load, not the rest voltage)
%       Mean OCV     ->  3.60 V   (nominal, matches 18 Wh / 5 Ah)
%
%   The shape between those anchors is typical-NMC, not measured. It is
%   good enough for energy bookkeeping and for sizing work. It is NOT
%   good enough for SOC estimation accuracy claims or for a BMS
%   calibration table.
%
%   TO REPLACE WITH MEASURED DATA
%   -----------------------------
%   Run a low-rate (C/20 or slower) discharge, or a GITT/pulse-relaxation
%   sequence, and write the result to:
%
%       04_data/P50B_OCV_SOC.csv     columns: SOC, OCV_V
%
%   If that file exists, this function loads it and reports the source as
%   MEASURED instead of ASSUMPTION. No code changes needed.
%
%   See also P50B_DCIR, P50B_CellData.

    %% =========================================================
    % Prefer measured data if the project has it
    %% =========================================================

    derivedFile = fullfile(P50B_ProjectRoot(), ...
        "params","cells","p50b_derived.json");

    dataFile = fullfile(P50B_ProjectRoot(),"04_data","P50B_OCV_SOC.csv");

    if isfile(derivedFile)

        %% -----------------------------------------------------
        % Preferred: the shared derived dataset.
        %
        % Generated once by tools/export_cell_tables.py from the
        % digitised datasheet curves, so MATLAB, Python and the
        % Mission Control browser engine all use the identical
        % curve. Deriving it separately here would let the three
        % drift apart in the third decimal place.
        %% -----------------------------------------------------

        D = jsondecode(fileread(derivedFile));

        socBreakpoints = D.ocv.soc(:)';
        ocvBreakpoints = D.ocv.v(:)';

        sourceTag = "DIGITISED";

        sourceNote = "Traced from the Molicel datasheet discharge curves, " + ...
                     "IR-corrected. Shared with the Python and browser " + ...
                     "models via params/cells/p50b_derived.json.";

    elseif isfile(dataFile)

        Tbl = readtable(dataFile);

        socBreakpoints = Tbl.SOC(:)';
        ocvBreakpoints = Tbl.OCV_V(:)';

        sourceTag = "MEASURED";

        sourceNote = "Loaded from 04_data/P50B_OCV_SOC.csv.";

    else

        %% -----------------------------------------------------
        % Fallback: representative NMC curve, datasheet-anchored
        %% -----------------------------------------------------

        socBreakpoints = [ ...
            0.00 0.05 0.10 0.15 0.20 0.25 0.30 0.35 0.40 0.45 ...
            0.50 0.55 0.60 0.65 0.70 0.75 0.80 0.85 0.90 0.95 1.00];

        ocvBreakpoints = [ ...
            3.000 3.320 3.440 3.500 3.545 3.580 3.612 3.645 3.680 3.720 ...
            3.762 3.808 3.858 3.912 3.968 4.025 4.080 4.128 4.166 4.190 4.200];

        sourceTag = "ASSUMPTION";

        sourceNote = "Representative NMC 21700 curve anchored to " + ...
                     "datasheet endpoints. Replace with measured data.";

    end

    %% =========================================================
    % Integrity checks
    %
    % A non-monotonic OCV curve makes SOC estimation ill-posed and
    % will silently produce nonsense. Catch it here, not later.
    %% =========================================================

    assert(numel(socBreakpoints) == numel(ocvBreakpoints), ...
        "P50B_OCV:LengthMismatch", ...
        "SOC and OCV breakpoint vectors must be the same length.");

    assert(all(diff(socBreakpoints) > 0), ...
        "P50B_OCV:SOCNotMonotonic", ...
        "SOC breakpoints must be strictly increasing.");

    assert(all(diff(ocvBreakpoints) > 0), ...
        "P50B_OCV:OCVNotMonotonic", ...
        "OCV must increase monotonically with SOC, otherwise the " + ...
        "inverse SOC(OCV) map is not single-valued.");

    assert(socBreakpoints(1) >= 0 && socBreakpoints(end) <= 1, ...
        "P50B_OCV:SOCRange", ...
        "SOC breakpoints must lie within [0,1].");

    %% =========================================================
    % Direct evaluation mode
    %% =========================================================

    if nargin >= 1

        OCV = interp1( ...
            socBreakpoints, ...
            ocvBreakpoints, ...
            min(max(soc,0),1), ...
            "pchip");

        return;

    end

    %% =========================================================
    % Struct mode
    %% =========================================================

    OCV.SOC = socBreakpoints;
    OCV.V   = ocvBreakpoints;

    OCV.Source = sourceTag;
    OCV.Note   = sourceNote;

    %% ---------------------------------------------------------
    % Forward map: SOC -> OCV
    %
    % pchip is used rather than spline because it does not
    % overshoot, which keeps the curve monotonic between
    % breakpoints.
    %% ---------------------------------------------------------

    OCV.Evaluate = @(s) interp1( ...
        socBreakpoints, ...
        ocvBreakpoints, ...
        min(max(s,0),1), ...
        "pchip");

    %% ---------------------------------------------------------
    % Inverse map: OCV -> SOC
    %
    % Valid only at rest. Under load the terminal voltage includes
    % the IR drop and this inversion will read low.
    %% ---------------------------------------------------------

    OCV.InverseEvaluate = @(v) interp1( ...
        ocvBreakpoints, ...
        socBreakpoints, ...
        min(max(v,ocvBreakpoints(1)),ocvBreakpoints(end)), ...
        "pchip");

    %% ---------------------------------------------------------
    % Mean OCV over the full SOC window
    %
    % This is the voltage that sets usable energy, and it is the
    % number to use for range estimates -- not the 3.6 V nominal.
    %% ---------------------------------------------------------

    fineSOC = linspace(0,1,1001);

    OCV.MeanVoltage_V = mean(OCV.Evaluate(fineSOC));

    %% ---------------------------------------------------------
    % Usable-window mean
    %
    % Real operation does not run 0-100%. A 10-95% window is the
    % working assumption for this pack: it protects cycle life at
    % the top and leaves reserve at the bottom.
    %% ---------------------------------------------------------

    OCV.UsableSOCMin = 0.10;
    OCV.UsableSOCMax = 0.95;

    usableSOC = linspace( ...
        OCV.UsableSOCMin, ...
        OCV.UsableSOCMax, ...
        1001);

    OCV.UsableMeanVoltage_V = mean(OCV.Evaluate(usableSOC));

    OCV.UsableFraction = ...
        OCV.UsableSOCMax - OCV.UsableSOCMin;

end

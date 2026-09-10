function DCIR = P50B_DCIR(soc,tempC)
%P50B_DCIR  DC internal resistance surface for the P50B cell.
%
%   DCIR = P50B_DCIR() returns a struct containing the R(SOC,T)
%   breakpoint grid and an evaluation handle.
%
%   R = P50B_DCIR(SOC,TEMPC) evaluates the surface directly and returns
%   ohms. SOC is 0 to 1, TEMPC is in degrees Celsius. Both may be arrays
%   of matching size, or one may be scalar.
%
%   WHY THIS MATTERS MORE THAN IT LOOKS
%   -----------------------------------
%   DCIR is the single parameter that drives cell heating, voltage sag
%   under load, and therefore the achievable power at low SOC. Treating
%   it as one constant number -- as the previous revision of this project
%   did -- hides two effects that dominate real behaviour:
%
%     Cold cells are resistive. At 0 degC the P50B is roughly twice as
%     resistive as at 25 degC, so a cold start costs voltage and heat.
%
%     Empty cells are resistive. Below about 20% SOC resistance climbs
%     steeply, which is exactly when the pack is least able to afford it.
%
%   PROVENANCE -- READ THIS BEFORE QUOTING RESULTS
%   -----------------------------------------------
%   One point on this surface is datasheet-backed:
%
%       R(SOC=0.5, T=25 degC) = 12.8 mOhm
%
%   The variation around that anchor is modelled with typical NMC
%   multipliers and is tagged ASSUMPTION. The shape is defensible; the
%   exact numbers are not measured.
%
%   Independent bench testing has reported P50B units at or below
%   19 mOhm, which is consistent with this surface at the cold and
%   low-SOC corners, and is also a reasonable aged-cell value.
%
%   TO REPLACE WITH MEASURED DATA
%   -----------------------------
%   Run a pulse (HPPC) sequence across SOC and temperature and write:
%
%       04_data/P50B_DCIR_SOC_T.csv
%
%   with columns: SOC, Temp_C, DCIR_Ohm, on a full rectangular grid.
%   This function will then load and use it, reporting MEASURED.
%
%   See also P50B_OCV, P50B_CellData.

    %% =========================================================
    % Prefer measured data if the project has it
    %% =========================================================

    derivedFile = fullfile(P50B_ProjectRoot(), ...
        "params","cells","p50b_derived.json");

    dataFile = fullfile(P50B_ProjectRoot(),"04_data","P50B_DCIR_SOC_T.csv");

    if isfile(derivedFile)

        %% -----------------------------------------------------
        % Preferred: the shared derived R0(SOC,T) map.
        %
        % 41 SOC points x 6 temperatures, extracted pairwise
        % between the digitised rate curves. This is real data,
        % not a typical-NMC shape scaled to one anchor.
        %
        % It includes polarisation built up over the discharge,
        % which is the correct conservative bias for thermal
        % work: sustained resistance is what heats the pack over
        % a race, not the 10 ms value.
        %% -----------------------------------------------------

        D = jsondecode(fileread(derivedFile));

        socBreakpoints  = D.r0.soc(:)';
        tempBreakpoints = D.r0.temp_C(:)';

        % JSON stores [n_temp][n_soc]; the model wants [soc x temp]
        R = D.r0.ohm';

        sourceTag = "DIGITISED";

        sourceNote = "Extracted from the Molicel datasheet rate curves. " + ...
                     "Shared with the Python and browser models via " + ...
                     "params/cells/p50b_derived.json.";

    elseif isfile(dataFile)

        Tbl = readtable(dataFile);

        socBreakpoints  = unique(Tbl.SOC(:))';
        tempBreakpoints = unique(Tbl.Temp_C(:))';

        R = nan(numel(socBreakpoints),numel(tempBreakpoints));

        for k = 1:height(Tbl)

            i = find(socBreakpoints  == Tbl.SOC(k),1);
            j = find(tempBreakpoints == Tbl.Temp_C(k),1);

            R(i,j) = Tbl.DCIR_Ohm(k);

        end

        assert(~any(isnan(R(:))), ...
            "P50B_DCIR:IncompleteGrid", ...
            "04_data/P50B_DCIR_SOC_T.csv must cover a full " + ...
            "rectangular SOC x Temperature grid with no gaps.");

        sourceTag = "MEASURED";

        sourceNote = "Loaded from 04_data/P50B_DCIR_SOC_T.csv.";

    else

        %% -----------------------------------------------------
        % Fallback: datasheet anchor plus typical NMC shape
        %% -----------------------------------------------------

        R_reference = 12.8e-3;      % Ohm, at 50% SOC, 25 degC

        socBreakpoints  = [0.05 0.10 0.20 0.30 0.50 0.70 0.90 1.00];

        tempBreakpoints = [-10 0 10 25 40 55];

        % Multiplier vs SOC, relative to 50% SOC
        socMultiplier = [1.55 1.32 1.12 1.05 1.00 0.98 1.02 1.08];

        % Multiplier vs temperature, relative to 25 degC
        tempMultiplier = [3.00 2.10 1.45 1.00 0.82 0.75];

        R = R_reference * (socMultiplier(:) * tempMultiplier(:)');

        sourceTag = "ASSUMPTION";

        sourceNote = "Datasheet 12.8 mOhm anchor at 50% SOC / 25 degC, " + ...
                     "scaled by typical NMC SOC and temperature trends.";

    end

    %% =========================================================
    % Integrity checks
    %% =========================================================

    assert(all(R(:) > 0), ...
        "P50B_DCIR:NonPositive", ...
        "DCIR must be strictly positive everywhere.");

    assert(all(diff(socBreakpoints) > 0), ...
        "P50B_DCIR:SOCNotMonotonic", ...
        "SOC breakpoints must be strictly increasing.");

    assert(all(diff(tempBreakpoints) > 0), ...
        "P50B_DCIR:TempNotMonotonic", ...
        "Temperature breakpoints must be strictly increasing.");

    %% =========================================================
    % Evaluation function
    %
    % Clamped at the grid edges. Extrapolating a resistance
    % surface is a good way to generate confident nonsense, so it
    % is deliberately not allowed: outside the grid the nearest
    % edge value is returned.
    %% =========================================================

    evaluate = @(s,t) interp2( ...
        tempBreakpoints, ...
        socBreakpoints, ...
        R, ...
        min(max(t,tempBreakpoints(1)),tempBreakpoints(end)), ...
        min(max(s,socBreakpoints(1)),socBreakpoints(end)), ...
        "linear");

    %% =========================================================
    % Direct evaluation mode
    %% =========================================================

    if nargin >= 2

        DCIR = evaluate(soc,tempC);

        return;

    end

    %% =========================================================
    % Struct mode
    %% =========================================================

    DCIR.SOC      = socBreakpoints;
    DCIR.Temp_C   = tempBreakpoints;
    DCIR.R_Ohm    = R;

    DCIR.Evaluate = evaluate;

    DCIR.Source   = sourceTag;
    DCIR.Note     = sourceNote;

    %% ---------------------------------------------------------
    % Convenience reference points
    %% ---------------------------------------------------------

    DCIR.Reference_Ohm = evaluate(0.50,25);

    DCIR.Cold_Ohm      = evaluate(0.50,0);

    DCIR.LowSOC_Ohm    = evaluate(0.10,25);

    DCIR.WorstCase_Ohm = evaluate( ...
        socBreakpoints(1), ...
        tempBreakpoints(1));

    DCIR.BestCase_Ohm  = evaluate(0.70,55);

end
